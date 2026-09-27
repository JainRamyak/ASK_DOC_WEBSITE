## Summary
`/upload`, `/upload-url`, and `/query` returned `f"Ingestion failed: {e}"` or `str(e)` as the HTTP 500 `detail` for any unexpected exception, and the frontend displays `detail` verbatim (`humanizeError`), so operator-facing internals reached end users — observed concretely as a missing LLM key producing `"GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com"` in a user-facing error.

- `answer_chain.py` now raises a dedicated `LLMConfigError` for provider misconfiguration (missing/invalid API key, missing SDK, unrecognized `LLM_PROVIDER`) instead of bare `EnvironmentError`/`ImportError`/`ValueError`, matching this repo's existing narrow-exception convention (`URLValidationError`, `FileValidationError`).
- `/query` catches `LLMConfigError` first and returns `503` + `"The assistant is temporarily unavailable. Please try again later."`; every other exception on `/upload`, `/upload-url`, and `/query` returns `500` + one shared `"Something went wrong while processing your request. Please try again."`.
- `logger.exception(...)` is unchanged in every branch — the full exception/traceback still reaches server logs, only the client-visible `detail` changes.
- `/feedback` and all pre-existing 400-status responses are untouched.

Spec: `docs/specs/G13.md` (APPROVED) · Plan: `docs/implementation/G13-plan.md` · Validation: `docs/implementation/G13-validation.md` · Decision: `docs/DECISIONS.md` (local workflow-tracking file, not yet checked in — same as prior G10/G11/G27 PRs)

## Validation evidence
- Full reproduce→fix→reproduce→verify chain (not just "tests pass"): reverted the fix locally, forced the exact scenario from the spec's OBSERVED evidence (`pipeline.ask` raising the missing-key message) — confirmed unfixed code returns `500` with the raw message verbatim; re-applied the fix, confirmed the same scenario now returns `503` + the fixed message, with the original message still visible in the server log (`logger.exception`).
- New `backend/tests/test_error_responses.py` (key-free, direct route-call, stubbed embedder — same pattern as `test_upload_concurrency.py`/`test_delete_session.py`): 10 tests covering all 8 Acceptance Criteria (config-error 503, generic 500 on all three routes, logging still captures the original exception in every branch, pre-existing 400s and `/feedback`'s 500 unchanged).
- Regression: 90 backend tests (`test_embedder`, `test_web_loader`, `test_delete_session`, `test_session_ttl`, `test_upload_concurrency`, `test_upload_dedup`, `test_upload_skipped_files`, `test_error_responses`) all pass.
- CI command `pytest tests/test_embedder.py tests/test_web_loader.py -v` (from `backend/`): 32 passed locally, exit 0.
- Diff reviewed: exactly `backend/api/main.py` (1 import, 2 constants, 3 except-block edits) and `backend/src/generation/answer_chain.py` (1 new exception class, 9 raise-site swaps) plus the new test file — no frontend, CI workflow, or deploy-config file touched.

## Not verified / for the reviewer
- GitHub Actions `backend-tests` run status for this push — not yet observed from this session; will record once visible.
- `backend/tests/test_pipeline.py` not run (needs a real LLM API key; out of scope for this change — confirmed by inspection it only imports `NOT_FOUND_MESSAGE` from `answer_chain.py`, unaffected by this change).
- No new test file was added to CI's exact command (`.github/workflows/backend-tests.yml` still runs only `test_embedder.py`/`test_web_loader.py`) — per CLAUDE.md, CI is not touched without explicit instruction; `test_error_responses.py` is documented as a manual-run regression test in its module docstring. Flagging in case the reviewer wants CI broadened as a separate follow-up.
- No frontend or manual UI check — `frontend/lib/api.ts` already displays `detail` verbatim regardless of its content, so there's nothing UI-code-level to change; a live smoke test against a running `uvicorn` instance was not performed this session (only the direct-function-call test layer), consistent with how prior G-series PRs in this repo verified route-handler changes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
