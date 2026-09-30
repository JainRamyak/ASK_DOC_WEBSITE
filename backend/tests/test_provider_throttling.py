"""
tests/test_provider_throttling.py

G29: a provider 429 on the answer call must reach /query clients as
HTTP 429 + RATE_LIMIT_ERROR_MESSAGE, and a provider 503/529 as HTTP 503 +
BUSY_ERROR_MESSAGE — never as the generic 500, never with raw exception
text, and with no retry. Any other status, or an unclassifiable error,
keeps the generic 500; LLMConfigError keeps its config 503.

Run with: pytest tests/test_provider_throttling.py -v

Key-free: no real SDK call is made. The provider SDKs' exceptions are
stood in for by FakeProviderError carrying the same status attribute the
real ones expose (`status_code` for mistral/openai/anthropic, `code` for
google-genai). That attribute naming is an ASSUMPTION about the pinned
SDKs (none is installed where these tests were written) — see
docs/specs/G29.md § Unknowns. The real `answer()` dispatch runs; only the
`_answer_<provider>` function is replaced.
"""
import asyncio
import logging
import uuid

import pytest
from fastapi import HTTPException

from config import settings
from src.generation import answer_chain
from src.generation.answer_chain import LLMConfigError, answer
from tests.test_upload_concurrency import api_main, api  # noqa: F401

RAW = "SECRET-RAW-TEXT key=abc123"
CHUNKS = [{"text": "t", "source": "s.txt", "score": 1.0}]

# provider -> attribute its SDK error carries the HTTP status in (assumed)
PROVIDERS = [
    ("gemini", "code"),
    ("mistral", "status_code"),
    ("openai", "status_code"),
    ("anthropic", "status_code"),
]


class FakeProviderError(Exception):
    def __init__(self, attr=None, value=None):
        super().__init__(RAW)
        if attr:
            setattr(self, attr, value)


def _wire(api, monkeypatch, provider, exc):
    """/query -> real answer() dispatch -> provider function raising exc.
    Returns a call counter for the provider function."""
    calls = []

    def _provider_fn(*args, **kwargs):
        calls.append(1)
        raise exc

    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(answer_chain, f"_answer_{provider}", _provider_fn)
    monkeypatch.setattr(api.pipeline, "ask", lambda *a, **k: answer("q", CHUNKS))
    return calls


def _query(api):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.query_document(api.QueryRequest(session_id=str(uuid.uuid4()), question="x"))
        )
    return exc.value


# ── AC1, AC3 (R1, R4): 429 for every provider ──────────────────────────

@pytest.mark.parametrize("provider,attr", PROVIDERS)
def test_429_maps_to_429(api, monkeypatch, provider, attr):
    _wire(api, monkeypatch, provider, FakeProviderError(attr, 429))
    e = _query(api)
    assert (e.status_code, e.detail) == (429, api.RATE_LIMIT_ERROR_MESSAGE)
    assert "SECRET" not in str(e.detail)


# ── AC2, AC3 (R1, R4): 503 and 529 for every provider ──────────────────

@pytest.mark.parametrize("status", [503, 529])
@pytest.mark.parametrize("provider,attr", PROVIDERS)
def test_503_and_529_map_to_503_busy(api, monkeypatch, provider, attr, status):
    _wire(api, monkeypatch, provider, FakeProviderError(attr, status))
    e = _query(api)
    assert (e.status_code, e.detail) == (503, api.BUSY_ERROR_MESSAGE)
    assert api.BUSY_ERROR_MESSAGE != api.CONFIG_ERROR_MESSAGE
    assert "SECRET" not in str(e.detail)


def test_status_attribute_precedence(api, monkeypatch):
    """`status_code` wins over `code` when both exist."""
    exc = FakeProviderError("status_code", 429)
    exc.code = 500
    _wire(api, monkeypatch, "openai", exc)
    assert _query(api).status_code == 429


# ── AC2 negative: anything else stays the generic 500 ───────────────────

@pytest.mark.parametrize(
    "attr,value",
    [
        ("status_code", 500),
        ("status_code", 401),
        ("status_code", 404),
        ("status_code", "429"),   # str, not int
        ("status_code", True),    # bool is not a status
        ("code", None),
        (None, None),             # no status attribute at all
    ],
)
def test_unclassified_errors_stay_generic_500(api, monkeypatch, attr, value):
    _wire(api, monkeypatch, "mistral", FakeProviderError(attr, value))
    e = _query(api)
    assert (e.status_code, e.detail) == (500, api.GENERIC_ERROR_MESSAGE)


# ── AC4 (R5): config errors are not reclassified ────────────────────────

def test_config_error_still_503_config_message(api, monkeypatch):
    _wire(api, monkeypatch, "gemini", LLMConfigError("GEMINI_API_KEY is not set"))
    e = _query(api)
    assert (e.status_code, e.detail) == (503, api.CONFIG_ERROR_MESSAGE)


# ── AC5 (R3): raw error still reaches the server log ───────────────────

@pytest.mark.parametrize("status", [429, 503])
def test_raw_error_still_logged(api, monkeypatch, caplog, status):
    _wire(api, monkeypatch, "gemini", FakeProviderError("code", status))
    with caplog.at_level(logging.ERROR):
        _query(api)
    assert "SECRET-RAW-TEXT" in caplog.text


# ── AC7 (R7): no retry ──────────────────────────────────────────────────

@pytest.mark.parametrize("status", [429, 503])
def test_provider_called_exactly_once(api, monkeypatch, status):
    calls = _wire(api, monkeypatch, "gemini", FakeProviderError("code", status))
    _query(api)
    assert len(calls) == 1


# ── AC3: real SDK exception classes (skipped where the SDK is absent) ──
# Confirms the status attribute assumption above against the installed
# SDK versions; construction is offline (an httpx.Response, no request).

def _http_response(code):
    httpx = pytest.importorskip("httpx")
    return httpx.Response(code, request=httpx.Request("POST", "https://x"), json={"error": {"message": RAW}})


def _real_error(provider, status):
    if provider == "gemini":
        errors = pytest.importorskip("google.genai.errors")
        cls = errors.ClientError if status < 500 else errors.ServerError
        return cls(status, {"error": {"code": status, "status": "S", "message": RAW}})
    if provider == "openai":
        openai = pytest.importorskip("openai")
        return openai.APIStatusError(RAW, response=_http_response(status), body=None)
    if provider == "anthropic":
        anthropic = pytest.importorskip("anthropic")
        return anthropic.APIStatusError(RAW, response=_http_response(status), body=None)
    sdk_errors = pytest.importorskip("mistralai.client.errors")
    return sdk_errors.SDKError(RAW, _http_response(status))


@pytest.mark.parametrize("status,expected", [(429, 429), (503, 503)])
@pytest.mark.parametrize("provider", [p for p, _ in PROVIDERS])
def test_real_sdk_exceptions_are_classified(api, monkeypatch, provider, status, expected):
    _wire(api, monkeypatch, provider, _real_error(provider, status))
    e = _query(api)
    assert e.status_code == expected
    assert "SECRET" not in str(e.detail)


def test_real_anthropic_529_is_classified(api, monkeypatch):
    _wire(api, monkeypatch, "anthropic", _real_error("anthropic", 529))
    e = _query(api)
    assert (e.status_code, e.detail) == (503, api.BUSY_ERROR_MESSAGE)
