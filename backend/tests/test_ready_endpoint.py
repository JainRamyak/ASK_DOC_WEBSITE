"""
tests/test_ready_endpoint.py

G14: GET /ready reports whether the configured LLM_PROVIDER is usable
(key present, provider recognized, SDK importable) without ever making
a network/API call. /health must remain completely unaffected.

Run with: pytest tests/test_ready_endpoint.py -v

Key-free: reuses the stubbed-model fixtures from test_upload_concurrency
(no model is loaded, no network is used). The endpoint function is
called directly (no HTTP client), matching the pattern already used by
test_delete_session.py / test_error_responses.py.
"""
import json
import sys

from config import settings
from tests.test_upload_concurrency import api_main, api  # noqa: F401


def test_ready_true_when_configured(api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-test")

    result = api.ready()

    assert result == {"ready": True}


def test_ready_false_unknown_provider(api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "foo")

    result = api.ready()

    assert result.status_code == 503
    body = json.loads(result.body)
    assert body == {"ready": False, "reason": api.READY_ERROR_MESSAGE}
    assert "foo" not in body["reason"]


def test_ready_false_missing_key(api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")

    result = api.ready()

    assert result.status_code == 503
    assert json.loads(result.body) == {"ready": False, "reason": api.READY_ERROR_MESSAGE}


def test_ready_false_sdk_not_importable(api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-test")
    # A sys.modules entry of None makes the import system raise
    # ImportError for that module, regardless of whether the real
    # package is actually installed — no need to uninstall anything.
    monkeypatch.setitem(sys.modules, "anthropic", None)

    result = api.ready()

    assert result.status_code == 503
    assert json.loads(result.body) == {"ready": False, "reason": api.READY_ERROR_MESSAGE}


def test_health_still_static(api, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "foo")

    assert api.health() == {"status": "ok", "version": "2.2.0"}
