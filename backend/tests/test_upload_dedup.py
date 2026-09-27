"""
tests/test_upload_dedup.py

G27 regression: re-uploading content whose SHA-256 hash is already indexed
in a session must not create a second copy of its chunks. Identity is the
raw file bytes (or, for /upload-url, the fetched/extracted text), scoped
per session. A repeat is reported via the additive `already_indexed`
field — never merged into `filenames` or G02's `skipped`.

Run with: pytest tests/test_upload_dedup.py -v

Key-free: reuses the stubbed embedder/reranker fixtures from the G01 test
module, and calls the endpoint function directly.
"""
import asyncio
import hashlib

import pytest

import src.pipeline as pipeline_module
from tests.test_upload_concurrency import (  # noqa: F401  (fixtures + helpers)
    _collection,
    _expected_chunks,
    _install_gate,
    _text,
    _upload,
    _upload_concurrently,
    _upload_one,
    api,
    api_main,
)

BLANK = b"   \n\t \n"


def _already_indexed_by_name(resp) -> dict:
    return {a["filename"]: a for a in resp["already_indexed"]}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── AC1 (R1, R2, R3) ─────────────────────────────────────────────────────

def test_identical_reupload_is_skipped(api):
    good = _text("good", 2).encode()
    first = _upload_one(api, None, [("notes.txt", good)])
    assert first["filenames"] == ["notes.txt"]
    assert first["already_indexed"] == []
    first_chunks = first["chunks"]
    assert first_chunks > 0

    sid = first["session_id"]
    second = _upload_one(api, sid, [("notes.txt", good)])

    assert second["filenames"] == []
    assert second["chunks"] == 0
    already = _already_indexed_by_name(second)
    assert set(already) == {"notes.txt"}
    assert already["notes.txt"]["hash"] == _sha256(good)
    assert _collection(api, sid).count() == first_chunks


# ── AC2 (R1, R2) ─────────────────────────────────────────────────────────

def test_rename_is_still_a_repeat(api):
    data = _text("dup").encode()
    first = _upload_one(api, None, [("original.txt", data)])
    sid = first["session_id"]

    second = _upload_one(api, sid, [("renamed_copy.txt", data)])

    assert second["filenames"] == []
    already = _already_indexed_by_name(second)
    assert set(already) == {"renamed_copy.txt"}
    assert already["renamed_copy.txt"]["hash"] == _sha256(data)
    assert _collection(api, sid).count() == first["chunks"]


# ── AC3 (R7) ─────────────────────────────────────────────────────────────

def test_same_name_different_content_indexes_both(api):
    v1 = ("ALPHA-MARKER " + _text("v1")).encode()
    v2 = ("BRAVO-MARKER " + _text("v2")).encode()
    first = _upload_one(api, None, [("notes.txt", v1)])
    sid = first["session_id"]

    second = _upload_one(api, sid, [("notes.txt", v2)])

    assert second["filenames"] == ["notes.txt"]
    assert second["already_indexed"] == []
    assert second["chunks"] > 0
    docs = _collection(api, sid).get(include=["documents"])["documents"]
    assert any("ALPHA-MARKER" in d for d in docs)
    assert any("BRAVO-MARKER" in d for d in docs)
    assert _collection(api, sid).count() == first["chunks"] + second["chunks"]


# ── Edge case: within-batch duplicates (same name, and different name) ───

def test_duplicate_within_one_batch_same_name(api):
    data = _text("batch").encode()
    resp = _upload_one(api, None, [("a.txt", data), ("a.txt", data)])

    assert resp["filenames"] == ["a.txt"]
    already = _already_indexed_by_name(resp)
    assert set(already) == {"a.txt"}  # the second "a.txt" (disambiguated on disk)
    assert resp["chunks"] > 0
    assert _collection(api, resp["session_id"]).count() == resp["chunks"]


