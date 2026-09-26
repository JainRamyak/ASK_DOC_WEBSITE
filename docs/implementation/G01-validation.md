# G01 — Validation

Session: VALID-G01-2026-09-26 · Branch `fix/G01-concurrent-upload-staging` (base `main` @ `bd69010`) · Spec `docs/specs/G01.md` (APPROVED)

**Environment.** Throwaway venv outside the repo (`~/.cache/claude-g01-venv`, Python 3.14.7). Requirements installed as pinned, except `torch`, which is the CPU build from the PyTorch CPU index (the pinned wheel's `triton` download kept failing, and `/tmp` tmpfs ran out of space). CI uses Python 3.11 and the pinned torch. That difference is not exercised here. Local embedder `all-MiniLM-L6-v2`; no API keys used, no paid calls.

**Diff under validation** (`git diff` + one untracked file): `backend/api/main.py` (+4/−1: request-keyed `tmp_dir` + comment) and new `backend/tests/test_upload_concurrency.py`. Nothing else.

## Bug chain: reproduce → fix → reproduce → verify

Probe: real `uvicorn api.main:app`, local embedder, 5 rounds. Each round seeds a session with 1 file, then fires 4 parallel `POST /upload` calls (distinct 1-chunk files) to that session. This is the 03 §5 scenario. Script: scratchpad `probe.py`, not committed.

| Step | Evidence |
|---|---|
| 1. Reproduce original failure (fix stashed via `git stash push -- backend/api/main.py`) | All 4 responses in every round were HTTP 200 but reported chunks 2–4 each (e.g. `[3,3,4,4]`, `[4,2,4,4]`). Collections held 13–16 chunks where 5 were expected; sources duplicated (e.g. `c0.txt` ×4). 5 of 5 rounds failed. The new test file also failed 5/8 (AC1–AC5) on this code. |
| 2. Apply fix | `git stash pop`; `git diff --stat`: `backend/api/main.py | 5 ++++-` |
| 3. Reproduce same scenario | Same probe, same script, fresh server. |
| 4. Verify failure gone | 5 of 5 rounds: HTTP `[200,200,200,200]`, chunks `[1,1,1,1]`, collection = 5, sources `c0..c3.txt` + `seed.txt` once each. `/tmp/rag_sessions` empty afterwards. New test file: 8/8 passed, and 8/8 on 5 further repeat runs. |
| 5. Verify no regression | CI command `pytest tests/test_embedder.py tests/test_web_loader.py`: 32 passed, exit 0. `test_sequential_new_and_append_response_contract` and `test_error_paths_unchanged` pass both before and after the fix. Seed uploads in the live probe (new session) returned 200 in both runs. |

## Acceptance criteria

| AC | Status | Evidence |
|---|---|---|
| AC1 (R1–R3) 4 concurrent, 1-chunk files: 200, `chunks==1`, exact total, each source once | VERIFIED | `test_concurrent_uploads_index_each_file_once`: fails unfixed, passes fixed. Live probe above: 5/5 rounds. |
| AC2 (R3) files of 1/2/3 chunks, per-file counts | VERIFIED | `test_concurrent_uploads_report_each_files_own_chunk_count`: fails unfixed, passes fixed. Expected values computed by `chunk_documents`. Live probe used only 1-chunk files. |
| AC3 (R4) failing request doesn't disturb in-flight ones | VERIFIED | `test_failing_request_does_not_disturb_in_flight_requests`: fails unfixed, passes fixed. Test-only; not exercised on a live server. |
| AC4 (R5) same filename, different content, both indexed | VERIFIED | `test_same_filename_in_overlapping_requests_are_both_indexed`: fails unfixed, passes fixed. Test-only. |
| AC5 (R6) stray staged file not ingested | VERIFIED | `test_stray_file_left_in_staging_is_not_ingested`: unfixed → `chunks == 2` (stray ingested); fixed → passes. Test-only. |
| AC6 (R7) response shape/status/messages unchanged | VERIFIED | `test_sequential_new_and_append_response_contract` and `test_error_paths_unchanged` pass before and after (keys, `filenames`, `status`, "Invalid session_id.", "not supported", "No readable text", "Too many files", no orphan session). The tests call the endpoint function directly, so the HTTP/multipart layer is exercised only by the live probe (200 + JSON with counts). |
| AC7 (R4) no staging data left | VERIFIED | `test_no_staging_data_left_after_success_and_failures` passes. `/tmp/rag_sessions` empty after both live probe runs. |
| AC8 CI command still exits 0; new test key-free | VERIFIED locally / NOT_YET_VERIFIED on GitHub CI | Local exit 0, 32 passed. New test needs no key. The real CI run (Python 3.11) has not happened; no push yet. |

Requirements without a direct check: R8 (single-process) is a constraint, not a behavior. The fix adds no cross-process claim.

## Definition of Done — G01

- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G01.md` Status APPROVED; human approved as written in-session.
- [x] Implementation plan created — APPLICABLE+VERIFIED — `docs/implementation/G01-plan.md`, approved in Plan Mode.
- [x] Code implemented — APPLICABLE+VERIFIED — diff above.
- [x] Unit tests pass — APPLICABLE+VERIFIED — new file, 8/8 (×6 runs).
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — 32 passed, exit 0.
- [x] Integration tests pass (where applicable) — APPLICABLE+VERIFIED — live-server probe, 5/5 rounds. No integration suite exists in the repo.
- [x] Original bug reproduced before fix — APPLICABLE+VERIFIED — live probe (5/5 rounds) and tests (5 failures).
- [x] Original bug verified fixed — APPLICABLE+VERIFIED — live probe and tests.
- [x] Acceptance criteria verified — APPLICABLE+VERIFIED — AC1–AC7; AC8 partially (see table).
- [x] Regression check performed — APPLICABLE+VERIFIED — CI tests plus AC6 tests.
- [x] Diff reviewed — APPLICABLE+VERIFIED — full diff read: 5 lines in `main.py` plus the test file. Formal review is the next skill.
- [x] No unrelated changes — APPLICABLE+VERIFIED — `git diff --name-only` shows only `backend/api/main.py`; the only new source-tree file is the test. Untracked `docs/`, `.claude/`, `CLAUDE.md` predate this task.
- [ ] Documentation updated (where necessary) — APPLICABLE+NOT_YET_VERIFIED — spec/plan/handoffs/validation written. `PROJECT_BACKLOG.md` still lists G01 as OPEN; to be updated at review/merge.
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — nothing committed (not requested yet).
- [ ] Branch pushed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not pushed.
- [ ] PR created (where applicable) — APPLICABLE+NOT_YET_VERIFIED — review phase.
- [ ] CI passed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — needs a push/PR. Note the workflow does not run the new test file (no CI edit was authorized).
- [ ] Review completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — next session.
- [ ] Merge completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — human only.
- [ ] Post-merge verification completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — after merge.
- [ ] Branch cleanup completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — after merge.

## Not run / caveats
- No lint, type-check or build step exists for the backend (CLAUDE.md), so none was run.
- Python 3.14 + CPU torch, not CI's 3.11 + pinned torch.
- Overlap in the live probe is timing-dependent; it reproduced the bug in 5/5 rounds before and showed no failure in 5/5 after. That is strong but not a proof. The mechanism (request-keyed dirs) removes the shared state.
- Pre-existing, unchanged: dirs orphaned by a hard kill mid-request are never cleaned up (per-request keys stop them being ingested, but they still leak disk). Out of scope; candidate found-but-out-of-scope item.
- `test_pipeline.py` (paid API) not run.
