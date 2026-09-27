# Validation: G11 — `DELETE /sessions/{session_id}` skips input validation

Session: VALID-G11-2026-09-27 · Branch `fix/G11-delete-session-validation` (HEAD `171a098` + one uncommitted line, rebased onto current `main`, which now includes G10) · Spec `docs/specs/G11.md` (APPROVED) · Plan `docs/implementation/G11-plan.md`

## Bug reproduction chain (evidence, not assertion)

**1. REPRODUCE ORIGINAL FAILURE** — temporarily reverted the fix (`git stash push -- backend/api/main.py`, restoring the pre-fix `delete_session` with no validation call) and ran the new test file against it:
```
pytest tests/test_delete_session.py -v
...
FAILED tests/test_delete_session.py::test_invalid_format_rejected_before_store_call[not-a-uuid]
FAILED tests/test_delete_session.py::test_invalid_format_rejected_before_store_call[123]
FAILED tests/test_delete_session.py::test_invalid_format_rejected_before_store_call[abc%2Fdef]
FAILED tests/test_delete_session.py::test_invalid_format_rejected_before_store_call[xxx...(250 chars)]
4 failed, 2 passed
```
Each failure is the store's `delete_session` actually being invoked with a malformed `session_id` (an `AssertionError` raised from the test's own guard, because the route never rejected the input first) — direct proof the vulnerability described in the spec's Root Cause exists on unfixed code. The two well-formed-UUID tests still passed, confirming the bug is specifically the missing validation, not something else.

Additionally ran the spec's own Reproduction step 2 verbatim against the unfixed code, via a standalone script constructing the same stubbed pipeline the test fixtures use:
```
>>> asyncio.run(m.delete_session('not-a-uuid'))
{'deleted': 'not-a-uuid', 'success': False}
```
Matches the spec's documented Current Behavior exactly: a malformed id is silently accepted and returns `200 success:false` instead of being rejected.

**2. APPLY FIX** — `git stash pop`, restoring `_validate_client_session_id(session_id)` as the first line of the route. Confirmed via `grep`/diff the exact one line is back.

**3. REPRODUCE SAME SCENARIO POST-FIX**:
```
>>> asyncio.run(m.delete_session('not-a-uuid'))
HTTPException 400 Invalid session_id.
```
Same input, now correctly rejected before the store is touched.

**4. VERIFY FAILURE IS GONE**: `pytest tests/test_delete_session.py -v` → `6 passed` (all 4 invalid-format cases now pass, plus both well-formed cases).

**5. VERIFY NO REGRESSION**: `pytest tests/test_upload_concurrency.py tests/test_upload_skipped_files.py tests/test_upload_dedup.py tests/test_session_ttl.py tests/test_delete_session.py -v` → `48 passed`. `pytest tests/test_embedder.py tests/test_web_loader.py -v` (exact CI command) → `32 passed`, exit 0.

## Acceptance Criteria

| AC | Requirement | Status | Evidence |
|---|---|---|---|
| AC1 | R1 — invalid format → 400, store not called | **VERIFIED** | `test_invalid_format_rejected_before_store_call["not-a-uuid"]` passes post-fix; fails pre-fix with proof the store was reached (bug reproduction step 1) |
| AC2 | R1 — sample of other invalid formats (`"123"`, `abc%2Fdef`, 250-char garbage) all 400, none reach store, none 500 | **VERIFIED** | Same test, all 4 parametrized cases pass post-fix (and fail pre-fix for the same reason as AC1) |
| AC3 | R2 — well-formed random UUID, never used → 200 success:false | **VERIFIED** | `test_wellformed_nonexistent_uuid_returns_success_false` passes both pre- and post-fix (unaffected behavior, as the spec requires) |
| AC4 | R2 — well-formed existing UUID → 200 success:true, then actually gone | **VERIFIED** | `test_wellformed_existing_uuid_deletes_and_returns_success_true` passes; asserts `session_exists() is False` after delete and that a second delete returns `success:false` |
| AC5 | R3 — fix confined to the `delete_session` route function; no other file changed | **VERIFIED** | `git diff main -- backend/` shows exactly `backend/api/main.py \| 1 +`; the one line is `_validate_client_session_id(session_id)`. No changes to `chroma_store.py`, `config.py`, route path/method |
| AC6 | CI command still exits 0; new test file not added to it | **VERIFIED** | `pytest tests/test_embedder.py tests/test_web_loader.py -v` → 32 passed, exit 0; `backend/tests/test_delete_session.py` is a separate file, not referenced by that command |
| AC7 | R4 — `POST /feedback`/`FeedbackRequest` byte-for-byte unchanged | **VERIFIED** | `git diff main -- backend/api/main.py` contains no `/feedback` or `FeedbackRequest` lines — the diff is one line, elsewhere in the file |

