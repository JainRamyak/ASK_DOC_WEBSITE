# Implementation Plan: G10 — Session TTL anchor (activity + hard cap)

Session: PLAN-G10-2026-09-27 · Branch `fix/G10-ttl-activity-anchor` (base `main` @ `834a94a`, verified equal to `origin/main`) · Spec `docs/specs/G10.md` (APPROVED)

## Implementation outcome (IMPL-G10-2026-09-27)
Implemented as designed below, with one real deviation discovered while writing `_touch_activity`: `collection.modify()` on chromadb 1.5.9 rejects **any** metadata dict that contains the `hnsw:space` key at all — not just a changed value — raising `ValueError: Changing the distance function of a collection once it is created is not supported currently.` This wasn't caught by the plan's earlier empirical checks (those checks happened to omit `hnsw:space` from the `modify()` call). Fixed by having `_touch_activity` pop `hnsw:space` before calling `modify()`; harmless, since the distance function is fixed at creation regardless and can never be changed via this method anyway — the collection's actual index behavior is unaffected, only its `.metadata` mirror of that setting is lost after the first activity touch. All 8 new tests pass, plus the 34 existing G01/G02/G27 regression tests (unmodified) and the CI command (32 tests). `backend/tests/test_pipeline.py` was not run (needs an LLM key; CLAUDE.md). A real `ChromaStore` (temp dir, no models) was also smoke-tested directly outside pytest: `created_at` stays fixed across `add()`/`query()`, `last_activity_at` advances on each.

## Context
`docs/specs/G10.md` (APPROVED, Option 3, D-U01 resolved 2026-09-27) requires: a session expires `SESSION_TTL_HOURS` after its **last activity** (idle timeout, not the current creation-only anchor), or `SESSION_MAX_LIFETIME_HOURS` (new setting, default 168h/7 days) after **creation**, whichever fires first.

Confirmed empirically against the installed `chromadb==1.5.9` (dev/CI pin, `backend/requirements.txt`) before writing this plan:
- `ChromaStore.get_or_create_collection()`'s `metadata=` argument is silently ignored once a collection already exists — `created_at` is frozen at first creation and never updated by any later call. This is why the store needs a way to update metadata on an *existing* collection.
- `collection.modify(metadata=...)` does update stored metadata on an existing collection, but **replaces the dict wholesale** — a `modify()` call that omits an existing key (e.g. `hnsw:space`) drops it. Any write must read-merge-write the full existing metadata.

Incidental finding while reading `pipeline.py` for this plan (informational only, not a code change here): `AskMyDocsPipeline.ask()` already has a `no_session` reason path (`pipeline.py:193-199`, guards on `chroma_store.session_exists()` before ever calling `retrieve_and_rerank`/`query()`). This resolves the spec's Unknown U2 — the path exists. It also means a query against an already-expired session never reaches `ChromaStore.query()` at all, so it can never spuriously extend that session's liveness — this plan doesn't need to add any extra guard for that case.

## Design

### 1. `backend/src/storage/chroma_store.py` — core change
- **`get_or_create_collection`** (currently lines 32-36): stamp both `created_at` and `last_activity_at` to the same `now = time.time()` value in the `metadata=` dict passed to `get_or_create_collection`. Only affects first creation (confirmed: ignored on the "get" path), satisfying R5 — a never-touched-again session still has a `last_activity_at` equal to its `created_at`.
- **New private helper**, `_touch_activity(self, collection) -> None`:
  ```python
  def _touch_activity(self, collection) -> None:
      metadata = dict(collection.metadata or {})
      metadata["last_activity_at"] = time.time()
      collection.modify(metadata=metadata)
  ```
  Single place implementing the read-merge-write required by `modify()`'s wholesale-replace behavior (R1).
