"""
tests/test_upload_skipped_files.py

G02 regression: /upload must report as indexed only the files that
contributed text, and name every other file in a `skipped` list with a
user-safe reason.

Run with: pytest tests/test_upload_skipped_files.py -v

Key-free: reuses the stubbed embedder/reranker fixtures from the G01 test
module, and calls the endpoint function directly.
"""
import asyncio
import os

import pytest
from fastapi import HTTPException

import src.pipeline as pipeline_module
from src.ingestion.chunker import chunk_documents
from src.ingestion.loader import load_documents
from tests.test_upload_concurrency import (  # noqa: F401  (fixtures + helpers)
    STAGING_ROOT,
    _collection,
    _expected_chunks,
    _staging_entries,
    _text,
    _upload,
    _upload_concurrently,
    _upload_one,
    api,
    api_main,
)

BLANK = b"   \n\t \n"
NOT_A_PDF = b"this is definitely not a pdf"


def _skipped_by_name(resp) -> dict:
    return {s["filename"]: s for s in resp["skipped"]}


def _stored_sources(api, session_id) -> list:
    metas = _collection(api, session_id).get()["metadatas"]
    return [m["source"] for m in metas]


# ── AC1, AC4 (R1, R2, R6) ────────────────────────────────────────────────

def test_skipped_file_not_reported_as_indexed(api):
    good = _text("good", 2)
    resp = _upload_one(api, None, [("good.txt", good.encode()), ("blank.txt", BLANK)])

    assert resp["filenames"] == ["good.txt"]
    assert [s["filename"] for s in resp["skipped"]] == ["blank.txt"]
    assert resp["chunks"] == _expected_chunks("good.txt", good)
    assert _collection(api, resp["session_id"]).count() == resp["chunks"]


def test_every_upload_is_in_exactly_one_list(api):
    files = [("a.txt", _text("a").encode()), ("b.txt", BLANK), ("c.md", _text("c").encode()),
             ("d.md", BLANK), ("broken.pdf", NOT_A_PDF)]
    resp = _upload_one(api, None, files)

    reported = resp["filenames"] + [s["filename"] for s in resp["skipped"]]
    assert sorted(reported) == sorted(n for n, _ in files)
    assert not set(resp["filenames"]) & {s["filename"] for s in resp["skipped"]}


# ── AC2 (R3) ─────────────────────────────────────────────────────────────

def test_reason_categories_and_safe_messages(api):
    resp = _upload_one(api, None, [("good.txt", _text("g").encode()),
                                   ("blank.txt", BLANK), ("broken.pdf", NOT_A_PDF)])
    skipped = _skipped_by_name(resp)

    assert resp["filenames"] == ["good.txt"]
    assert skipped["blank.txt"]["reason"] == "no_text"
    assert skipped["broken.pdf"]["reason"] == "unreadable"
    assert skipped["blank.txt"]["message"] != skipped["broken.pdf"]["message"]
    for s in skipped.values():
        for leak in ("Traceback", "/tmp", "rag_sessions", "Error", "Exception", ".py"):
            assert leak not in s["message"], (leak, s)


# ── AC3 (R4) ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("order", ["prose_first", "blank_first"])
def test_duplicate_names_are_attributed_correctly(api, order):
    prose = ("a.txt", _text("dup").encode())
    blank = ("a.txt", BLANK)
    resp = _upload_one(api, None, [prose, blank] if order == "prose_first" else [blank, prose])

    assert resp["filenames"] == ["a.txt"]
    assert [s["filename"] for s in resp["skipped"]] == ["a.txt"]
    assert resp["chunks"] == _expected_chunks("a.txt", _text("dup"))


def test_literal_name_matching_a_disambiguated_name_does_not_overwrite(api):
    """a.txt, a.txt, then a file literally named 'a (1).txt': the second
    upload is staged as 'a (1).txt' and must not be clobbered by the third."""
    one, two, three = _text("one"), _text("two"), _text("three")
    resp = _upload_one(api, None, [("a.txt", one.encode()), ("a.txt", two.encode()),
                                   ("a (1).txt", three.encode())])

    assert resp["filenames"] == ["a.txt", "a.txt", "a (1).txt"]
    assert resp["skipped"] == []
    assert resp["chunks"] == 3
    assert len(set(_stored_sources(api, resp["session_id"]))) == 3


