# Implementation Plan: G11 — `DELETE /sessions/{session_id}` skips input validation

Session: PLAN-G11-2026-09-27 · Branch `fix/G11-delete-session-validation` (base `main` @ `834a94a` at plan time, confirmed equal to `origin/main` via `git fetch`; rebased onto `main` @ `171a098` during implementation after G10 merged — see Implementation outcome) · Spec `docs/specs/G11.md` (APPROVED)

## Implementation outcome (IMPL-G11-2026-09-27)
Implemented exactly as designed below — no plan row required revision. All 6 new tests in `backend/tests/test_delete_session.py` pass, plus 42 existing regression tests across `test_upload_concurrency.py`, `test_upload_skipped_files.py`, `test_upload_dedup.py`, and `test_session_ttl.py` (the last added by G10, merged to `main` mid-session — see below), and the CI command (32 tests). `backend/tests/test_pipeline.py` was not run (needs an LLM key; CLAUDE.md).

**Concurrent-session note**: while this session held uncommitted changes on `fix/G11-delete-session-validation`, another session in this same shared working directory was running G10's post-merge-verification and needed to switch to `main`. It stashed this session's WIP first (visible stash message: "G11 WIP (delete_session validation) - preserved before G10 post-merge-verification switch to main") rather than discarding it, then merged G10 into `main` (`171a098`). On returning, this session recovered the branch, popped the stash cleanly (no conflicts — G10 touched only `_session_cleanup_loop`/`lifespan` in `main.py`, unrelated to `delete_session`), and rebased `fix/G11-delete-session-validation` onto the new `main` tip so the branch reflects current `main`. No work was lost; nothing needed re-doing.

## Context
`docs/specs/G11.md` is APPROVED, scoped to the `DELETE` half only (the `/feedback` half stays out of scope, blocked on the still-open `D-U05` decision). The bug: `_validate_client_session_id` — the UUID-format check already wired into `/upload`, `/upload-url`, and `/query` — was never wired into `DELETE /sessions/{session_id}`. A malformed `session_id` reaches `pipeline.chroma_store.delete_session` unchecked; today most malformed inputs happen to come back as a harmless `200 {"success": false}` (chromadb raises `NotFoundError` for a collection that was never created), but nothing guarantees that for every malformed string, and it's inconsistent with the other three routes for no reason. This plan makes `DELETE` call the same helper, the same way, before touching the store — nothing else changes.

## Design

### 1. `backend/api/main.py` — one-line fix
```python
@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    _validate_client_session_id(session_id)
    deleted = pipeline.chroma_store.delete_session(session_id)
    return {"deleted": session_id, "success": deleted}
```
Reuses `_validate_client_session_id` exactly as `/upload`, `/upload-url`, and `/query` already do — same `HTTPException(400, "Invalid session_id.")` contract, no new helper, no new message. Nothing else in this file changes; `POST /feedback` and `FeedbackRequest` are untouched (spec R4/AC7).

### 2. `backend/tests/test_delete_session.py` — new file
Follows the exact scaffolding `test_upload_skipped_files.py`/`test_upload_dedup.py` already use — no shared `conftest.py` exists in this repo; fixtures are reused module-to-module via import:
```python
from tests.test_upload_concurrency import api_main, api, _seed_session  # noqa: F401
```
Route is called directly (`await api.delete_session(...)`), bypassing HTTP/rate-limiting, matching every other keyless route test in this suite. Tests:

- **`test_invalid_format_rejected_before_store_call`** (AC1, AC2) — parametrized over `"not-a-uuid"`, `"123"`, `"abc%2Fdef"`, and a 250-char garbage string. For each: monkeypatch `api.pipeline.chroma_store.delete_session` to raise `AssertionError` if invoked; assert `pytest.raises(HTTPException)` with `(exc.value.status_code, exc.value.detail) == (400, "Invalid session_id.")`.
- **`test_wellformed_nonexistent_uuid_returns_success_false`** (AC3) — `str(uuid.uuid4())`, never seeded; assert `{"deleted": <id>, "success": False}`.
- **`test_wellformed_existing_uuid_deletes_and_returns_success_true`** (AC4) — `sid = _seed_session(api)`; assert first delete returns `success: True`; assert `session_exists(sid) is False` afterward; a second delete returns `success: False`.
- AC5/AC7 verified by diff review, not a runtime test (see below).

### 3. Unknown U2 (percent-encoded slash at the real HTTP layer)
Non-blocking per the spec. The direct-call unit tests establish that *any* string that isn't a valid UUID is rejected before the store is touched, regardless of what the router hands the function — which is what R1 actually requires. No live-server test was added; the `abc%2Fdef` parametrized case covers the substance without needing one.

## Requirement/AC → Change → Test → Verification

| Spec req/AC | Code change | Test | Verification |
|---|---|---|---|
| R1, AC1 | `_validate_client_session_id(session_id)` added to the route | `test_invalid_format_rejected_before_store_call["not-a-uuid"]` | pytest — PASSED |
| R1, AC2 | same | same test, other 3 parametrized invalid values | pytest — all 4 PASSED |
| R2, AC3 | none (existing behavior, now reached only after validation passes) | `test_wellformed_nonexistent_uuid_returns_success_false` | pytest — PASSED |
| R2, AC4 | none | `test_wellformed_existing_uuid_deletes_and_returns_success_true` | pytest — PASSED |
| R3, AC5 | confined to the one added line | diff review | `git diff backend/api/main.py` — confirmed one line |
| R4, AC7 | none — `/feedback` untouched | diff review | confirmed, no `/feedback`/`FeedbackRequest` lines in the diff |
| AC6 | — | — | `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` — 32 passed |

## Files
- `backend/api/main.py` — one line added to `delete_session`
- `backend/tests/test_delete_session.py` — new (6 tests)

## Risks / notes
- No migration, no config change, no CORS/CI/deploy-config touch.
- `backend/venv` had `pytest`/`fastapi`/`chromadb` importable at implementation time (unlike at spec/plan time) — the environment gap flagged in prior sessions had already been resolved by the time this session ran.

## Verification (end-to-end) — all run
1. `cd backend && venv/bin/python -m pytest tests/test_delete_session.py -v` — 6 passed.
2. Regression: `pytest tests/test_upload_concurrency.py tests/test_upload_skipped_files.py tests/test_upload_dedup.py tests/test_session_ttl.py -v` — 42 passed.
3. CI parity (AC6): `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` — 32 passed.
4. `git diff backend/api/main.py` reviewed — exactly the one added line (AC5, AC7).
5. Not run: `test_pipeline.py` (needs an LLM key; CLAUDE.md) — unrelated to this route regardless.
6. No frontend or manual UI verification needed — spec A2 established the frontend ignores this route's response status entirely.