- **`add`** (currently lines 38-96): call `self._touch_activity(collection)` as the last statement inside the existing `with self._add_lock:` block, after the `if keep:` branch, before `return newly_added_hashes`. Runs on every call that reaches this point — including an all-duplicate (G27) upload, since the store operation genuinely ran. A request that raises before `add()` is even entered (e.g. `main.py`'s validation `HTTPException`s) never reaches this line — satisfies R7.
- **`query`** (currently lines 98-104): call `self._touch_activity(collection)` after `collection.query(...)` returns successfully, before `return`. If `self.client.get_collection(...)` raises (`NotFoundError`, session already gone), the method never reaches the touch — R7 preserved. No lock needed here (`query()` isn't locked today, and the spec's Edge Cases explicitly accepts last-writer-wins for concurrent activity writes).
- **`cleanup_expired`**: change signature from `cleanup_expired(self, ttl_hours: int) -> int` to `cleanup_expired(self, ttl_hours: int, max_lifetime_hours: int) -> int`. New body:
  ```python
  def cleanup_expired(self, ttl_hours: int, max_lifetime_hours: int) -> int:
      now = time.time()
      idle_cutoff = now - ttl_hours * 3600
      lifetime_cutoff = now - max_lifetime_hours * 3600
      deleted = 0
      for coll in self.client.list_collections():
          meta = coll.metadata or {}
          created_at = meta.get("created_at")
          last_activity_at = meta.get("last_activity_at", created_at)
          idle_expired = last_activity_at is not None and last_activity_at < idle_cutoff
          lifetime_expired = created_at is not None and created_at < lifetime_cutoff
          if idle_expired or lifetime_expired:
              self.client.delete_collection(coll.name)
              deleted += 1
      if deleted:
          logger.info("Cleanup: removed %d expired session(s)", deleted)
      return deleted
  ```
  `last_activity_at` falls back to `created_at` when absent — covers collections created before this change ships (no `last_activity_at` key yet), same "old-schema tolerance" precedent G27 already set for `content_hash`. Strict `<` on both comparisons, matching today's style. Return-value and logging contract unchanged (R2/R3/R4).

### 2. `backend/config.py`
Add, immediately after `session_ttl_hours` (line 80), same pattern:
```python
session_max_lifetime_hours: int = int(_optional("SESSION_MAX_LIFETIME_HOURS", "168"))
```
No other setting touched. No ad hoc `os.getenv` (CLAUDE.md).

### 3. `backend/.env.example`
Update the `SESSION_TTL_HOURS=24` line's surrounding comment to state it now measures idle time (last activity), and add directly below it:
```
# Absolute cap on a session's lifetime from creation, independent of
# activity. A session expires at whichever of SESSION_TTL_HOURS (idle)
# or this fires first.
SESSION_MAX_LIFETIME_HOURS=168
```
(R9/AC10)

### 4. `backend/api/main.py`
- `_session_cleanup_loop` (currently lines 31-41): change the call to
  `await run_in_threadpool(pipeline.chroma_store.cleanup_expired, settings.session_ttl_hours, settings.session_max_lifetime_hours)`.
- Startup log line (currently lines 47-50): add `max_lifetime_hours=%d` to the format string and args.
- No route handler changes — `/upload`, `/upload-url`, `/query` call the same pipeline/store methods; the activity write is inside `chroma_store.add()`/`query()` (R6: response shapes unchanged).

## Requirement/AC → Change → Test → Verification

| Spec req/AC | Code change | Test | Verification |
|---|---|---|---|
| R5, AC1 | `get_or_create_collection` stamps both timestamps at creation | `test_session_ttl.py::test_new_collection_activity_equals_creation` | pytest |
| R1, AC2 | `ChromaStore.add()` calls `_touch_activity` | `test_session_ttl.py::test_add_advances_last_activity` (fake clock) | pytest |
| R1, AC3 | `ChromaStore.query()` calls `_touch_activity` | `test_session_ttl.py::test_query_advances_last_activity` (fake clock) | pytest |
| R2, AC4 | `cleanup_expired` idle-timeout branch | `test_session_ttl.py::test_idle_timeout_expires_despite_recent_creation` | pytest |
| R3, AC5 | `cleanup_expired` hard-cap branch | `test_session_ttl.py::test_hard_cap_expires_despite_recent_activity` | pytest |
| R4, AC6 | `cleanup_expired` OR logic | `test_session_ttl.py::test_within_both_windows_survives_outside_both_deleted_once` | pytest |
| Legacy fallback (Constraints) | `last_activity_at = meta.get(..., created_at)` | `test_session_ttl.py::test_missing_last_activity_falls_back_to_created_at` | pytest |
| R7, AC7 | none (failure paths in `main.py` already return before touching the store) | `test_session_ttl.py::test_validation_failure_does_not_touch_activity` | pytest, via `api` fixture |
| R8, AC8 | none — `_add_lock`, id-assignment, G27 dedup untouched | run `test_upload_concurrency.py`, `test_upload_dedup.py` unmodified | pytest |
| R6, AC9 | none — response building untouched | reuse existing response-shape assertions from `test_upload_concurrency.py`'s contract test | pytest |
| R9, AC10 | `.env.example` | — | read the file |
| AC11 | — | — | `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` (CI command; unaffected by this change and doesn't run the new/upload test files today — pre-existing gap, G06, not this spec's job) |

## Files
- `backend/src/storage/chroma_store.py` — `get_or_create_collection`, new `_touch_activity`, `add`, `query`, `cleanup_expired`
- `backend/config.py` — `session_max_lifetime_hours`
- `backend/.env.example` — new var + updated comment
- `backend/api/main.py` — `_session_cleanup_loop` call + log line
- `backend/tests/test_session_ttl.py` — new

## New test file design: `backend/tests/test_session_ttl.py`
Keyless. Most cases build a `ChromaStore` directly against a `tmp_path` persist dir (no FastAPI stub harness needed for pure store-level behavior); the AC7 regression case reuses the `api`/`api_main` fixtures from `test_upload_concurrency.py` (imported the same way `test_upload_dedup.py` already does).
- Time control: monkeypatch `src.storage.chroma_store.time.time` to a small controllable counter (same stubbing style already used for models in `test_upload_concurrency.py`) for the "does last_activity_at move" cases (AC2/AC3). The cutoff-comparison cases (AC4/AC5/AC6/legacy-fallback) instead build a collection normally, then call `collection.modify(metadata={...})` directly to backdate timestamps — closer to a real aged session than mocking `time.time` for the whole test, and exercises the same `modify()` mechanism R1 relies on.
- AC7: send a `/query` with an invalid `session_id` (triggers existing `_validate_client_session_id`, 400) and an `/upload` exceeding `max_files_per_upload` (400); assert no collection exists afterward for either attempted session — both fail before any `chroma_store` call, so there's nothing to have touched.

## Risks / notes
- **U1 carried from spec, not resolved by this plan**: chromadb `0.6.3` is the production/Docker pin (`backend/requirements.prod.txt`); this plan's empirical checks (`get_or_create_collection` metadata-freeze, `modify()` wholesale-replace) were only run against `1.5.9` (dev/CI). Before merging, run the same two throwaway checks against an isolated `chromadb==0.6.3` install. If `modify()` behaves differently there, that's a **BLOCKED** condition back to `specification` for re-approval, not a silent workaround.
- `list_collections()` (used by `cleanup_expired`, pre-existing, unmodified by this plan) takes optional `limit`/`offset` params; this plan doesn't touch its call site or that behavior — noted only because it's adjacent code, not a new finding introduced by this change.

## Verification (end-to-end)
1. `cd backend && pytest tests/test_session_ttl.py tests/test_upload_concurrency.py tests/test_upload_dedup.py tests/test_upload_skipped_files.py -v` — all green.
2. CI parity: `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` exits 0 (AC11; this file doesn't touch either module).
3. Manual: run the backend locally (local embedder, no key), upload a file, query it, inspect `pipeline.chroma_store.client.get_collection(f"session_{sid}").metadata` directly to see `last_activity_at` advance on each call.
4. The chromadb `0.6.3` parity check (Risks) before this branch is considered mergeable.
