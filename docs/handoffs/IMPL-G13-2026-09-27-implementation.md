# Handoff: IMPL-G13-2026-09-27

SESSION ID: IMPL-G13-2026-09-27 (session named "PhaseB_G13")
SESSION TYPE: IMPLEMENTATION
OBJECTIVE: Implement `docs/implementation/G13-plan.md` against APPROVED spec `docs/specs/G13.md`.

CURRENT STATE: IMPLEMENTING → complete, all plan rows addressed as designed, ready for `validation-and-review`.

WORK COMPLETED:
- Confirmed branch `fix/G13-hide-raw-exception-detail`, created from `main` @ `b929908` (confirmed equal to `origin/main` via `git fetch`) at the start of this session (no plan file/branch existed from the prior planning session yet — created both as the first step here, since the implementation skill requires them).
- `backend/src/generation/answer_chain.py`: added `class LLMConfigError(Exception)`; swapped its 9 raise sites (unknown-provider `ValueError`, and each of the 4 providers' `ImportError`/`EnvironmentError`) to raise `LLMConfigError` with the same message text, unchanged. Left `_call_llm_plain`'s unrelated `ValueError` (used only by `rewrite_query`, which never propagates to `/query`) untouched.
- `backend/api/main.py`: added `from src.generation.answer_chain import LLMConfigError`; added `GENERIC_ERROR_MESSAGE` and `CONFIG_ERROR_MESSAGE` module constants; `/upload` and `/upload-url` catch-alls now raise `HTTPException(500, GENERIC_ERROR_MESSAGE)` (dropped the now-unused `as e` binding); `/query` now has `except LLMConfigError: ... 503 CONFIG_ERROR_MESSAGE` before `except Exception: ... 500 GENERIC_ERROR_MESSAGE`. `logger.exception(...)` calls unchanged in every branch. No other lines touched.
- New file `backend/tests/test_error_responses.py` (10 tests), reusing `api_main`/`api` fixtures from `test_upload_concurrency.py` per repo convention (direct async route-function calls, no HTTP client, no new dependency). Covers AC1–AC7 (AC8 is a diff check, not a test).
- Ran and passed: `pytest tests/test_error_responses.py -v` (10/10), the full regression set (`test_embedder.py`, `test_web_loader.py`, `test_delete_session.py`, `test_session_ttl.py`, `test_upload_concurrency.py`, `test_upload_dedup.py`, `test_upload_skipped_files.py` — 80/80), and the exact CI command in isolation (`test_embedder.py` + `test_web_loader.py` — 32/32).
- Confirmed via `git status --short backend/ frontend/ .github/` that the diff touches only the 3 planned files — no `frontend/` file, no CI workflow file.
- Did not run `test_pipeline.py` (needs a real LLM API key; CLAUDE.md — never run without explicit approval).
- Did not edit `.github/workflows/backend-tests.yml` — the new test file is not in CI's exact command and this was flagged, not decided, per CLAUDE.md ("never touch CI without explicit instruction"). Documented as a manual-run test in its module docstring.
- Annotated `docs/implementation/G13-plan.md` with an "Implementation outcome" section and marked each requirement/AC row's Verification column PASSED.

FILES CHANGED:
- `backend/api/main.py` (modified)
- `backend/src/generation/answer_chain.py` (modified)
- `backend/tests/test_error_responses.py` (new)

ARTIFACTS CREATED / UPDATED:
- docs/implementation/G13-plan.md (implementation outcome appended)
- docs/handoffs/IMPL-G13-2026-09-27-implementation.md (this file)
- Branch `fix/G13-hide-raw-exception-detail` (local; not pushed)

EVIDENCE:
- `venv/bin/python -m pytest tests/test_error_responses.py -v` → 10 passed.
- `venv/bin/python -m pytest tests/test_embedder.py tests/test_web_loader.py tests/test_delete_session.py tests/test_session_ttl.py tests/test_upload_concurrency.py tests/test_upload_dedup.py tests/test_upload_skipped_files.py -v` → 80 passed.
- `venv/bin/python -m pytest tests/test_embedder.py tests/test_web_loader.py -v` → 32 passed (CI parity).
- `git diff backend/api/main.py backend/src/generation/answer_chain.py` reviewed in full — matches the plan exactly.
- `git status --short backend/ frontend/ .github/` → only the 3 planned files touched.

DECISIONS: none new this session — implemented the decision already recorded in `docs/DECISIONS.md` from the specification session.

UNKNOWNS: none blocking. `test_pipeline.py`'s reference risk (flagged in the spec's Unknowns) was checked during planning — it only imports `NOT_FOUND_MESSAGE` from `answer_chain.py`, nothing exception-related, so it is unaffected by this change (not run, per CLAUDE.md, but confirmed safe by inspection).

FOUND BUT OUT OF SCOPE: none identified during implementation.

NEXT REQUIRED HUMAN ACTION: none to continue the workflow — implementation is complete and self-verified. A human will eventually review/merge the PR (never auto-merged, per CLAUDE.md).
NEXT OBJECTIVE: Run `validation-and-review` for G13 to validate against the Definition of Done and prepare the PR.