def test_duplicate_within_one_batch_different_name(api):
    data = _text("batch2").encode()
    resp = _upload_one(api, None, [("first.txt", data), ("second.txt", data)])

    assert resp["filenames"] == ["first.txt"]
    already = _already_indexed_by_name(resp)
    assert set(already) == {"second.txt"}
    assert already["second.txt"]["hash"] == _sha256(data)
    assert _collection(api, resp["session_id"]).count() == resp["chunks"]


# ── AC4 (R3) ─────────────────────────────────────────────────────────────

def test_mixed_batch_partitions_correctly(api):
    existing = _upload_one(api, None, [("old.txt", _text("old").encode())])
    sid = existing["session_id"]

    new_data = _text("new").encode()
    resp = _upload_one(
        api,
        sid,
        [
            ("new.txt", new_data),
            ("old.txt", _text("old").encode()),  # exact repeat of the seed file
            ("blank.txt", BLANK),  # G02 skip case
        ],
    )

    assert resp["filenames"] == ["new.txt"]
    assert [s["filename"] for s in resp["skipped"]] == ["blank.txt"]
    already = _already_indexed_by_name(resp)
    assert set(already) == {"old.txt"}

    reported = resp["filenames"] + [s["filename"] for s in resp["skipped"]] + list(already)
    assert sorted(reported) == ["blank.txt", "new.txt", "old.txt"]
    assert not (set(resp["filenames"]) & set(already))
    assert not (set(resp["filenames"]) & {s["filename"] for s in resp["skipped"]})


# ── AC5, R6 ──────────────────────────────────────────────────────────────

def test_concurrent_identical_reupload(api, monkeypatch):
    data = _text("race", 2).encode()
    seed = _upload_one(api, None, [("seed.txt", _text("seed").encode())])
    sid = seed["session_id"]
    before = _collection(api, sid).count()

    _install_gate(monkeypatch, parties=2)
    results = _upload_concurrently(api, sid, [[("race.txt", data)], [("race.txt", data)]])

    for r in results:
        assert isinstance(r, dict), r

    total_new = sum(r["chunks"] for r in results)
    expected = _expected_chunks("race.txt", data.decode())
    # Exactly one of the two requests must have won the race — its
    # content is indexed exactly once, never twice, never zero times.
    assert total_new == expected
    assert _collection(api, sid).count() == before + expected
    winners = [r for r in results if r["filenames"] == ["race.txt"]]
    losers = [r for r in results if r["already_indexed"]]
    assert len(winners) == 1
    assert len(losers) == 1


# ── AC6, R5 ──────────────────────────────────────────────────────────────

def test_same_content_different_sessions_both_index(api):
    data = _text("shared").encode()
    first = _upload_one(api, None, [("shared.txt", data)])
    second = _upload_one(api, None, [("shared.txt", data)])  # no session_id -> new session

    assert first["session_id"] != second["session_id"]
    assert first["filenames"] == ["shared.txt"]
    assert second["filenames"] == ["shared.txt"]
    assert first["already_indexed"] == []
    assert second["already_indexed"] == []


# ── AC8, R4 ──────────────────────────────────────────────────────────────

def test_upload_url_repeat(api, monkeypatch):
    text = "some fixed page content " * 30
    monkeypatch.setattr(
        pipeline_module, "load_url", lambda url: [{"text": text, "source": url}]
    )

    url = "https://example.com/page"
    first = asyncio.run(api.upload_url(api.UploadURLRequest(url=url)))
    assert first["filenames"] == [url]
    assert first["already_indexed"] == []
    assert first["chunks"] > 0

    sid = first["session_id"]
    second = asyncio.run(api.upload_url(api.UploadURLRequest(url=url, session_id=sid)))

    assert second["filenames"] == []
    assert second["chunks"] == 0
    already = _already_indexed_by_name(second)
    assert set(already) == {url}
    assert already[url]["hash"] == _sha256(text.encode("utf-8"))
    assert _collection(api, sid).count() == first["chunks"]
