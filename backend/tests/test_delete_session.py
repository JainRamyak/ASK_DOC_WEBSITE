"""
tests/test_delete_session.py

G11: DELETE /sessions/{session_id} must reject a non-UUID session_id
before it ever reaches the store, exactly like /upload, /upload-url,
and /query already do via _validate_client_session_id.

Run with: pytest tests/test_delete_session.py -v

Key-free: reuses the stubbed-model fixtures from test_upload_concurrency.
The endpoint function is called directly (no HTTP client), which also
bypasses the rate limiter.
"""
import asyncio
import uuid

import pytest
from fastapi import HTTPException

from tests.test_upload_concurrency import api_main, api, _seed_session  # noqa: F401


def _reject_if_called(*args, **kwargs):
    raise AssertionError("chroma_store.delete_session must not be called")


@pytest.mark.parametrize(
    "session_id",
    [
        "not-a-uuid",
        "123",
        "abc%2Fdef",
        "x" * 250,
    ],
)
def test_invalid_format_rejected_before_store_call(api, monkeypatch, session_id):
    monkeypatch.setattr(api.pipeline.chroma_store, "delete_session", _reject_if_called)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.delete_session(session_id))

    assert (exc.value.status_code, exc.value.detail) == (400, "Invalid session_id.")


def test_wellformed_nonexistent_uuid_returns_success_false(api):
    session_id = str(uuid.uuid4())
    result = asyncio.run(api.delete_session(session_id))
    assert result == {"deleted": session_id, "success": False}


def test_wellformed_existing_uuid_deletes_and_returns_success_true(api):
    session_id = _seed_session(api)

    result = asyncio.run(api.delete_session(session_id))
    assert result == {"deleted": session_id, "success": True}
    assert api.pipeline.chroma_store.session_exists(session_id) is False

    # Deleting again is a no-op, not an error (unchanged behavior).
    result = asyncio.run(api.delete_session(session_id))
    assert result == {"deleted": session_id, "success": False}
