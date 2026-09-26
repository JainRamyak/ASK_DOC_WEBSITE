# G02 — Validation

Session: VALID-G02-2026-09-26 · Branch `fix/G02-report-skipped-files` (base `main` @ `d782338`, uncommitted working tree) · Spec `docs/specs/G02.md` (APPROVED)

**Environment.** `backend/venv/` (Python 3.14.7, `requirements.txt` as pinned, incl. torch; the first install failed with ENOSPC in `/tmp` and was re-run with `TMPDIR` on `/home`). Live server: real `uvicorn api.main:app`, local embedder `all-MiniLM-L6-v2` (cached, no network), no API keys, no paid calls. CI uses Python 3.11; not exercised here. Live probe script and raw outputs are in the session scratchpad (`probe.py`, `probe_orig.txt`, `probe_fix.txt`), not committed.

**Diff under validation.** `backend/api/main.py`, `backend/src/ingestion/loader.py`, `backend/src/pipeline.py`, `backend/tests/test_upload_concurrency.py` (one assertion), new `backend/tests/test_upload_skipped_files.py`, `frontend/lib/types.ts`, `frontend/app/app/page.tsx`. Docs: plan outcome, backlog line. Every hunk maps to a plan row.

## Bug chain: reproduce → fix → reproduce → verify

| Step | Evidence |
|---|---|
| 1. Reproduce original failure | Detached worktree of `main` @ `d782338`, real uvicorn on :8101. One request, 8 files (`good.txt`, `blank.txt`, `broken.pdf`, `real.pdf`, `scan.pdf` (blank page), `tables.docx` (table only), `real.docx`, `broken.docx`): HTTP 200, `filenames` listed **all 8** as indexed, `chunks: 4`, no mention of the 5 unusable files. Append of `more.md` + `blank2.md`: both listed. Duplicate names `a.txt`(good), `a.txt`(blank), `a (1).txt`(good): all three listed. Concurrent variant: `cb.txt` (blank) listed as indexed. New test file on that code: **8 failed, 9 passed**. |
| 2. Apply fix | Branch diff (above). |
| 3. Reproduce same scenario | Identical `probe.py` against the branch, real uvicorn on :8102, fresh Chroma dir. |
| 4. Verify failure gone | Mixed batch: `filenames == [good.txt, real.pdf, real.docx]`; `skipped` = `blank.txt` (no_text), `broken.pdf` (unreadable), `scan.pdf` (no_text), `tables.docx` (no_text), `broken.docx` (unreadable); `chunks: 4` (same as before). Append: `filenames [more.md]`, `skipped [blank2.md]`. Duplicates: `filenames [a.txt, a (1).txt]`, `skipped [a.txt]`, `chunks: 4`. Concurrent: `cb.txt` reported skipped, others indexed with `chunks: 1`. Tests: new file 17/17 pass. |
| 5. Verify no regression | All-skipped request: HTTP 400 "No readable text was found in the uploaded file(s)." identical on both builds (new and existing session). All 8 G01 tests pass. 5 repeated runs of G02+G01 suites: 25 passed each. CI command: exit 0, 32 passed. `/tmp/rag_sessions` empty afterwards. Chunk counts for the same input are identical before/after (4, 2, 4). |

## Acceptance criteria

| AC | Status | Evidence |
|---|---|---|
| AC1 (R1, R2, R6) good + blank | VERIFIED | `test_skipped_file_not_reported_as_indexed` fails on `main`, passes on branch (also asserts stored count == `chunks`). Live: mixed batch above. |
| AC2 (R3) reason categories, safe messages | VERIFIED | `test_reason_categories_and_safe_messages` (fails on `main`, passes): `blank.txt`→`no_text`, `broken.pdf`→`unreadable`, messages differ, none contain `Traceback`, `/tmp`, `rag_sessions`, `Error`, `Exception`, `.py`. Live output shows only the two fixed strings. |
| AC3 (R4) duplicate names, both orders | VERIFIED | `test_duplicate_names_are_attributed_correctly[prose_first / blank_first]` fail on `main`, pass. Extra: `test_literal_name_matching_a_disambiguated_name_does_not_overwrite` (`a.txt, a.txt, a (1).txt` → all three indexed, 3 distinct sources) fails on `main`, passes. Live duplicate scenario above. |
| AC4 (R2) partition of uploaded names | VERIFIED | `test_every_upload_is_in_exactly_one_list` (5 files, mixed types), fails on `main`, passes. |
| AC5 (R5, R6) readable batch unchanged + empty `skipped` | VERIFIED | `test_fully_readable_uploads_have_empty_skipped_list` (new + append) and G01 `test_sequential_new_and_append_response_contract` (edited key set incl. `skipped`, `skipped == []`). |
| AC6 (R7) all-skipped → 400, cleanup | VERIFIED | `test_all_skipped_is_still_400_and_cleans_up_new_session`, `test_all_skipped_append_keeps_existing_session` (both pass on `main` too, i.e. behavior preserved); live 400 on both builds. |
| AC7 (R7) other error paths unchanged | VERIFIED | G01 `test_error_paths_unchanged` passes unmodified. |
| AC8 (R9, R10) G01 tests pass; concurrent + blank | VERIFIED | 8/8 G01 tests pass with only the one approved assertion edit (`git diff` shows +2/−1 lines); `test_concurrent_upload_with_a_blank_file_reports_correctly` and the live concurrent probe pass. |
| AC9 (R11) `/upload-url` unchanged | PARTIALLY VERIFIED | `test_upload_url_response_is_unchanged` with `ingest_url` stubbed (key set and values). `git diff` shows no change to `upload_url`. No live URL fetch was run (network/allowlist; out of scope). |
| AC10 (R5, R8) types, lint, build | VERIFIED | `frontend/lib/types.ts` has `SkippedFile` and `UploadResponse.skipped?`. `npm run lint` exit 0, `npx tsc --noEmit` exit 0, `npm run build` exit 0. |
| AC11 (R8) manual UI check | UNVERIFIED | Not run: no browser automation available here (Chrome/Chromium absent; Firefox present without a driver). Type-check and build pass, but the rendered notice, its accumulation on append and the reset behavior have not been seen. Steps for a human: run backend (`cd backend && venv/bin/uvicorn api.main:app --port 8000`) and frontend (`cd frontend && npm run dev`, `NEXT_PUBLIC_API_URL=http://localhost:8000`); upload `good.txt` + a whitespace-only `.txt`; expect banner to list only `good.txt` and an amber notice naming the blank file with its reason; add another blank file via "add more files" and expect both listed; click reset and expect the notice to clear. This also serves V-F28 for this area. |
| AC12 CI command exits 0, new tests key-free | VERIFIED locally / NOT_YET_VERIFIED on GitHub CI | Exit 0, 32 passed. New tests use stubs, no key. No push, so no CI run (Python 3.11) yet. |

