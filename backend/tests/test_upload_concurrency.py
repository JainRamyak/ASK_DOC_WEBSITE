"""
tests/test_upload_concurrency.py

G01 regression: overlapping /upload requests to the same session must each
index only their own files, exactly once, and report an exact chunk count.

Run with: pytest tests/test_upload_concurrency.py -v

Key-free: the embedder and reranker are stubbed, so no model is loaded and
no network is used. The endpoint function is called directly (no HTTP
client), which also bypasses the rate limiter.
"""
import asyncio
import hashlib
import io
import os
import shutil
import threading

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

import src.pipeline as pipeline_module
from config import settings
from embedder.base import BaseEmbedder
from src.ingestion.chunker import chunk_documents

STAGING_ROOT = "/tmp/rag_sessions"
GATE_TIMEOUT = 2.0


class _StubEmbedder(BaseEmbedder):
    @property
    def dimension(self) -> int:
        return 8

    def embed_text(self, text):
        return [b / 255 for b in hashlib.sha256(text.encode()).digest()[:8]]

    def embed_batch(self, texts):
        return [self.embed_text(t) for t in texts]


class _StubReranker:
    def __init__(self, *args, **kwargs):
        pass


def _stub_models(monkeypatch):
    monkeypatch.setattr(pipeline_module, "get_embedder", lambda: _StubEmbedder())
    monkeypatch.setattr(pipeline_module, "Reranker", _StubReranker)


@pytest.fixture(scope="module")
def api_main(tmp_path_factory):
    """Import api.main once with the heavy models stubbed — it builds an
    AskMyDocsPipeline at import time."""
    mp = pytest.MonkeyPatch()
    _stub_models(mp)
    mp.setattr(settings, "chroma_persist_dir", str(tmp_path_factory.mktemp("chroma_import")))
    import api.main as module
    mp.undo()
    return module


@pytest.fixture
def api(api_main, monkeypatch, tmp_path):
    """api.main with a fresh, isolated pipeline (own Chroma dir) per test."""
    _stub_models(monkeypatch)
    monkeypatch.setattr(settings, "chroma_persist_dir", str(tmp_path / "chroma"))
    monkeypatch.setattr(api_main, "pipeline", pipeline_module.AskMyDocsPipeline())
    return api_main


# ── helpers ──────────────────────────────────────────────────────────────

def _text(tag: str, paragraphs: int = 1) -> str:
    """Each ~420-char paragraph becomes its own chunk (chunk_size 512)."""
    return "\n\n".join(f"{tag} paragraph {i} " + "x" * 400 for i in range(paragraphs))


def _expected_chunks(name: str, text: str) -> int:
    return len(chunk_documents([{"text": text.strip(), "source": name}]))


async def _upload(api, session_id, files):
    uploads = [UploadFile(file=io.BytesIO(data), filename=name) for name, data in files]
    return await api.upload_documents(files=uploads, session_id=session_id)


def _upload_one(api, session_id, files):
    return asyncio.run(_upload(api, session_id, files))


def _upload_concurrently(api, session_id, file_lists):
    async def run():
        return await asyncio.gather(
            *[_upload(api, session_id, files) for files in file_lists],
            return_exceptions=True,
        )
    return asyncio.run(run())


def _install_gate(monkeypatch, parties, on_all_staged=None, hold=None):
    """Make the first `parties` calls to load_documents wait for each other
    (bounded), so every request has staged its files before any scans a
    directory. Mechanism-agnostic: if the implementation serialises ingest,
    the barrier times out instead of deadlocking."""
    real = pipeline_module.load_documents
    barrier = threading.Barrier(parties, action=on_all_staged, timeout=GATE_TIMEOUT)

    def gated(directory):
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
        if hold is not None:
            hold.wait(GATE_TIMEOUT)
        return real(directory)

    monkeypatch.setattr(pipeline_module, "load_documents", gated)


def _seed_session(api) -> str:
    return _upload_one(api, None, [("seed.txt", _text("seed").encode())])["session_id"]


def _collection(api, session_id):
    return api.pipeline.chroma_store.get_or_create_collection(session_id)


def _staging_entries() -> set:
    return set(os.listdir(STAGING_ROOT)) if os.path.isdir(STAGING_ROOT) else set()


# ── AC1 (R1, R2, R3) ─────────────────────────────────────────────────────

def test_concurrent_uploads_index_each_file_once(api, monkeypatch):
    sid = _seed_session(api)
    before = _collection(api, sid).count()
    files = [(f"c{i}.txt", _text(f"c{i}").encode()) for i in range(4)]

    _install_gate(monkeypatch, parties=len(files))
    results = _upload_concurrently(api, sid, [[f] for f in files])

    for r in results:
        assert isinstance(r, dict), r
        assert r["chunks"] == 1
    got = _collection(api, sid).get(include=["metadatas"])
    assert len(got["ids"]) == before + len(files)
    sources = [m["source"] for m in got["metadatas"]]
    for name, _ in files:
        assert sources.count(name) == 1


# ── AC2 (R3) ─────────────────────────────────────────────────────────────

def test_concurrent_uploads_report_each_files_own_chunk_count(api, monkeypatch):
    sid = _seed_session(api)
    before = _collection(api, sid).count()
    files = [(f"m{n}.txt", _text(f"m{n}", paragraphs=n)) for n in (1, 2, 3)]
    expected = [_expected_chunks(name, text) for name, text in files]
    assert len(set(expected)) == 3  # precondition: the files really differ in size

    _install_gate(monkeypatch, parties=len(files))
    results = _upload_concurrently(api, sid, [[(n, t.encode())] for n, t in files])

    for r, want in zip(results, expected):
        assert isinstance(r, dict), r
        assert r["chunks"] == want
    assert _collection(api, sid).count() == before + sum(expected)


