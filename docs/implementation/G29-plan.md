# Implementation Plan: G29 — provider 429/503 shown as generic 500

Session PLAN-G29-2026-09-30 · Spec `docs/specs/G29.md` (APPROVED) · Base `main` @ `09432cb` (local `main` == local `origin/main`; a `git fetch` is the first step after plan approval) · New branch `fix/G29-provider-429-503-status`.

## Implementation outcome (IMPL-G29-2026-09-30)
Implemented as designed; no plan row revised. Files: `backend/src/generation/answer_chain.py` (two exception classes, `_provider_status`, try/except around the dispatch in `answer()`), `backend/api/main.py` (import, two constants, two `except` branches), new `backend/tests/test_provider_throttling.py` (34 tests). Nothing under `frontend/`, `config.py`, `.env.example`, deploy files or CI touched.
Evidence (scratch venv in the session scratchpad, CPU torch, `pip install -r requirements.txt`): new tests 34 passed; red check on the unchanged code: 13 failed / 12 passed (the 12 cover unchanged behaviour); CI command 32 passed; key-free suite (`tests` minus `test_pipeline.py`) 148 passed. `test_pipeline.py` not run (needs key). No provider API call made.
Plan Risk 1 resolved by evidence: with the pinned SDKs installed, offline-constructed real exceptions confirm `status_code` for openai (429/503), anthropic (429/529 via `APIStatusError`) and mistralai 2.9.4 `SDKError`, and `.code` for google-genai `ClientError`/`ServerError`. Covered by real-class tests. Still unchecked: mistralai 2.4.2 (pinned in `requirements.prod.txt`, the Docker image) and whether anthropic raises a dedicated class for 529 (none named Overloaded* exists; `APIStatusError.status_code` carries it).
Pre-existing uncommitted doc/untracked files were carried onto the branch from `docs/G05-answer-path-observations`; not staged or committed.

## Context
`/query` maps every provider SDK error to `500 GENERIC_ERROR_MESSAGE`. Owner decision (Option 1, `docs/DECISIONS.md`): provider 429 → HTTP 429, provider 503/529 → HTTP 503, each with its own fixed message, no retry, no new settings, no frontend change. The four provider functions in `answer_chain.py` call their SDK raw, so classification goes in one place: `answer()`.

## Pre-flight notes (surface to developer)
- Current branch is `docs/G05-answer-path-observations` at `main`'s commit, with many uncommitted doc changes and untracked `docs/`, `.claude/`, `CLAUDE.md`. Branching from `main` carries those uncommitted files along (same as earlier tickets). I will not commit them; only my G29 files get staged when asked. **Confirm this is acceptable**, otherwise stop.
- No SDK (google-genai, anthropic, openai, mistralai) is installed locally; their exception attributes cannot be checked here.

## Design
1. `backend/src/generation/answer_chain.py`
   - Add two exception classes next to `LLMConfigError`, same flat style:
     `class LLMRateLimitError(Exception)` (status 429) and `class LLMOverloadedError(Exception)` (status 503/529). Docstring: raised by `answer()` for provider throttling/overload; mapped by `/query`; never shown verbatim.
   - Add `_provider_status(e) -> Optional[int]`: return `e.status_code` if it is an `int` (not `bool`), else `e.code` if an `int` (not `bool`), else `None`. Duck-typed: covers mistral/openai/anthropic (`status_code`) and google-genai (`code`) without importing any SDK.
   - In `answer()` wrap only the final `return dispatch[provider](...)`:
     ```python
     try:
         return dispatch[provider](question, context, chunks)
     except LLMConfigError:
         raise
     except Exception as e:
         status = _provider_status(e)
         if status == 429:
             raise LLMRateLimitError(f"{provider} rate limited (429)") from e
         if status in (503, 529):
             raise LLMOverloadedError(f"{provider} overloaded ({status})") from e
         raise
     ```
     The unknown-provider `LLMConfigError` raise sits before the try, and `_require_*` config errors are re-raised untouched. Classification happens only on the answer call, not `rewrite_query` (still swallowed) and not the embedder (out of scope).
2. `backend/api/main.py`
   - Import the two new exceptions with `LLMConfigError`.
   - Add constants beside `GENERIC_ERROR_MESSAGE`:
     `RATE_LIMIT_ERROR_MESSAGE = "The assistant is receiving too many requests right now. Please wait a moment and try again."`
     `BUSY_ERROR_MESSAGE = "The assistant is busy right now. Please try again in a moment."`
   - In `query_document`, add before `except Exception`: `except LLMRateLimitError:` → `logger.exception("Query failed")`, `HTTPException(429, RATE_LIMIT_ERROR_MESSAGE)`; `except LLMOverloadedError:` → same with 503 and `BUSY_ERROR_MESSAGE`. `logger.exception` logs the chained original (`from e`), so raw provider text still reaches logs only.
   - Not touched: `/upload`, `/upload-url`, `/ready`, `config.py`, `.env.example`, `frontend/`, deploy files.

