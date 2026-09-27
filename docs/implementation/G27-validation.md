# G27 — Validation

Session: VALID-G27-2026-09-27 · Branch `fix/G27-dedup-reupload` (base `main` @ `d8760a5`, uncommitted working tree) · Spec `docs/specs/G27.md` (APPROVED) · Plan `docs/implementation/G27-plan.md`

**Environment.** `backend/venv/` (Python 3.14.7, chromadb 1.5.9, pytest 8.2.0, fastapi 0.136.1 — all importable, per `requirements.txt`). Live checks used real `uvicorn api.main:app` and the real local embedder (`all-MiniLM-L6-v2`, cached, no network) and real `next dev`; no API keys, no paid calls. CI uses Python 3.11 — not exercised here (matches G01/G02 validation precedent). Probe script and a pristine `main` worktree (`/tmp/g27-before`, removed after use) were used for the reproduce/fix comparison; not committed.

**Diff under validation.** `backend/src/storage/chroma_store.py`, `backend/src/pipeline.py`, `backend/src/ingestion/chunker.py`, `backend/api/main.py`, `backend/tests/test_upload_concurrency.py` (1 assertion), `backend/tests/test_upload_skipped_files.py` (1 stub + 1 assertion), new `backend/tests/test_upload_dedup.py`, `frontend/lib/types.ts`, `frontend/app/app/page.tsx`. Every changed file matches the plan's file list exactly (`git diff --stat` — 8 files, no unrelated files).

## Bug chain: reproduce → fix → reproduce → verify

