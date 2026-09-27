# Implementation Plan: G13 — raw exception text returned to clients in HTTP 500 details

Session: PLAN-G13-2026-09-27 · Branch `fix/G13-hide-raw-exception-detail` (base `main` @ `b929908`, confirmed equal to `origin/main` via `git fetch`) · Spec `docs/specs/G13.md` (APPROVED)

## Implementation outcome (IMPL-G13-2026-09-27)
Implemented exactly as designed below — no plan row required revision. All 10 new tests in `backend/tests/test_error_responses.py` pass, plus 70 existing regression tests across `test_embedder.py`, `test_web_loader.py`, `test_delete_session.py`, `test_session_ttl.py`, `test_upload_concurrency.py`, `test_upload_dedup.py`, and `test_upload_skipped_files.py` (80 total), and the CI command in isolation (`test_embedder.py` + `test_web_loader.py`, 32 passed). `backend/tests/test_pipeline.py` was not run (needs an LLM key; CLAUDE.md). Diff confirmed scoped to exactly the 3 planned files (`git status --short backend/ frontend/ .github/`): `backend/api/main.py`, `backend/src/generation/answer_chain.py` (both modified), `backend/tests/test_error_responses.py` (new) — no `frontend/` or CI workflow file touched.

## Context
`docs/specs/G13.md` is APPROVED. `/upload`, `/upload-url`, and `/query` in `backend/api/main.py` currently put the raw Python exception (`str(e)`) into the HTTP `detail` field on any unexpected server error, and the frontend displays `detail` verbatim — so operator-facing internals (e.g. `"GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com"`) reach end users. Owner-approved decision (`docs/DECISIONS.md`): `/query` config errors (missing/invalid LLM key, missing SDK, unrecognized `LLM_PROVIDER`) map to a fixed `503`; every other unexpected exception on all three routes maps to one shared fixed `500` message. Server-side `logger.exception(...)` calls are untouched — only the client-visible `detail` changes.

## Design

### 1. Classification mechanism
Add one new exception class, `LLMConfigError(Exception)`, in `backend/src/generation/answer_chain.py`, and change its 9 existing `EnvironmentError`/`ImportError`/unknown-provider-`ValueError` raise sites to raise it instead. This matches the repo's existing convention (flat, undecorated `class XError(Exception)` defined in the raising module, imported narrowly into `main.py` — already done for `URLValidationError`/`FileValidationError`), keeps classification at the source instead of a fragile message-prefix check in `main.py`, and is a small, uniform, additive change (same swap across all 4 providers, no provider-specific logic touched). Confirmed safe: no test references these builtin exception types from `answer_chain.py` (`test_pipeline.py` only imports `NOT_FOUND_MESSAGE`).

### 2. `backend/src/generation/answer_chain.py`
Add near the top (after `logger = logging.getLogger(__name__)`):
```python
class LLMConfigError(Exception):
    """Raised for any LLM provider misconfiguration (missing/invalid API
    key, missing SDK, unrecognized LLM_PROVIDER). Caught by /query in
    api/main.py and mapped to a 503 — never shown to the client
    verbatim."""
```
Change these 9 raise sites from `ValueError`/`ImportError`/`EnvironmentError` to `LLMConfigError`, keeping existing message text unchanged (only reaches logs now):
- Unknown-provider `ValueError` inside `answer()` (~line 76-79)
- gemini `ImportError`/`EnvironmentError` (~89, 92-94)
- mistral `ImportError`/`EnvironmentError` (~122, 125-127)
- openai `ImportError`/`EnvironmentError` (~148, 151)
- anthropic `ImportError`/`EnvironmentError` (~172, 175-177)

Not touched: the unrelated `ValueError` in `_call_llm_plain` (~line 296, used by `rewrite_query`) — `rewrite_query` already catches its own exceptions internally and never propagates to `/query`'s try block.

### 3. `backend/api/main.py`
- Import: `from src.generation.answer_chain import LLMConfigError`, grouped with the other narrow route-exception imports.
- Two module-level constants near `SKIP_MESSAGES`:
  ```python
  # Fixed, safe strings for unexpected-exception responses — never
  # str(e). Shared verbatim across routes per docs/DECISIONS.md (G13).
  GENERIC_ERROR_MESSAGE = "Something went wrong while processing your request. Please try again."
  CONFIG_ERROR_MESSAGE = "The assistant is temporarily unavailable. Please try again later."
  ```
