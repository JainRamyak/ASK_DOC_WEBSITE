# G10 — Validation

Session: VALID-G10-2026-09-27 · Branch `fix/G10-ttl-activity-anchor` (base `main` @ `834a94a`, verified equal to `origin/main`; uncommitted working tree) · Spec `docs/specs/G10.md` (APPROVED) · Plan `docs/implementation/G10-plan.md`

**Environment.** `backend/venv/` (Python 3.14.7, chromadb 1.5.9, pytest 8.2.0, fastapi 0.136.1 — all importable, per `requirements.txt`). A separate scratch venv (`/tmp/chroma063-check`, removed after use) was created specifically to check chromadb `0.6.3` (the production/Docker pin, `requirements.prod.txt`) in isolation. No live `uvicorn`/`next dev` server was started this session — G10 has no frontend surface and no HTTP-shape change, so the `api` fixture's direct (non-HTTP) calls into the real endpoint functions, plus a from-scratch `ChromaStore` smoke test outside pytest, were judged sufficient; a full HTTP round-trip would have required either an untracked scratch `.env` outside `backend/` or touching `backend/.env`, and CLAUDE.md prohibits creating/editing the real `.env`, so this was avoided rather than worked around. No paid LLM/embedding calls were made (`test_pipeline.py` not run, per CLAUDE.md).

**Diff under validation.** `backend/src/storage/chroma_store.py`, `backend/config.py`, `backend/.env.example`, `backend/api/main.py`, new `backend/tests/test_session_ttl.py`. Matches the plan's file list exactly (`git status --short backend/` — 4 modified + 1 new, no unrelated files).

## Bug chain: reproduce → fix → reproduce → verify