| Step | Evidence |
|---|---|
| 1. Reproduce original failure | `git worktree add /tmp/g27-before main` (pristine `d8760a5`). Probe (`/upload` → `notes.txt`, 2 chunks; re-`/upload` identical bytes, same session): second response `{'filenames': ['notes.txt'], 'skipped': [], 'chunks': 2, 'status': 'ready'}` — reported as freshly indexed. Final stored chunk count: **4** (doubled from 2). Also: copying the new `test_upload_dedup.py` into that pristine worktree and running it there gives **9 failed** (`KeyError: 'already_indexed'` / wrong counts) — confirms the regression suite genuinely exercises the defect. |
| 2. Apply fix | Branch diff (above), already implemented in `IMPL-G27-2026-09-27`. |
| 3. Reproduce same scenario | Identical probe against the current branch, fresh Chroma dir, real local embedder. |
| 4. Verify failure is gone | First upload: `{'filenames': ['notes.txt'], 'skipped': [], 'already_indexed': [], 'chunks': 2, ...}`. Re-upload identical bytes, same session: `{'filenames': [], 'skipped': [], 'already_indexed': [{'filename': 'notes.txt', 'hash': '2d7aada2...4ce683f62'}], 'chunks': 0, ...}` — hash matches `hashlib.sha256(data).hexdigest()` computed independently. Final stored chunk count: **2** (unchanged — no duplicate). `test_upload_dedup.py` on the branch: **9/9 pass**. |
| 5. Verify no regression | `pytest tests/ --ignore=tests/test_pipeline.py -q` → **66 passed** (all of G01 + G02 + G27's own suite). CI command `pytest tests/test_embedder.py tests/test_web_loader.py -v` → **32 passed**, exit 0. `test_concurrent_identical_reupload` re-run 5× standalone: passed every time (no flake). `test_pipeline.py` **not run** — needs a live LLM key; CLAUDE.md forbids running it without approval. Frontend: `npm run lint` clean, `npm run build` succeeds with no new errors (`/app` route compiles, static generation succeeds). Live end-to-end: real `uvicorn` (local embedder, no keys) + real `next dev`, both started and reachable (`/health` 200, `/app` served) — see AC11 below for what this did and didn't cover. |

## Acceptance criteria (docs/specs/G27.md)

| AC | Requirement(s) | Status | Evidence |
|---|---|---|---|
| AC1 | R1,R2,R3 | VERIFIED | `test_identical_reupload_is_skipped`; live probe (bug chain step 4) reproduces the exact response shape and hash with a real embedder/store, not just the stub. |
| AC2 | R1,R2 | VERIFIED | `test_rename_is_still_a_repeat` — identical bytes under a different filename is still a repeat. |
| AC3 | R7 | VERIFIED | `test_same_name_different_content_indexes_both` — same filename, different bytes, both versions indexed and retrievable (`get(include=["documents"])` checked for both markers). |
| AC4 | R3 | VERIFIED | `test_mixed_batch_partitions_correctly` — new/repeat/skip in one batch partitions into disjoint `filenames`/`already_indexed`/`skipped` covering exactly the uploaded filenames. |
| AC5 | R6 | VERIFIED | `test_concurrent_identical_reupload` (reuses `_install_gate` from the G01 suite) — exactly one of two simultaneous identical uploads wins; collection ends with exactly one copy's worth of chunks; re-run 5× with no flake. |
| AC6 | R5 | VERIFIED | `test_same_content_different_sessions_both_index` — identical bytes to two different sessions both index independently. |
| AC7 | — (regression) | VERIFIED | `test_upload_concurrency.py` (8 tests) and `test_upload_skipped_files.py` (12 tests) pass unmodified in behavior, with the two pre-approved assertion/stub updates from the plan (key-set gains `already_indexed`; `ingest_url` stub returns `IngestResult`). |
| AC8 | R4 | VERIFIED | `test_upload_url_repeat` — repeat URL returns 200 (not 400) with `chunks: 0` and `already_indexed` naming the URL; hash matches `sha256(text)` independently computed. |
| AC9 | R9 | VERIFIED | `git diff` touches no file under `src/retrieval/` or `src/generation/`; `retrieve_and_rerank`/`answer_chain` unchanged (diff review, not just assertion). |
| AC10 | R10 | VERIFIED | `frontend/lib/types.ts` has `AlreadyIndexedFile`/`UploadResponse.already_indexed`; `npm run lint` and `npm run build` both pass with no new errors/warnings. |
| AC11 | R10 | **NOT_YET_VERIFIED** | See below — no browser automation tool was available in this session to drive the actual page; the underlying data path was verified live instead. |
| AC12 | — | VERIFIED | `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/`: 32 passed, exit 0. |

### AC11 detail (why NOT_YET_VERIFIED, not a false pass)
What **was** done live: started the real backend (`uvicorn`, local embedder, no keys) and the real frontend (`next dev`, pointed at it via `NEXT_PUBLIC_API_URL`); both served successfully (`/health` 200, `/app` reachable). This confirms the exact JSON shape the running frontend will receive is what `page.tsx` was written against (already confirmed by the backend-side live probe above, which used the identical response contract).
What was **not** done: actually loading `/app` in a browser, uploading a file, re-uploading it, and looking at the rendered banner. No browser automation tool (`claude-in-chrome`, built-in browser) was reachable/available in this session — the available web tools (`WebFetch`, Firecrawl) explicitly cannot reach `localhost`. This is the same gap G02's AC11 was left with (`docs/PROJECT_BACKLOG.md`: "G02 ... AC11 manual UI check pending") — recorded honestly rather than asserted.
Supporting (not substitute) evidence: `npm run build` type-checks the component (the `AlreadyIndexedFile[]` shape flows through cleanly), the new banner reuses the exact JSX/state pattern already shipped and visually verified for G02's `skipped` banner (same component, same file, same session-state wiring), and the state-update code was read in full during implementation.

## Definition of Done — G27

- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G27.md` `Status: APPROVED` (2026-09-27).
- [x] Implementation plan created — APPLICABLE+VERIFIED — `docs/implementation/G27-plan.md`.
- [x] Code implemented — APPLICABLE+VERIFIED — diff above; matches every plan row (outcome note in the plan file: no row needed revision).
- [x] Unit tests pass — APPLICABLE+VERIFIED — `test_upload_dedup.py` 9/9 (bug-chain step 4).
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — `test_upload_concurrency.py` 8/8, `test_upload_skipped_files.py` 12/12 (bug-chain step 5).
- [x] Integration tests pass (where applicable) — APPLICABLE+VERIFIED — live `uvicorn` + real local embedder + real Chroma persistence probe (bug-chain steps 1–4), not just stubbed pytest.
- [x] Original bug reproduced before fix — APPLICABLE+VERIFIED — bug-chain step 1 (pristine `main` worktree, live probe: chunk count doubled 2→4; new tests fail 9/9 against pre-fix code).
- [x] Original bug verified fixed — APPLICABLE+VERIFIED — bug-chain step 4 (same probe, branch: chunk count stays at 2, `already_indexed` populated with the correct hash).
- [~] Acceptance criteria verified — APPLICABLE+NOT_YET_VERIFIED (partial) — AC1–AC10, AC12 VERIFIED; AC11 NOT_YET_VERIFIED (no browser tool available this session; see AC11 detail above).
- [x] Regression check performed — APPLICABLE+VERIFIED — full keyless suite 66/66 (bug-chain step 5); `test_pipeline.py` deliberately not run (needs paid API key, CLAUDE.md).
- [x] Diff reviewed — APPLICABLE+VERIFIED — `git diff --stat` matches the plan's file list exactly; no file outside `backend/{api,src,tests}` or `frontend/{lib,app}` touched.
- [x] No unrelated changes — APPLICABLE+VERIFIED — same diff review; no drive-by refactors, renames, or unrelated edits found in the 8 changed files.
- [x] Documentation updated (where necessary) — APPLICABLE+VERIFIED — `docs/implementation/G27-plan.md` outcome note, `docs/PROJECT_BACKLOG.md` G27 status, this validation doc, session handoffs.
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — out of scope for this session (Phase 1 validation only, per this session's own instructions); belongs to the review/PR-preparation phase.
- [ ] Branch pushed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not done this session, same reason.
- [ ] PR created (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not done this session, same reason.
- [ ] CI passed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — no PR/CI run exists yet; the CI *command* was run locally and passed (see AC12), but the actual GitHub Actions run has not executed.
- [ ] Review completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — no PR open yet.
- [ ] Merge completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — merge is a human action (CLAUDE.md: never merge automatically).
- [ ] Post-merge verification completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — only valid after merge.
- [ ] Branch cleanup completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — only valid after merge.

## Result
All code-level and testable behavior is VERIFIED with evidence, including a genuine reproduce→fix→reproduce→verify chain run against a pristine pre-fix checkout, not just an assertion that the code "should" fix it. One item (AC11's actual browser click-through) is honestly NOT_YET_VERIFIED for lack of a reachable browser tool in this session, with strong supporting (not substitute) evidence. Phase 2 (commit, push, PR) was out of this session's scope per its own instructions and is the next step.