# ── AC3 (R4) ─────────────────────────────────────────────────────────────

def test_failing_request_does_not_disturb_in_flight_requests(api, monkeypatch):
    sid = _seed_session(api)
    before = _collection(api, sid).count()
    good = [(f"g{i}.txt", _text(f"g{i}").encode()) for i in range(2)]
    staged = threading.Event()
    failer_done = threading.Event()

    _install_gate(monkeypatch, parties=len(good), on_all_staged=staged.set, hold=failer_done)

    async def failing_request():
        # Fire only once the good requests have staged, then fail validation.
        await asyncio.to_thread(staged.wait, GATE_TIMEOUT)
        try:
            return await _upload(api, sid, [("bad.exe", b"not allowed")])
        except HTTPException as e:
            return e
        finally:
            failer_done.set()

    async def run():
        return await asyncio.gather(
            *[_upload(api, sid, [f]) for f in good],
            failing_request(),
            return_exceptions=True,
        )

    *good_results, bad_result = asyncio.run(run())

    assert isinstance(bad_result, HTTPException) and bad_result.status_code == 400
    for r in good_results:
        assert isinstance(r, dict), r
        assert r["chunks"] == 1
    assert _collection(api, sid).count() == before + len(good)


# ── AC4 (R5) ─────────────────────────────────────────────────────────────

def test_same_filename_in_overlapping_requests_are_both_indexed(api, monkeypatch):
    sid = _seed_session(api)
    before = _collection(api, sid).count()
    a = ("notes.txt", ("ALPHA-MARKER " + _text("a")).encode())
    b = ("notes.txt", ("BRAVO-MARKER " + _text("b")).encode())

    _install_gate(monkeypatch, parties=2)
    results = _upload_concurrently(api, sid, [[a], [b]])

    for r in results:
        assert isinstance(r, dict), r
        assert r["chunks"] == 1
    docs = _collection(api, sid).get(include=["documents"])["documents"]
    assert len(docs) == before + 2
    assert any("ALPHA-MARKER" in d for d in docs)
    assert any("BRAVO-MARKER" in d for d in docs)


# ── AC5 (R6) ─────────────────────────────────────────────────────────────

def test_stray_file_left_in_staging_is_not_ingested(api, monkeypatch):
    sid = _seed_session(api)
    stray_dir = os.path.join(STAGING_ROOT, sid)
    os.makedirs(stray_dir, exist_ok=True)
    with open(os.path.join(stray_dir, "stray.txt"), "w") as f:
        f.write("STRAY-MARKER left behind by a crashed request")
    try:
        result = _upload_one(api, sid, [("up.txt", _text("up").encode())])
    finally:
        shutil.rmtree(stray_dir, ignore_errors=True)

    assert result["chunks"] == 1
    docs = _collection(api, sid).get(include=["documents"])["documents"]
    assert not any("STRAY-MARKER" in d for d in docs)


# ── AC7 (R4) ─────────────────────────────────────────────────────────────

def test_no_staging_data_left_after_success_and_failures(api):
    sid = _seed_session(api)
    before = _staging_entries()

    _upload_one(api, sid, [("ok.txt", _text("ok").encode())])
    with pytest.raises(HTTPException):
        _upload_one(api, sid, [("bad.exe", b"x")])
    with pytest.raises(HTTPException):
        _upload_one(api, sid, [("blank.txt", b"   \n")])

    assert _staging_entries() - before == set()


# ── AC6 (R7): behaviour that must not change ─────────────────────────────

def test_sequential_new_and_append_response_contract(api):
    a_text, b_text = _text("a", 2), _text("b")
    first = _upload_one(api, None, [("a.txt", a_text.encode())])
    assert set(first) == {"session_id", "filenames", "skipped", "chunks", "status"}
    assert first["skipped"] == []
    assert first["filenames"] == ["a.txt"]
    assert first["status"] == "ready"
    assert first["chunks"] == _expected_chunks("a.txt", a_text)

    second = _upload_one(api, first["session_id"], [("b.txt", b_text.encode())])
    assert second["session_id"] == first["session_id"]
    assert second["filenames"] == ["b.txt"]
    assert second["chunks"] == _expected_chunks("b.txt", b_text)
    assert _collection(api, first["session_id"]).count() == first["chunks"] + second["chunks"]


def test_error_paths_unchanged(api, monkeypatch):
    def status_and_detail(session_id, files):
        with pytest.raises(HTTPException) as exc:
            _upload_one(api, session_id, files)
        return exc.value.status_code, exc.value.detail

    code, detail = status_and_detail("not-a-uuid", [("a.txt", b"hello")])
    assert (code, detail) == (400, "Invalid session_id.")

    code, detail = status_and_detail(None, [("a.exe", b"hello")])
    assert code == 400 and "not supported" in detail

    code, detail = status_and_detail(None, [("blank.txt", b"   \n")])
    assert code == 400 and "No readable text" in detail
    assert api.pipeline.chroma_store.client.list_collections() == []  # no orphan session

    monkeypatch.setattr(settings, "max_files_per_upload", 1)
    code, detail = status_and_detail(None, [("a.txt", b"hello"), ("b.txt", b"hello")])
    assert code == 400 and detail.startswith("Too many files")