G10 is a behavior-change spec rather than a crash bug, so "the original failure" is the creation-only anchor itself (a session's `created_at` never updates and no `last_activity_at` field exists at all — confirmed as CODE in the spec, now re-confirmed live).

| Step | Evidence |
|---|---|
| 1. Reproduce original behavior | `git worktree add /tmp/g10-before main` (pristine `834a94a`). Direct `ChromaStore` probe (temp dir, no models): created a collection, waited 1s, called `add()`. Result: `at creation: {'created_at': ..., 'hnsw:space': 'cosine'}`; `after add 1s later:` — **same `created_at`, no `last_activity_at` key at all**. `store.cleanup_expired(24)` (old 1-arg signature) ran without error, confirming the pre-fix signature. Also: copying `test_session_ttl.py` into that pristine worktree and running it there gives **7 failed / 1 passed** (`KeyError: 'last_activity_at'`, `TypeError: unexpected keyword argument 'max_lifetime_hours'`) — confirms the new suite genuinely exercises the changed behavior, not just the happy path. (The 1 pass, `test_validation_failure_does_not_touch_activity`, is unrelated pre-existing validation behavior, correctly unaffected either way.) |
| 2. Apply fix | Branch diff (above), already implemented in `IMPL-G10-2026-09-27`. |
| 3. Reproduce same scenario | Identical direct-`ChromaStore` probe against the current branch. |
| 4. Verify behavior changed | `at creation: {'last_activity_at': ..., 'created_at': ..., 'hnsw:space': 'cosine'}` — equal. `after add()`: `created_at` unchanged, `last_activity_at` advanced to the `add()` call's time. `after query()`: `created_at` still unchanged, `last_activity_at` advanced again. `test_session_ttl.py` on the branch: **8/8 pass**, re-run 3× standalone with no flake. |
| 5. Verify no regression | `test_session_ttl.py` + `test_upload_concurrency.py` + `test_upload_dedup.py` + `test_upload_skipped_files.py` → **42/42 pass**, fresh run this session (not reused from implementation). CI command `pytest tests/test_embedder.py tests/test_web_loader.py -v` → **32 passed**, exit 0. `test_pipeline.py` **not run** (needs a live LLM key; CLAUDE.md forbids running it without approval). |

## chromadb `0.6.3` parity check (U1 — carried forward from spec/plan as a pre-merge risk)

Scratch venv, `pip install chromadb==0.6.3`, against a throwaway persist dir:
- `get_or_create_collection` called twice against the same name with different `metadata=` on the second call: **metadata unchanged after the second call** — same freeze-on-existing-collection behavior as 1.5.9.
- `collection.modify(metadata={"hnsw:space": ..., ...})`: raises `ValueError: Changing the distance function of a collection once it is created is not supported currently.` — identical to 1.5.9.
- `collection.modify(metadata={...without hnsw:space...})`: succeeds and updates the stored metadata — identical mechanism to 1.5.9.

**Result: no divergence found.** U1 is resolved, not just carried forward — `_touch_activity`'s mechanism (read-merge-write via `modify()`, dropping `hnsw:space`) is confirmed portable to the production pin. This was the one open risk flagged in the plan as a precondition for mergeability; it is now cleared.

## Acceptance criteria (docs/specs/G10.md)

| AC | Requirement(s) | Status | Evidence |
|---|---|---|---|
| AC1 | R1, R5 | VERIFIED | `test_new_collection_activity_equals_creation`; live probe (bug-chain step 4) confirms equality with a real chromadb 1.5.9 instance, not just the stub. |
| AC2 | R1 | VERIFIED | `test_add_advances_last_activity` (fake clock); live probe confirms `last_activity_at` moves on `add()` while `created_at` doesn't. |
| AC3 | R1 | VERIFIED | `test_query_advances_last_activity` (fake clock); live probe confirms the same via `query()`. |
| AC4 | R2 | VERIFIED | `test_idle_timeout_expires_despite_recent_creation` — idle past the TTL window but within the hard cap is deleted. |
| AC5 | R3 | VERIFIED | `test_hard_cap_expires_despite_recent_activity` — fresh activity but past the hard cap is deleted anyway. |
| AC6 | R4 | VERIFIED | `test_within_both_windows_survives_outside_both_deleted_once` — inside both windows survives; outside both is deleted exactly once, no exception, correct count. |
| AC7 | R7 | VERIFIED | `test_validation_failure_does_not_touch_activity` — an invalid `session_id` on `/query` and an over-limit `/upload` both fail before reaching the store (`HTTPException` raised, no collection created for the attempted session). |
| AC8 | R8 | VERIFIED | `test_upload_concurrency.py` (8 tests) and `test_upload_dedup.py` (9 tests) pass unmodified — G01/G27 store-level behavior (`_add_lock`, id assignment, content-hash dedup) untouched. |
| AC9 | R6 | VERIFIED | `git diff` review: `/upload`, `/upload-url`, `/query` response-building code in `main.py` is untouched; `test_upload_concurrency.py::test_sequential_new_and_append_response_contract` and `test_upload_skipped_files.py` (which assert exact response key sets) still pass unmodified. |
| AC10 | R9 | VERIFIED | `backend/.env.example` read directly: `SESSION_TTL_HOURS`'s comment now states "idle timeout... since its last /upload or /query", and `SESSION_MAX_LIFETIME_HOURS=168` is present with a comment stating it's measured from creation and that whichever fires first wins. |
| AC11 | — | VERIFIED | `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/`: 32 passed, exit 0 (bug-chain step 5). Neither file was touched by this change. |

No AC is UNVERIFIED, PARTIALLY VERIFIED, or FAILED. (No browser/UI-style gap exists for this item — G10 has no frontend surface.)

## Definition of Done — G10

- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G10.md` `Status: APPROVED` (2026-09-27, owner via AskUserQuestion).
- [x] Implementation plan created — APPLICABLE+VERIFIED — `docs/implementation/G10-plan.md`.
- [x] Code implemented — APPLICABLE+VERIFIED — diff above; matches every plan row (one implementation-level deviation from the plan's exact `modify()` call, documented in the plan's Implementation outcome note and in code comments — the `hnsw:space` rejection — not a spec/approach change).
- [x] Unit tests pass — APPLICABLE+VERIFIED — `test_session_ttl.py` 8/8, re-run fresh this session and 3× for flake-check (bug-chain step 4).
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — `test_upload_concurrency.py` 8/8, `test_upload_dedup.py` 9/9, `test_upload_skipped_files.py` 17/17 (bug-chain step 5).
- [x] Integration tests pass (where applicable) — APPLICABLE+VERIFIED — `api`-fixture-driven calls into the real endpoint functions (AC7); direct `ChromaStore` probes against a real chromadb instance (not only the stubbed fixtures).
- [x] Original bug reproduced before fix — APPLICABLE+VERIFIED — bug-chain step 1 (pristine `main` worktree; live probe shows no `last_activity_at` field and a frozen `created_at`; new suite fails 7/8 against pre-fix code).
- [x] Original bug verified fixed — APPLICABLE+VERIFIED — bug-chain step 4 (same probe, branch: `last_activity_at` present and advancing, `created_at` stable).
- [x] Acceptance criteria verified — APPLICABLE+VERIFIED — AC1–AC11 all VERIFIED (table above); no partial or unverified item.
- [x] Regression check performed — APPLICABLE+VERIFIED — full keyless suite 42/42 (bug-chain step 5); `test_pipeline.py` deliberately not run (needs a paid API key, CLAUDE.md).
- [x] Diff reviewed — APPLICABLE+VERIFIED — `git status --short backend/` matches the plan's file list exactly; no file outside `backend/{api,config.py,.env.example,src,tests}` touched.
- [x] No unrelated changes — APPLICABLE+VERIFIED — same diff review; no drive-by refactors, renames, or unrelated edits in the 5 changed/new files.
- [x] Documentation updated (where necessary) — APPLICABLE+VERIFIED — `docs/implementation/G10-plan.md` Implementation outcome note, this validation doc, session handoffs, `.env.example`.
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — out of scope for this session (Phase 1 validation only); belongs to review/PR-preparation.
- [ ] Branch pushed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not done this session, same reason.
- [ ] PR created (where applicable) — APPLICABLE+NOT_YET_VERIFIED — not done this session, same reason.
- [ ] CI passed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — no PR/CI run exists yet; the CI *command* was run locally and passed (AC11), but the actual GitHub Actions run has not executed.
- [ ] Review completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — no PR open yet.
- [ ] Merge completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — a human merges (CLAUDE.md); not this session's action.
- [ ] Post-merge verification completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — follows merge.
- [ ] Branch cleanup completed (where applicable) — APPLICABLE+NOT_YET_VERIFIED — follows merge.