All 7 Acceptance Criteria: **VERIFIED**, none PARTIALLY VERIFIED/UNVERIFIED/FAILED/BLOCKED.

## Edge Cases (from spec, checked)
- UUID with/without hyphens, mixed case: not separately tested here — this is `_validate_client_session_id`'s existing, unmodified tolerance (already exercised by `/upload`/`/upload-url`/`/query`'s own tests), and this change adds a call to that helper without altering it. No new risk introduced.
- Same valid session deleted twice: covered directly by `test_wellformed_existing_uuid_deletes_and_returns_success_true`'s second call (`success:false` on the repeat) — unchanged behavior, verified not to have regressed.

## Definition of Done — G11

- [x] Specification approved — **APPLICABLE+VERIFIED** — `docs/specs/G11.md` `Status: APPROVED (2026-09-27, owner approval in this session)`, independently re-verified in session `SPECVERIFY-G11-2026-09-27`.
- [x] Implementation plan created — **APPLICABLE+VERIFIED** — `docs/implementation/G11-plan.md`, approved via `ExitPlanMode` in session `PLAN-G11-2026-09-27`.
- [x] Code implemented — **APPLICABLE+VERIFIED** — `backend/api/main.py` one-line change, confirmed present on `fix/G11-delete-session-validation`.
- [x] Unit tests pass — **APPLICABLE+VERIFIED** — `backend/tests/test_delete_session.py`, 6/6 passed.
- [x] Relevant existing tests pass — **APPLICABLE+VERIFIED** — `test_upload_concurrency.py`, `test_upload_skipped_files.py`, `test_upload_dedup.py`, `test_session_ttl.py` — 42/42 passed (this session's run, combined 48 with the new file).
- [ ] Integration tests pass (where applicable) — **NOT_APPLICABLE** — no integration test layer exists in this repo beyond the keyless pytest suite already covered above; route is exercised via direct function call per the repo's established test convention (see `test_upload_concurrency.py`), not a live HTTP client.
- [x] Original bug reproduced before fix — **APPLICABLE+VERIFIED** — bug reproduction chain step 1 above (test failures + standalone script, both matching the spec's Current Behavior exactly).
- [x] Original bug verified fixed — **APPLICABLE+VERIFIED** — bug reproduction chain steps 3–4 above.
- [x] Acceptance criteria verified — **APPLICABLE+VERIFIED** — AC1–AC7 table above, all VERIFIED.
- [x] Regression check performed — **APPLICABLE+VERIFIED** — bug reproduction chain step 5; 48 tests + CI command (32 tests), all passing.
- [x] Diff reviewed — **APPLICABLE+VERIFIED** — `git diff main -- backend/` reviewed by eye and quoted above; exactly one line.
- [x] No unrelated changes — **APPLICABLE+VERIFIED** — same diff review; no drive-by edits, no unrelated files in the branch's diff against `main` (docs-only files with uncommitted changes on the branch predate this work entirely — see Note below, and are not part of this branch's diff against `main` since they're uncommitted working-tree state shared across concurrent sessions, not branch content).
- [ ] Documentation updated (where necessary) — **NOT_APPLICABLE** — no user-facing docs, README, or API docs describe this endpoint's validation behavior; the spec/plan/validation docs themselves are the record.
- [ ] Commit created — **APPLICABLE+NOT_YET_VERIFIED** — the fix and test file are uncommitted on `fix/G11-delete-session-validation` as of this validation session; committing is left to the review/PR step, consistent with G01/G02/G27/G10 precedent where validation happens pre-commit.
- [ ] Branch pushed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — not yet pushed; follows commit.
- [ ] PR created (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — not yet created; next step is `review`.
- [x] CI passed (where applicable) — **APPLICABLE+VERIFIED** — local run of the exact CI command (`pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/`), 32 passed. GitHub Actions itself only runs once a PR/push exists.
- [ ] Review completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — this is Phase 1 (validation); review is the next session.
- [ ] Merge completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — per CLAUDE.md, only a human merges; not attempted.
- [ ] Post-merge verification completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — follows merge.
- [ ] Branch cleanup completed (where applicable) — **APPLICABLE+NOT_YET_VERIFIED** — follows merge.

**Note on the docs-only uncommitted files** (`docs/specs/{G01,G02,G10,G27}.md`, `docs/implementation/{G01,G02,G10,G27}-validation.md`): these show as modified in `git status` on this branch but are pre-existing working-tree state shared across this whole multi-session workflow (visible in the very first `git status` at the start of the overall session, before G11 work began), not something introduced by G11's implementation or this validation. They are untouched by `git diff main -- backend/` and by anything this session did. Not this branch's concern to resolve; flagged here only for completeness, not as a G11 defect.

## Overall Verdict
**PASS.** All 7 Acceptance Criteria VERIFIED with direct evidence, including a full reproduce→fix→reproduce→verify chain and a 48+32 test regression sweep. Ready for `review`.
