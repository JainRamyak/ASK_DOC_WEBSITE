"""
tests/test_session_ttl.py

G10: a session expires at whichever fires first of
- an idle timeout (ttl_hours since its last /upload or /query), or
- an absolute cap (max_lifetime_hours since creation, regardless of
  activity).

Before this change, ChromaStore stamped created_at once and never
touched it again, so a session's total lifetime was capped at ttl_hours
from creation even while in active use. Verified against the installed
chromadb 1.5.9: get_or_create_collection()'s metadata= argument is
ignored once a collection exists, so advancing last_activity_at needs
collection.modify(), which replaces metadata wholesale rather than
merging — see ChromaStore._touch_activity().

Run with: pytest tests/test_session_ttl.py -v

Key-free: most cases drive ChromaStore directly against a tmp_path
persist dir; the regression case reuses the stubbed-model `api` fixture
from test_upload_concurrency.py.
"""
import io
import time

import chromadb
import pytest
from starlette.datastructures import UploadFile

import src.storage.chroma_store as chroma_store_module
from src.storage.chroma_store import ChromaStore
from tests.test_upload_concurrency import (  # noqa: F401  (fixtures)
    api,
    api_main,
)

HOUR = 3600


class _FakeClock:
    """Replaces chroma_store.py's `time` import so its own time.time()
    calls are controllable, without touching the real time module used
    by anything else."""

    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def time(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = _FakeClock()
    monkeypatch.setattr(chroma_store_module, "time", fake)
    return fake


@pytest.fixture
def store(tmp_path) -> ChromaStore:
    return ChromaStore(persist_dir=str(tmp_path / "chroma"))


def _metadata(store: ChromaStore, session_id: str) -> dict:
    return store.client.get_collection(f"session_{session_id}").metadata


def _backdate(store: ChromaStore, session_id: str, **fields) -> None:
    """Directly rewrites a collection's metadata to simulate an aged
    session — exercises the same collection.modify() mechanism
    _touch_activity() relies on."""
    collection = store.client.get_collection(f"session_{session_id}")
    metadata = dict(collection.metadata or {})
    metadata.pop("hnsw:space", None)  # chromadb rejects modify() with this key present
    metadata.update(fields)
    collection.modify(metadata=metadata)


def _one_chunk(text: str = "hello world"):
    return [text], [[0.1, 0.2, 0.3]], [{"source": "notes.txt"}]


def _dummy_upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


# ── R5, AC1 ────────────────────────────────────────────────────────────

def test_new_collection_activity_equals_creation(store):
    store.get_or_create_collection("s1")
    meta = _metadata(store, "s1")
    assert meta["last_activity_at"] == meta["created_at"]


# ── R1, AC2 ────────────────────────────────────────────────────────────

def test_add_advances_last_activity(store, clock):
    clock.now = 0.0
    chunks, embeddings, metadatas = _one_chunk()
    store.add("s1", chunks, embeddings, metadatas)
    assert _metadata(store, "s1")["created_at"] == 0.0

    clock.now = 100.0
    chunks, embeddings, metadatas = _one_chunk("more text")
    store.add("s1", chunks, embeddings, metadatas)
    meta = _metadata(store, "s1")
    assert meta["created_at"] == 0.0
    assert meta["last_activity_at"] == 100.0


# ── R1, AC3 ────────────────────────────────────────────────────────────

def test_query_advances_last_activity(store, clock):
    clock.now = 0.0
    chunks, embeddings, metadatas = _one_chunk()
    store.add("s1", chunks, embeddings, metadatas)

    clock.now = 50.0
    store.query("s1", query_embedding=[0.1, 0.2, 0.3])
    meta = _metadata(store, "s1")
    assert meta["created_at"] == 0.0
    assert meta["last_activity_at"] == 50.0


# ── R2, AC4 ────────────────────────────────────────────────────────────

def test_idle_timeout_expires_despite_recent_creation(store):
    store.get_or_create_collection("s1")
    now = time.time()
    _backdate(store, "s1", created_at=now - 1 * HOUR, last_activity_at=now - 25 * HOUR)

    deleted = store.cleanup_expired(ttl_hours=24, max_lifetime_hours=1000)
    assert deleted == 1
    with pytest.raises(chromadb.errors.NotFoundError):
        store.client.get_collection("session_s1")


# ── R3, AC5 ────────────────────────────────────────────────────────────

def test_hard_cap_expires_despite_recent_activity(store):
    store.get_or_create_collection("s1")
    now = time.time()
    _backdate(store, "s1", created_at=now - 200 * HOUR, last_activity_at=now - 1 * HOUR)

    deleted = store.cleanup_expired(ttl_hours=1000, max_lifetime_hours=168)
    assert deleted == 1
    with pytest.raises(chromadb.errors.NotFoundError):
        store.client.get_collection("session_s1")


# ── R4, AC6 ────────────────────────────────────────────────────────────

def test_within_both_windows_survives_outside_both_deleted_once(store):
    now = time.time()
    store.get_or_create_collection("alive")
    _backdate(store, "alive", created_at=now - 1 * HOUR, last_activity_at=now - 1 * HOUR)
    store.get_or_create_collection("dead")
    _backdate(store, "dead", created_at=now - 200 * HOUR, last_activity_at=now - 200 * HOUR)

    deleted = store.cleanup_expired(ttl_hours=24, max_lifetime_hours=168)

    assert deleted == 1
    assert store.client.get_collection("session_alive") is not None
    with pytest.raises(chromadb.errors.NotFoundError):
        store.client.get_collection("session_dead")


# ── Legacy-metadata fallback (Constraints) ──────────────────────────────

def test_missing_last_activity_falls_back_to_created_at(store):
    store.get_or_create_collection("s1")
    now = time.time()
    # Simulate a collection stored before this change shipped: no
    # last_activity_at key at all.
    collection = store.client.get_collection("session_s1")
    collection.modify(metadata={"created_at": now - 25 * HOUR})

    deleted = store.cleanup_expired(ttl_hours=24, max_lifetime_hours=1000)
    assert deleted == 1


# ── R7, AC7 ──────────────────────────────────────────────────────────────

def test_validation_failure_does_not_touch_activity(api):
    import asyncio

    from fastapi import HTTPException

    # An invalid session_id fails _validate_client_session_id (400)
    # before /query ever calls into the pipeline/store.
    with pytest.raises(HTTPException):
        asyncio.run(
            api.query_document(api.QueryRequest(session_id="not-a-uuid", question="anything"))
        )
    with pytest.raises(chromadb.errors.NotFoundError):
        api.pipeline.chroma_store.client.get_collection("session_not-a-uuid")

    # Too many files fails before ingestion starts, so no collection is
    # ever created for the fresh session_id it would have used.
    with pytest.raises(HTTPException):
        asyncio.run(
            api.upload_documents(
                files=[
                    _dummy_upload(f"f{i}.txt", b"x")
                    for i in range(api.settings.max_files_per_upload + 1)
                ],
                session_id=None,
            )
        )
