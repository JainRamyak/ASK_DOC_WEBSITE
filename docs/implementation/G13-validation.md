# Validation: G13 — raw exception text returned to clients in HTTP 500 details

Session: VALID-G13-2026-09-27 · Branch `fix/G13-hide-raw-exception-detail` (base `main` @ `b929908`, uncommitted) · Spec `docs/specs/G13.md` (APPROVED) · Plan `docs/implementation/G13-plan.md`

## Bug reproduction chain (evidence, not assertion)

**1. REPRODUCE ORIGINAL FAILURE** — temporarily reverted the fix (`git stash push -- backend/api/main.py backend/src/generation/answer_chain.py`, restoring pre-fix code) and ran a standalone script forcing `pipeline.ask` to raise `EnvironmentError("GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com")` (the exact message quoted in the spec's Reproduction and OBSERVED evidence), then calling `api.query_document(...)` directly:
```
status=500
detail='GEMINI_API_KEY is not set in .env. Get a free key at https://aistudio.google.com'
RAW_MESSAGE_LEAKED=True
```
Confirms the spec's Current Behavior exactly: the raw exception message reaches the client verbatim as `detail`, with status 500 (no distinct config-error status).

**2. APPLY FIX** — `git stash pop`, restoring both files. Confirmed via `git status --short backend/` that exactly `backend/api/main.py` and `backend/src/generation/answer_chain.py` are back to modified state (plus the untracked `backend/tests/test_error_responses.py`).

**3. REPRODUCE SAME SCENARIO POST-FIX** — same script, now raising `LLMConfigError` (the type the fixed `answer_chain.py` actually raises for this exact condition) with the same message text:
```
status=503
detail='The assistant is temporarily unavailable. Please try again later.'
RAW_MESSAGE_LEAKED=False
```
(The traceback containing the raw message that appears in the script's stderr immediately before this is `logger.exception("Query failed")` firing as designed — evidence for AC5, not a leak to the client: `exc.detail` itself contains only the fixed string.)

**4. VERIFY FAILURE IS GONE**: `pytest tests/test_error_responses.py -v` → `10 passed`, including `test_query_config_error_returns_503` and `test_query_config_error_still_logs_original` which pin this exact scenario as a regression test going forward.

**5. VERIFY NO REGRESSION**: `pytest tests/test_error_responses.py tests/test_embedder.py tests/test_web_loader.py tests/test_delete_session.py tests/test_session_ttl.py tests/test_upload_concurrency.py tests/test_upload_dedup.py tests/test_upload_skipped_files.py -v` → `90 passed`. `pytest tests/test_embedder.py tests/test_web_loader.py -v` (exact CI command) → `32 passed`, exit 0.

## Acceptance Criteria

| AC | Requirement | Status | Evidence |
|---|---|---|---|
| AC1 | R1/R2 — config error on `/query` → 503 + fixed message | **VERIFIED** | `test_query_config_error_returns_503` passes post-fix; bug reproduction chain step 3 shows the exact status/detail live, step 1 shows the pre-fix leak for the same scenario |
| AC2 | R3 — any other `/query` exception → 500 + shared generic message | **VERIFIED** | `test_query_generic_error_returns_500` passes; forces a plain `RuntimeError`, asserts `(500, GENERIC_ERROR_MESSAGE)` |
| AC3 | R4 — `/upload` catch-all → 500 + shared generic message | **VERIFIED** | `test_upload_generic_error_returns_500` passes; forces `pipeline.ingest_with_report` to raise, asserts `(500, GENERIC_ERROR_MESSAGE)`, not `f"Ingestion failed: {e}"` |
| AC4 | R4 — `/upload-url` catch-all → 500 + shared generic message | **VERIFIED** | `test_upload_url_generic_error_returns_500` passes; forces `pipeline.ingest_url` to raise, same assertion |
| AC5 | R5 — server log still captures the original exception in every branch | **VERIFIED** | 4 `caplog`-based tests (`test_query_config_error_still_logs_original`, `test_query_generic_error_still_logs_original`, `test_upload_error_still_logs_original`, `test_upload_url_error_still_logs_original`) each assert the forced exception's original message text is present in `caplog.text`, all pass |
| AC6 | R7 — pre-existing 400-status responses unchanged | **VERIFIED** | `test_existing_400s_unchanged_spot_check` passes (`/query` non-UUID → `400 "Invalid session_id."`; `/upload-url` empty url → `400 "url is required"`); full regression suite (`test_delete_session.py`, `test_session_ttl.py`, `test_upload_dedup.py`, `test_upload_skipped_files.py` — which exercise many other 400 paths) all still pass unmodified |
| AC7 | `/feedback`'s existing safe 500 unchanged | **VERIFIED** | `test_feedback_500_unchanged` (new coverage, not previously tested anywhere) passes: forced `OSError` on write still yields `(500, "Could not record feedback")` |
| AC8 | No frontend file modified | **VERIFIED** | `git status --short backend/ frontend/ .github/ railway.toml render.yaml docker-compose.yml` shows zero `frontend/`, CI, or deploy-config files touched — only `backend/api/main.py`, `backend/src/generation/answer_chain.py` (modified), `backend/tests/test_error_responses.py` (new) |

All 8 Acceptance Criteria: **VERIFIED**, none PARTIALLY VERIFIED/UNVERIFIED/FAILED/BLOCKED.

## Requirements cross-check (R1–R7, spec `docs/specs/G13.md`)
- R1 (type-based classification in `/query`): confirmed by code review of `backend/api/main.py`'s `except LLMConfigError:` branch preceding the bare `except Exception:` — subclass-before-superclass ordering verified correct (Python would otherwise never reach the specific branch).
- R2/R3/R4 (exact status/message per case): AC1–AC4 above.
- R5 (logging unchanged): AC5 above; additionally confirmed by direct diff review — the `logger.exception(...)` call sites, `shutil.rmtree(...)`, and `_cleanup_if_new(...)` calls are byte-identical to pre-fix, only the `HTTPException(...)` line changed in each block (`git diff backend/api/main.py`, reviewed in full this session).
- R6 (no exception internals in any 500/503 `detail`): enforced structurally — `GENERIC_ERROR_MESSAGE` and `CONFIG_ERROR_MESSAGE` are fixed literals containing no interpolation; `grep -n "detail=.*{e}\|detail=str(e)"` on `backend/api/main.py` post-fix shows only the pre-existing, out-of-scope, deliberate 400s (`FileValidationError`/`URLValidationError` messages, file-count/question-length limits) — none of the three unexpected-exception 500/503 sites remain.
- R7 (`/feedback` and 400s untouched): AC6/AC7 above.

## Edge Cases (from spec, checked)
- Unrelated `EnvironmentError`/`ImportError` from a different source (spec's noted acceptable edge case): not separately tested — the spec explicitly accepts this as harmless since the 503 message is generic enough not to mislead either way; no behavior change needed to satisfy it.
- Unrelated `ValueError` elsewhere in `/query`'s call graph misclassified as config error: verified NOT possible — `LLMConfigError` is a distinct class (not a `ValueError` subclass), so no other `ValueError` in the codebase can be caught by `except LLMConfigError:`. This is a stronger guarantee than the spec's Edge Cases discussion (which only ruled out a *message-prefix* mechanism) — the class-based mechanism actually implemented eliminates the false-positive risk entirely rather than just mitigating it.
- `/upload`/`/upload-url` never raising `LLMConfigError` (confirmed unreachable at spec time via `pipeline.py:222`): re-confirmed unchanged post-fix — `answer_chain.py`'s `answer()` function is still called only from `pipeline.ask`, still called only from `/query`.

## Definition of Done — G13

- [x] Specification approved — **APPLICABLE+VERIFIED** — `docs/specs/G13.md` `Status: APPROVED (2026-09-27, SPEC-G13-2026-09-27)`, independently re-verified in session `SPECVERIFY-G13-2026-09-27` with no code drift found.
- [x] Implementation plan created — **APPLICABLE+VERIFIED** — `docs/implementation/G13-plan.md`, designed via Plan Mode in session `PLAN-G13-2026-09-27`, executed as designed with no row revisions.
- [x] Code implemented — **APPLICABLE+VERIFIED** — `backend/api/main.py` and `backend/src/generation/answer_chain.py`, confirmed present on `fix/G13-hide-raw-exception-detail` and reviewed in full diff this session.
- [x] Unit tests pass — **APPLICABLE+VERIFIED** — `backend/tests/test_error_responses.py`, 10/10 passed (this session's fresh run).
- [x] Relevant existing tests pass — **APPLICABLE+VERIFIED** — `test_embedder.py`, `test_web_loader.py`, `test_delete_session.py`, `test_session_ttl.py`, `test_upload_concurrency.py`, `test_upload_dedup.py`, `test_upload_skipped_files.py` — 80/80 passed (this session's fresh run, combined 90 with the new file).
- [ ] Integration tests pass (where applicable) — **NOT_APPLICABLE** — no integration/HTTP-client test layer exists in this repo; routes are exercised via direct async function call per the established convention (`test_upload_concurrency.py`, `test_delete_session.py`), which this change follows.
- [x] Original bug reproduced before fix — **APPLICABLE+VERIFIED** — bug reproduction chain step 1 above, matching the spec's documented OBSERVED behavior and exact raw-message text.
- [x] Original bug verified fixed — **APPLICABLE+VERIFIED** — bug reproduction chain steps 3–4 above.
- [x] Acceptance criteria verified — **APPLICABLE+VERIFIED** — AC1–AC8 table above, all VERIFIED.
- [x] Regression check performed — **APPLICABLE+VERIFIED** — bug reproduction chain step 5; 90 tests + CI command (32 tests), all passing, fresh this session.
- [x] Diff reviewed — **APPLICABLE+VERIFIED** — `git diff backend/api/main.py backend/src/generation/answer_chain.py` reviewed in full and quoted in the implementation handoff; matches the plan exactly, no surprises.
- [x] No unrelated changes — **APPLICABLE+VERIFIED** — `git status --short backend/ frontend/ .github/ railway.toml render.yaml docker-compose.yml` shows only the 3 planned files; the many other modified/untracked doc files visible in `git status` predate this branch entirely (pre-existing multi-session workflow state, same situation noted in G11's validation) and are not part of this change's diff.
- [ ] Documentation updated (where necessary) — **NOT_APPLICABLE** — no user-facing docs, README, or API docs describe the exact wording of error responses; the spec/plan/validation docs themselves are the record, and `docs/PROJECT_BACKLOG.md`'s G13 entry was already updated to APPROVED during specification.
- [x] Commit created — **APPLICABLE+VERIFIED** — `60a1084` "fix(G13): stop returning raw exception text on HTTP 500/503" on `fix/G13-hide-raw-exception-detail` (session `REVIEW-G13-2026-09-27`).
- [x] Branch pushed (where applicable) — **APPLICABLE+VERIFIED** — `git push -u origin fix/G13-hide-raw-exception-detail` succeeded.
- [x] PR created (where applicable) — **APPLICABLE+VERIFIED** — PR #9, https://github.com/JainRamyak/ASK_DOC_WEBSITE/pull/9, open against `main`.
- [x] CI passed (where applicable) — **APPLICABLE+VERIFIED** — local run 32/32 passed; GitHub Actions `test` check on the pushed commit `60a1084` completed with conclusion `success` (see CI status section below).
- [ ] Review completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — PR is open; human review has not yet happened.
- [ ] Merge completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — per CLAUDE.md, only a human merges; not attempted.
- [ ] Post-merge verification completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — follows merge.
- [ ] Branch cleanup completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — follows merge.

**Note on the docs-only uncommitted/untracked files**: as with G01/G02/G10/G11/G27's validations, the many modified/untracked `docs/` files visible in `git status` on this branch are pre-existing multi-session workflow state from before G13 work began (specs/validation docs for already-merged backlog items, plus this session's own G13 spec/handoff docs). None are touched by, or relevant to, this branch's application-code diff.

## Overall Verdict
**PASS.** All 8 Acceptance Criteria VERIFIED with direct evidence, including a full reproduce→fix→reproduce→verify chain (using the spec's own OBSERVED scenario) and a 90+32 test regression sweep, all run fresh in this session. Ready for `review`.

## CI status (REVIEW-G13-2026-09-27)
PR #9 opened from `fix/G13-hide-raw-exception-detail` into `main`. GitHub Actions `test` check on commit `60a1084`: **completed, conclusion `success`**, both matrix runs ([36335370393](https://github.com/JainRamyak/ASK_DOC_WEBSITE/actions/runs/36335370393/job/108665088905), [36335339354](https://github.com/JainRamyak/ASK_DOC_WEBSITE/actions/runs/36335339354/job/108665002911)), confirmed via the GitHub REST API `check-runs` endpoint (`gh` CLI unavailable in this environment, same workaround as G11's post-merge verification). `Vercel Preview Comments` check also completed successfully (unrelated to this backend-only change).