# ── AC5, AC6, AC7 (R5, R7) ───────────────────────────────────────────────

def test_fully_readable_uploads_have_empty_skipped_list(api):
    first = _upload_one(api, None, [("a.txt", _text("a").encode())])
    second = _upload_one(api, first["session_id"], [("b.txt", _text("b").encode())])

    for resp, names in ((first, ["a.txt"]), (second, ["b.txt"])):
        assert resp["filenames"] == names
        assert resp["skipped"] == []
        assert resp["status"] == "ready"


def test_all_skipped_is_still_400_and_cleans_up_new_session(api):
    with pytest.raises(HTTPException) as exc:
        _upload_one(api, None, [("blank.txt", BLANK), ("broken.pdf", NOT_A_PDF)])
    assert exc.value.status_code == 400
    assert exc.value.detail == "No readable text was found in the uploaded file(s)."
    assert api.pipeline.chroma_store.client.list_collections() == []


def test_all_skipped_append_keeps_existing_session(api):
    seed = _upload_one(api, None, [("seed.txt", _text("seed").encode())])
    before = _collection(api, seed["session_id"]).count()

    with pytest.raises(HTTPException) as exc:
        _upload_one(api, seed["session_id"], [("blank.txt", BLANK)])
    assert exc.value.status_code == 400
    assert _collection(api, seed["session_id"]).count() == before


# ── AC8 (R9, R10) ────────────────────────────────────────────────────────

def test_concurrent_upload_with_a_blank_file_reports_correctly(api):
    sid = _upload_one(api, None, [("seed.txt", _text("seed").encode())])["session_id"]
    before = _collection(api, sid).count()
    requests = [
        [("x1.txt", _text("x1").encode())],
        [("x2.txt", _text("x2").encode()), ("blank.txt", BLANK)],
        [("x3.txt", _text("x3").encode())],
        [("x4.txt", _text("x4").encode())],
    ]
    results = _upload_concurrently(api, sid, requests)

    for files, r in zip(requests, results):
        assert isinstance(r, dict), r
        expected_ok = [n for n, d in files if d != BLANK]
        assert r["filenames"] == expected_ok
        assert [s["filename"] for s in r["skipped"]] == [n for n, d in files if d == BLANK]
        assert r["chunks"] == len(expected_ok)
    assert _collection(api, sid).count() == before + 4


# ── AC9 (R11) ────────────────────────────────────────────────────────────

def test_upload_url_response_is_unchanged(api, monkeypatch):
    monkeypatch.setattr(api.pipeline, "ingest_url", lambda url, session_id="default": 3)
    resp = asyncio.run(api.upload_url(api.UploadURLRequest(url=" https://example.com/x ")))
    assert set(resp) == {"session_id", "filenames", "chunks", "status"}
    assert resp["filenames"] == ["https://example.com/x"] and resp["chunks"] == 3


# ── Caller contracts ─────────────────────────────────────────────────────

def test_ingest_still_returns_an_int(api, tmp_path):
    (tmp_path / "a.txt").write_text(_text("a"))
    (tmp_path / "blank.txt").write_text("  \n")
    assert api.pipeline.ingest(str(tmp_path), session_id="contract-check") == 1


def test_load_documents_result_is_a_plain_list_of_dicts(tmp_path):
    (tmp_path / "a.txt").write_text("hello world")
    docs = load_documents(str(tmp_path))
    assert isinstance(docs, list)
    assert docs and all("text" in d and "source" in d for d in docs)


@pytest.mark.parametrize("text", ["x", "hello world", "a" * 5000, "line\n\nline " * 300])
def test_non_empty_text_always_yields_a_chunk(text):
    """Spec A2: a file the loader returns text for contributes >=1 chunk."""
    assert len(chunk_documents([{"text": text, "source": "f.txt"}])) >= 1
