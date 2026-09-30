## Summary

A provider rate-limit (429) or overload (503) on the answer call reached `/query` clients as the same generic `500 "Something went wrong…"` used for real bugs, with no way to tell "provider is busy" from "app is broken". Free-tier Gemini (5 requests/min) makes this reachable in normal use.

Per owner decision (`docs/DECISIONS.md`, 2026-09-30, Option 1): distinct status and fixed message, **no retry**.
- provider status 429 → HTTP 429, "The assistant is receiving too many requests right now. Please wait a moment and try again."
- provider status 503 or 529 (Anthropic overloaded) → HTTP 503, "The assistant is busy right now. Please try again in a moment." (different text from the G13 config-error 503)
- everything else unchanged: other errors stay the G13 generic 500, `LLMConfigError` stays its 503.

Implements `docs/specs/G29.md` (`Status: APPROVED`). Raw provider text still goes only to server logs (G13 preserved).

## Change
- `backend/src/generation/answer_chain.py` — `LLMRateLimitError`, `LLMOverloadedError`, duck-typed `_provider_status` (int `status_code`, else `code`; bool/str ignored), and a try/except around the provider dispatch in `answer()`. `rewrite_query` and the embedder are untouched.
- `backend/api/main.py` — two message constants and two `except` branches in `query_document`.
- `backend/tests/test_provider_throttling.py` — new, 34 key-free tests.

Not touched: `frontend/` (it already shows `detail` verbatim), `config.py`, `.env.example`, deploy files, CI.

## Validation evidence (`docs/implementation/G29-validation.md`)
- Before/after with **real SDK exception objects** built offline (google-genai, openai, anthropic) through `query_document`: generic 500 before; 429/503 with the fixed messages after.
- New tests: 13 failed on the unchanged code → 34 passed after.
- Regression: CI command 32 passed; G13 tests 10 passed; full backend suite excluding key-requiring `test_pipeline.py` 148 passed.
- AC1–AC9 VERIFIED (AC3 against mistralai 2.9.4 only).

## Not verified / for the reviewer
- mistralai **2.4.2** (pinned in `requirements.prod.txt`, the Docker image) not tested, only 2.9.4; if its attribute differs the result is today's generic 500.
- No live provider call (would spend quota). No browser check of the new messages (frontend unchanged; reading shows `detail` is displayed as-is).
- No backend lint command exists in the repo.
- The two message strings are owner-approved wording; say if you want different text.