## Requirements without a dedicated check
R8 (UI) rests on AC11 (unverified). R10 rests on AC8. No requirement is contradicted by evidence.

## Findings
- No failures. No spec/plan conflict.
- Spec Edge Case: scanned/blank PDFs report "no text… scanned images" without claiming OCR; consistent with G19 (OCR unavailable on Railway).
- Live probe confirms python-docx paragraph-only extraction: `tables.docx` is skipped as `no_text` (G21 remains open; G02 now surfaces it, as intended).
- `frontend/AGENTS.md` asks to read `node_modules/next/dist/docs/`; the directory does not exist in the installed Next (noted in the plan outcome). The change uses no Next-specific API.

## Definition of Done — G02

- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G02.md` Status APPROVED; human approved as written in PLAN-G02 session.
- [x] Implementation plan created — APPLICABLE+VERIFIED — `docs/implementation/G02-plan.md`, approved in Plan Mode.
- [x] Code implemented — APPLICABLE+VERIFIED — diff above; plan-row outcomes recorded.
- [x] Unit tests pass — APPLICABLE+VERIFIED — 17 new tests, 17/17 (25/25 with G01 file), repeated 5×.
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — G01 8/8; CI command 32/32. `test_pipeline.py` NOT run (paid API; CLAUDE.md), but its callers' contracts are covered by `test_ingest_still_returns_an_int` and `test_load_documents_result_is_a_plain_list_of_dicts`.
- [x] Integration tests pass (where applicable) — APPLICABLE+VERIFIED — live uvicorn + real embedder + real Chroma probe, before/after.
- [x] Original bug reproduced before fix — APPLICABLE+VERIFIED — live probe on `main` @ `d782338` and 8 failing tests.
- [x] Original bug verified fixed — APPLICABLE+VERIFIED — same probe on branch; tests pass.
- [ ] Acceptance criteria verified — APPLICABLE+NOT_YET_VERIFIED — 10 of 12 VERIFIED; AC9 PARTIAL; AC11 UNVERIFIED (no browser).
- [x] Regression check performed — APPLICABLE+VERIFIED — G01 suite, CI command, same chunk counts before/after, 400 paths identical.
- [x] Diff reviewed — APPLICABLE+VERIFIED — `git diff` read in full for backend and frontend (this session); review skill still to follow.
- [x] No unrelated changes — APPLICABLE+VERIFIED — source diff limited to plan rows. The uncommitted `docs/implementation/G01-validation.md` and `docs/specs/G01.md` edits and untracked workflow docs pre-date this work and are not part of the G02 change.
- [ ] Documentation updated (where necessary) — APPLICABLE+NOT_YET_VERIFIED — plan outcome + backlog line updated; final backlog status and any API doc wait for review/merge. No README/API doc describing the `/upload` response was found or changed.
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — nothing committed (awaits human instruction).
- [ ] Branch pushed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not pushed.
- [ ] PR created (where applicable) — APPLICABLE+NOT_YET_VERIFIED — review session.
- [ ] CI passed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — needs a push; note CI runs only the two existing test files (spec U2 left CI unchanged).
- [ ] Review completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — next session.
- [ ] Merge completed (where applicable) — NOT_YET_VERIFIED — human merges only.
- [ ] Post-merge verification completed (where applicable) — NOT_YET_VERIFIED — after merge.
- [ ] Branch cleanup completed (where applicable) — NOT_YET_VERIFIED — after post-merge verification.