- `/upload` (~192-196) and `/upload-url` (~256-259): `except Exception as e:` → `except Exception:` (the `e` binding is dropped only because nothing else in the block references it once the f-string is gone — necessary consequence of R4, not a drive-by cleanup); `detail=f"Ingestion failed: {e}"` → `detail=GENERIC_ERROR_MESSAGE`. `except URLValidationError as e:` in `/upload-url` is untouched.
- `/query` (~299-301): split into two branches (subclass first):
  ```python
  except LLMConfigError:
      logger.exception("Query failed")
      raise HTTPException(status_code=503, detail=CONFIG_ERROR_MESSAGE)
  except Exception:
      logger.exception("Query failed")
      raise HTTPException(status_code=500, detail=GENERIC_ERROR_MESSAGE)
  ```
- No other lines change. `/feedback` and every 400-status `HTTPException` in these routes are untouched.

### 4. `backend/tests/test_error_responses.py` — new file
Follows the exact convention `test_delete_session.py` already uses — reuse `api_main`/`api` fixtures (and `_seed_session` where a valid session_id is needed) from `test_upload_concurrency.py`; call route functions directly via `asyncio.run(...)`, no HTTP client/`httpx` dependency (this repo already tests this exact surface this way).

Cases:
- `test_query_config_error_returns_503` (AC1)
- `test_query_generic_error_returns_500` (AC2)
- `test_upload_generic_error_returns_500` (AC3)
- `test_upload_url_generic_error_returns_500` (AC4)
- 4x `caplog`-based logging tests, one per branch above (AC5)
- `test_existing_400s_unchanged_spot_check` (AC6, thin — full 400 coverage already lives elsewhere)
- `test_feedback_500_unchanged` (AC7, new coverage — force `open()` to raise `OSError`)
- AC8 (no frontend file touched) is a diff check, not a pytest case.

**CI**: this new file will not run in CI (`.github/workflows/backend-tests.yml` runs exactly `test_embedder.py test_web_loader.py`); per CLAUDE.md ("never touch CI without explicit instruction") the workflow file is not edited. Module docstring documents the manual run command.

## Requirement/AC → Change → Test → Verification

| Spec req/AC | Code change | Test | Verification |
|---|---|---|---|
| R1, AC1 | `LLMConfigError` class + 9 raise-site swaps; `except LLMConfigError` branch in `/query` | `test_query_config_error_returns_503` | pytest — PASSED |
| R2 | `CONFIG_ERROR_MESSAGE`, 503 | same | same |
| R3, AC2 | `/query` generic branch → `GENERIC_ERROR_MESSAGE`, 500 | `test_query_generic_error_returns_500` | pytest — PASSED |
| R4, AC3 | `/upload` → `GENERIC_ERROR_MESSAGE`, 500 | `test_upload_generic_error_returns_500` | pytest — PASSED |
| R4, AC4 | `/upload-url` → `GENERIC_ERROR_MESSAGE`, 500 | `test_upload_url_generic_error_returns_500` | pytest — PASSED |
| R5, AC5 | `logger.exception(...)` unchanged in all branches | 4x `caplog` tests (query×2, upload, upload-url) | pytest — all 4 PASSED |
| R6 | Enforced structurally (constants hold no exception internals) | covered by exact-string assertions above | code review — confirmed |
| R7, AC6 | No change to 400-status blocks | `test_existing_400s_unchanged_spot_check` | pytest — PASSED |
| AC7 | No change to `/feedback` | `test_feedback_500_unchanged` | pytest — PASSED |
| AC8 | No `frontend/` files touched | n/a | `git diff --stat` — confirmed zero `frontend/` files |

## Files
- `backend/src/generation/answer_chain.py` — new exception class, 9 raise-site swaps
- `backend/api/main.py` — 1 import, 2 constants, 3 except-block edits
- `backend/tests/test_error_responses.py` — new

## Risks / notes
- No migration, no config change, no CORS/CI/deploy-config touch.
- `backend/venv` has `pytest`/`fastapi`/`chromadb` importable (confirmed this session).

## Verification (end-to-end) — to run during implementation
1. `cd backend && venv/bin/python -m pytest tests/test_error_responses.py -v`
2. Regression: `pytest tests/test_embedder.py tests/test_web_loader.py tests/test_delete_session.py tests/test_session_ttl.py tests/test_upload_concurrency.py tests/test_upload_dedup.py tests/test_upload_skipped_files.py -v`
3. CI parity: `pytest tests/test_embedder.py tests/test_web_loader.py -v`
4. `git diff --stat` reviewed — confirm no `frontend/` or CI file touched.
5. Not run: `test_pipeline.py` (needs an LLM key; CLAUDE.md).
