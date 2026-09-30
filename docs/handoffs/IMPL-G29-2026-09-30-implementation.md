# Handoff: IMPL-G29-2026-09-30

SESSION TYPE: IMPLEMENTATION · Spec `docs/specs/G29.md` (APPROVED) · Plan `docs/implementation/G29-plan.md` · Branch `fix/G29-provider-429-503-status` (from `main` 09432cb).

STATE: IMPLEMENTED, all plan rows done, not yet validated. Nothing committed.

FILES CHANGED: `backend/src/generation/answer_chain.py`, `backend/api/main.py` (modified); `backend/tests/test_provider_throttling.py` (new); `docs/implementation/G29-plan.md` (new, with outcome section); this handoff.

BEHAVIOR: provider error with int status 429 → HTTP 429 `RATE_LIMIT_ERROR_MESSAGE`; 503/529 → HTTP 503 `BUSY_ERROR_MESSAGE`; all else unchanged. No retry/config/frontend change.

TESTS RUN (scratch venv, no API calls): new 34 pass (13 failed on old code); CI command 32 pass; key-free suite 148 pass. `test_pipeline.py` not run.

OUT-OF-SCOPE FINDINGS: none new. Still open: mistralai pin mismatch (2.9.4 vs 2.4.2 in prod requirements) means the prod-image SDK's `SDKError.status_code` is unchecked.

ENV NOTE: /tmp is a 3.9G tmpfs; the first venv install failed with ENOSPC, rebuilt with CPU-only torch. Scratch venv is outside the repo.

NEXT: `validation-and-review` for G29.
