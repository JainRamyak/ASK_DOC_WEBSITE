# Handoff: VALID-G29-2026-09-30

SESSION TYPE: VALIDATION · Spec `docs/specs/G29.md` · Branch `fix/G29-provider-429-503-status`.

STATE: VALIDATED. All 9 ACs VERIFIED (AC3 for mistralai 2.9.4 only). Report: `docs/implementation/G29-validation.md`.

EVIDENCE: before/after run with real SDK exception objects (gemini, openai, anthropic) through `query_document`: generic 500 before, 429/503 with the fixed messages after. New tests 34 pass; CI command 32 pass; G13 tests 10 pass; key-free suite 148 pass. No provider API call made; no code changed this session (a temporary repro script was created and deleted).

OPEN: mistralai 2.4.2 (prod image pin) unchecked; no live-provider run; no lint tool; frontend display checked by reading only. Nothing committed or pushed.

NEXT: `review` (PR preparation) for G29, then owner decides on commit/PR.