## Requirement / AC → change → test → verification
New file `backend/tests/test_provider_throttling.py`, key-free, reusing `api` fixture from `tests.test_upload_concurrency` and the direct-call pattern from `tests/test_error_responses.py`.

Shared test helpers: a `FakeProviderError(Exception)` with settable `status_code` and/or `code` attribute and a message containing a secret-looking marker (`"SECRET-RAW-TEXT"`); a stub `ask` for the endpoint tests: `lambda *a, **k: answer("q", [{"text": "t", "source": "s.txt", "score": 1.0}])` so the real `answer()` dispatch runs, with `answer_chain._answer_<provider>` monkeypatched to raise, and `settings.llm_provider` monkeypatched per provider.

| Spec item | Code change | Test | Verification |
|---|---|---|---|
| R1, AC1 (429) | classify in `answer()`; `except LLMRateLimitError` in `/query` | endpoint test: provider fn raises error with `status_code=429` → `HTTPException` (429, `RATE_LIMIT_ERROR_MESSAGE`); assert `"SECRET-RAW-TEXT"` not in `detail` | pytest passes |
| R1, AC2 (503, 529) | same, `status in (503, 529)` | parametrized 503 and 529 → (503, `BUSY_ERROR_MESSAGE`); assert `BUSY_ERROR_MESSAGE != CONFIG_ERROR_MESSAGE`; negative: status 500, 401, `"429"` (str), `True`, none → (500, `GENERIC_ERROR_MESSAGE`) | pytest passes |
| R4, AC3 (all four providers) | `_provider_status` reads `status_code` else `code` | parametrize over gemini (`code=`), mistral/openai/anthropic (`status_code=`): monkeypatch `settings.llm_provider` and the matching `_answer_*`; real SDK exception class used when importable (`pytest.importorskip`-style guarded block), stand-in otherwise, with a docstring saying which | pytest passes; stand-ins labelled |
| R2 | messages are constants; `from e` keeps raw text out of `detail` | covered by AC1/AC2 no-leak assertions | same |
| R3, AC5 | `logger.exception("Query failed")` in both new branches | `caplog`: `"SECRET-RAW-TEXT"` present in `caplog.text` for 429 and 503 | pytest passes |
| R5, AC4 | existing branches unchanged; `LLMConfigError` re-raised before classification | re-run existing `test_query_config_error_returns_503`, `test_query_generic_error_returns_500`; add one test: `LLMConfigError` raised from a provider fn is still 503 `CONFIG_ERROR_MESSAGE` (not reclassified) | existing + new tests pass |
| R6, AC6 | no change to success/gate/refusal paths | run `test_pipeline_grounding.py`, `test_citation_sources.py` unchanged | pass |
| R7, AC7 (no retry) | none added | provider fn monkeypatched with a call counter; 429 and 503 each → counter == 1 | pytest passes |
| AC8 | — | `git diff --stat main` lists only `answer_chain.py`, `main.py`, the new test file (plus docs); nothing under `frontend/`, `config.py`, `.env.example`, deploy files | manual diff check |
| AC9 | — | `cd backend && pytest tests/test_embedder.py tests/test_web_loader.py -v` exit 0; then the full key-free set (`test_error_responses`, `test_provider_throttling`, `test_pipeline_grounding`, `test_citation_sources`, `test_ready_endpoint`, `test_delete_session`, `test_session_ttl`, `test_upload_*`) | exit 0; `test_pipeline.py` NOT run (needs key) |

Red-before-green: write the new tests first and run them on unchanged code to confirm AC1/AC2/AC3 fail with the generic 500 (this doubles as the spec's "static reproduction").

## Files
- Modify: `backend/src/generation/answer_chain.py`, `backend/api/main.py`
- Create: `backend/tests/test_provider_throttling.py`
- Docs at implementation end: `docs/implementation/G29-plan.md` (copy of this plan), handoff `docs/handoffs/PLAN-G29-2026-09-30-plan.md`; backlog/spec status updates.

## Risks
- Real SDK attribute names differ from the assumption (e.g. anthropic 529, google-genai `.code`). Mitigation: duck-typed read of both attributes; a wrong guess only degrades to today's generic 500. During implementation, if a scratch venv can install the pinned SDKs (`pip` into the scratchpad, no API calls), inspect the classes to confirm; otherwise record as still UNVERIFIED in the validation doc.
- A non-provider exception with an int `code` of 429/503 is misclassified (accepted in spec).
- Broad `except Exception` wrapper in `answer()` re-raises unchanged for everything else, so no behaviour change for other errors.
- The two 503 messages differ only by text (accepted in spec).

## Migration / deploy
None: no schema, config, env, dependency or deploy change.

## Verification summary
1. `git fetch`, confirm `main` == `origin/main`, create branch.
2. Add tests; run them red on old code.
3. Implement; run new tests green.
4. Run CI command, then the key-free suite. Confirm diff scope. No live provider call.
