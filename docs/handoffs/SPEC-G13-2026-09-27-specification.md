# Handoff: SPEC-G13-2026-09-27

SESSION ID: SPEC-G13-2026-09-27 (session named "PhaseB_G13")
SESSION TYPE: SPECIFICATION
OBJECTIVE: Write and verify the specification for G13 (raw exception text returned to clients in HTTP 500 details).

CURRENT STATE: SPEC_VERIFIED + human approval → READY_FOR_IMPLEMENTATION (`docs/specs/G13.md`, `Status: APPROVED`)

WORK COMPLETED:
- Confirmed G13 is an existing, unspec'd backlog ID (`docs/PROJECT_BACKLOG.md`) with prior evidence in `docs/project-assessment/03-runtime-behavior.md` §4, `06-gap-analysis.md`, and `05-requirements.md` (REQ-E16 vs REQ-B10 conflict).
- Re-read `backend/api/main.py` (all three 500 sites in `/upload`, `/upload-url`, `/query`, plus `/feedback`'s existing safe 500), `backend/src/generation/answer_chain.py` (exception types/messages per provider), `backend/src/pipeline.py:222` (confirmed `answer()`/config errors are reachable only via `/query`, never from ingestion), and `frontend/lib/api.ts` (`humanizeError`, `parseErrorDetail` — confirmed the client already displays `detail` verbatim, no frontend change needed).
- Raised the backlog's flagged decision (error-mapping granularity) to the owner via `AskUserQuestion` rather than guessing: resolved as (1) a distinct `503` for LLM-configuration errors on `/query`, generic `500` for everything else, and (2) one shared generic message string across all three routes (not per-route wording).
- Drafted `docs/specs/G13.md` with Problem, Current Behavior, Expected Behavior, Evidence, Reproduction, Root Cause, Scope, Out of Scope, 7 Requirements, 8 Acceptance Criteria, Edge Cases, Regression Requirements, Relevant Components, Constraints, Unknowns, Assumptions, Verification Strategy.
- Ran the verify pass in-session (checked AC testability, scope-vs-evidence match, assumption labeling, no unresolved blocking unknowns) and set `Status: VERIFIED`.
- Sought explicit owner approval via `AskUserQuestion`; approved. Set `Status: APPROVED`.
- Updated `docs/DECISIONS.md` with the DECISION REQUIRED/DECISION pair for this session.
- Updated `docs/PROJECT_BACKLOG.md` G13 entry: status, required-specification, and business-priority lines now point at the approved spec/decision.

FILES CHANGED: none in application, config, CI, or deploy files (specification only — no implementation this session).

ARTIFACTS CREATED / UPDATED:
- docs/specs/G13.md (new, Status: APPROVED)
- docs/DECISIONS.md (appended one DECISION REQUIRED / DECISION pair)
- docs/PROJECT_BACKLOG.md (G13 entry updated)
- docs/handoffs/SPEC-G13-2026-09-27-specification.md (this file)

EVIDENCE:
- Code read only (`backend/api/main.py`, `backend/src/generation/answer_chain.py`, `backend/src/pipeline.py`, `frontend/lib/api.ts`). No backend commands run — `venv/` lacks pytest/uvicorn per `CLAUDE.md`'s existing "Not verified" note; not needed for a code-read specification pass.
- Confirmed by code-read: `/upload` and `/upload-url` never reach `answer_chain.py`, so the 503 config-error branch applies only to `/query`.

DECISIONS:
- RESOLVED (owner, this session): error-mapping granularity — distinct 503 for `/query` configuration errors, one shared generic 500 message for all other cases across all three routes. See `docs/DECISIONS.md` and `docs/specs/G13.md` Evidence/Expected Behavior.

UNKNOWNS (carried into implementation-planning):
- Whether `test_pipeline.py` (not run in CI) references any current raw error string in a way this change would break.
- Whether `TestClient` is available for backend route-level tests (per `CLAUDE.md`'s existing note) — implementation-planning must confirm.
- Exact mechanism for distinguishing the unknown-`LLM_PROVIDER` `ValueError` from unrelated `ValueError`s (message-prefix check vs. a dedicated exception type in `answer_chain.py`) — left open by design (spec states the requirement, not the mechanism); implementation-planning decides.

NEXT REQUIRED HUMAN ACTION: none — spec is APPROVED.
NEXT OBJECTIVE: Run `implementation-planning` for G13 against `docs/specs/G13.md`.
