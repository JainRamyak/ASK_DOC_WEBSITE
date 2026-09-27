"""
tests/test_error_responses.py

G13: /upload, /upload-url, and /query must never put raw exception text
(str(e), tracebacks, file paths, library names, env var names) in an
HTTP 500/503 response `detail`. /query must distinguish an LLM
configuration error (LLMConfigError, raised in answer_chain.py for a
missing/invalid API key, a missing provider SDK, or an unrecognized
LLM_PROVIDER) from any other unexpected exception: the former maps to
503 + CONFIG_ERROR_MESSAGE, the latter (on all three routes) maps to
500 + GENERIC_ERROR_MESSAGE. The server log must still capture the
original exception via the existing logger.exception(...) calls, which
this change does not touch. /feedback's existing safe 500 and every
pre-existing 400-status response are unaffected (spot-checked here).

Run with: pytest tests/test_error_responses.py -v

Key-free: reuses the stubbed-model fixtures from test_upload_concurrency
(no model is loaded, no network is used). Every exception in this file
is forced/stubbed; nothing here calls a real LLM or a real provider SDK.
The endpoint functions are called directly (no HTTP client), matching
the pattern already used by test_delete_session.py.
"""
import asyncio
import io
import logging
import uuid

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from src.generation.answer_chain import LLMConfigError
from tests.test_upload_concurrency import api_main, api, _seed_session  # noqa: F401


# ── AC1/AC2 (R1, R2, R3): /query ────────────────────────────────────────

def test_query_config_error_returns_503(api, monkeypatch):
    def _raise_config_error(*args, **kwargs):
        raise LLMConfigError("GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com")

    monkeypatch.setattr(api.pipeline, "ask", _raise_config_error)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.query_document(api.QueryRequest(session_id=str(uuid.uuid4()), question="x"))
        )

    assert (exc.value.status_code, exc.value.detail) == (503, api.CONFIG_ERROR_MESSAGE)


def test_query_generic_error_returns_500(api, monkeypatch):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api.pipeline, "ask", _raise_generic)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.query_document(api.QueryRequest(session_id=str(uuid.uuid4()), question="x"))
        )

    assert (exc.value.status_code, exc.value.detail) == (500, api.GENERIC_ERROR_MESSAGE)


# ── AC3/AC4 (R4): /upload, /upload-url ──────────────────────────────────

def test_upload_generic_error_returns_500(api, monkeypatch):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api.pipeline, "ingest_with_report", _raise_generic)

    upload = UploadFile(file=io.BytesIO(b"hello world"), filename="doc.txt")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.upload_documents(files=[upload], session_id=None))

    assert (exc.value.status_code, exc.value.detail) == (500, api.GENERIC_ERROR_MESSAGE)


def test_upload_url_generic_error_returns_500(api, monkeypatch):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api.pipeline, "ingest_url", _raise_generic)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.upload_url(api.UploadURLRequest(url="https://example.com")))

    assert (exc.value.status_code, exc.value.detail) == (500, api.GENERIC_ERROR_MESSAGE)


# ── AC5 (R5): logging still captures the original exception ────────────

def test_query_config_error_still_logs_original(api, monkeypatch, caplog):
    def _raise_config_error(*args, **kwargs):
        raise LLMConfigError("GEMINI_API_KEY is not set in .env")

    monkeypatch.setattr(api.pipeline, "ask", _raise_config_error)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException):
            asyncio.run(
                api.query_document(api.QueryRequest(session_id=str(uuid.uuid4()), question="x"))
            )

    assert "GEMINI_API_KEY is not set in .env" in caplog.text


def test_query_generic_error_still_logs_original(api, monkeypatch, caplog):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom-query-generic")

    monkeypatch.setattr(api.pipeline, "ask", _raise_generic)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException):
            asyncio.run(
                api.query_document(api.QueryRequest(session_id=str(uuid.uuid4()), question="x"))
            )

    assert "boom-query-generic" in caplog.text


def test_upload_error_still_logs_original(api, monkeypatch, caplog):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom-upload")

    monkeypatch.setattr(api.pipeline, "ingest_with_report", _raise_generic)

    upload = UploadFile(file=io.BytesIO(b"hello world"), filename="doc.txt")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException):
            asyncio.run(api.upload_documents(files=[upload], session_id=None))

    assert "boom-upload" in caplog.text


def test_upload_url_error_still_logs_original(api, monkeypatch, caplog):
    def _raise_generic(*args, **kwargs):
        raise RuntimeError("boom-upload-url")

    monkeypatch.setattr(api.pipeline, "ingest_url", _raise_generic)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException):
            asyncio.run(api.upload_url(api.UploadURLRequest(url="https://example.com")))

    assert "boom-upload-url" in caplog.text


# ── AC6/AC7 (R7): pre-existing responses unchanged (spot-check only —  ──
# ── full 400 coverage already lives in test_delete_session.py /       ──
# ── test_session_ttl.py)                                              ──

def test_existing_400s_unchanged_spot_check(api):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.query_document(api.QueryRequest(session_id="not-a-uuid", question="x")))
    assert (exc.value.status_code, exc.value.detail) == (400, "Invalid session_id.")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.upload_url(api.UploadURLRequest(url="")))
    assert (exc.value.status_code, exc.value.detail) == (400, "url is required")


def test_feedback_500_unchanged(api, monkeypatch):
    def _raise_oserror(*args, **kwargs):
        raise OSError("disk full")

    # Patches the module-global `open` that api/main.py's bare `open(...)`
    # call resolves to — scoped to this module only, reverted by monkeypatch.
    monkeypatch.setattr(api, "open", _raise_oserror, raising=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.submit_feedback(
                api.FeedbackRequest(
                    session_id=str(uuid.uuid4()), question="q", answer="a", helpful=True
                )
            )
        )

    assert (exc.value.status_code, exc.value.detail) == (500, "Could not record feedback")
