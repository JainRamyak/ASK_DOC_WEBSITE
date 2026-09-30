# Handoff: SPEC-G29-2026-09-30

SESSION TYPE: SPECIFICATION · Item G29 (provider 429/503 shown as generic 500) · Branch `docs/G05-answer-path-observations`.

CURRENT STATE: SPEC_VERIFIED. `docs/specs/G29.md` Status VERIFIED; not yet APPROVED (needs explicit owner approval).

DECISION: resolved by owner (Option 1): provider 429 → HTTP 429 fixed message; provider 503/overload → HTTP 503 fixed message; no retry, no settings, no frontend change. Recorded in `docs/DECISIONS.md`.

CHANGED: created `docs/specs/G29.md`; appended to `docs/DECISIONS.md`; updated G29 rows in `docs/PROJECT_BACKLOG.md`; this handoff. No code touched, nothing committed, no provider call made.

OPEN / UNKNOWN: exception classes and status attributes of the four SDKs are unverified (none installed locally; spec requires duck-typed status read and planning must confirm in a scratch env). `requirements.prod.txt` pins mistralai 2.4.2 vs 2.9.4 in `requirements.txt` (pre-existing, not fixed). The two message strings were drafted by me; approval covers them.

NEXT: owner approves spec (Status → APPROVED), then `implementation-planning` for G29.
