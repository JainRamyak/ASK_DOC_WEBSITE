# Handoff: PhaseB_G11-2026-09-27

SESSION ID: PhaseB_G11-2026-09-27
SESSION TYPE: SPECIFICATION (draft + verify, one pass)
OBJECTIVE: Write and verify `docs/specs/G11.md` for `DELETE /sessions/{session_id}` skipping input validation.

CURRENT STATE: SPEC APPROVED (owner approved in this session via AskUserQuestion)

WORK COMPLETED:
- Re-read `backend/api/main.py` (`_validate_client_session_id`, the `delete_session` route, and its three sibling routes that already call the helper), `backend/src/storage/chroma_store.py` (`delete_session`), and `frontend/lib/api.ts`/`frontend/app/app/page.tsx` (the `deleteSession` call site).
- Confirmed the root cause: `_validate_client_session_id` exists and is wired into `/upload`, `/upload-url`, `/query`, but never into the `DELETE` route — a straightforward omission, not a deliberate design choice.
- New fact beyond `PROJECT_BACKLOG.md`'s note that the frontend caller was "unverified beyond 04": the frontend *does* call `DELETE /sessions/{id}` (`frontend/lib/api.ts:126`, from `page.tsx:148`), but never reads the response status or body — only a thrown network error is caught. This removes the frontend-regression risk for changing the invalid-format case's status code.
- Confirmed `D-U05` (gating the `/feedback` half of G11) is still unresolved (`docs/DECISIONS.md` has no entry for it), so scoped this spec to the `DELETE` half only, per the backlog's own dependency note. `/feedback` is explicitly Out of Scope, not silently dropped.
- Wrote `docs/specs/G11.md`: Problem, Current Behavior (with exact code citations and line numbers), Expected Behavior, Evidence, Reproduction (4 steps, keyless), Root Cause, Scope, Out of Scope, Requirements (R1–R4), Acceptance Criteria (AC1–AC7, each independently checkable), Edge Cases, Regression Requirements, Relevant Components, Constraints, Unknowns (U1: chromadb's exact exception for names it rejects outright — moot for the fix since a UUID string is always chromadb-safe; U2: exact FastAPI decoding of an encoded-slash path segment), Assumptions (A1, A2), Verification Strategy.
- Self-verified: every AC traces to a Requirement and is independently testable; Scope/Out-of-Scope don't contradict; no Unknown blocks writing or checking the ACs. Set `Status: VERIFIED`.
- Presented to the owner via `AskUserQuestion`; approved. Set `Status: APPROVED (2026-09-27, owner approval in this session)`.

FILES CHANGED: docs only.

ARTIFACTS CREATED / UPDATED:
- docs/specs/G11.md (new; DRAFT → VERIFIED → APPROVED, all in this session)
- docs/handoffs/PhaseB_G11-2026-09-27-spec.md (this file)

Not touched this session (left as-is): `docs/PROJECT_BACKLOG.md` G11 entry still says `OPEN` — the backlog's status column should probably move to reflect "DELETE half spec'd" once implementation starts; left for the implementation-planning session to update alongside the plan, rather than editing the backlog mid-spec.

EVIDENCE:
- Code re-read 2026-09-27 at `main` @ `834a94a` (see spec's Evidence section for exact files/lines).
- Not run: chromadb is not installed in this session's `venv/` (per CLAUDE.md "Not verified"); the spec's Unknowns/Verification Strategy defer the actual test run to implementation.

DECISIONS: none new. `D-U05` remains open and untouched (tracked in `docs/PROJECT_BACKLOG.md`, not re-raised here).

UNKNOWNS: U1 (chromadb exception type for names it would reject outright — doesn't block, the fix moots it), U2 (exact path-decoding behavior for an encoded slash — left to the implementation phase's real test run).

NEXT REQUIRED HUMAN ACTION: none — spec is already APPROVED.
NEXT OBJECTIVE: run `implementation-planning` for G11 (DELETE-half only). That session will need `pytest`/`fastapi`/`chromadb` available to write and run AC1–AC7 as tests (currently absent from `venv/`, same gap noted in prior G01/G02/G27 handoffs).
