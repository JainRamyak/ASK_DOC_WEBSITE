# Handoff: VALID-G05-2026-09-29

SESSION TYPE: VALIDATION · `docs/implementation/G05-validation.md`

STATE: VALIDATED (with findings). All 9 ACs verified; AC8/AC9 needed fixes made this session (backlog entry text; new G29/G30 entries). CI command 32 passed; code/config/deploy diff empty; no key in repo or scratchpad.

FINDINGS FOR OWNER: (1) spec says ≤ 20 calls total vs. decision "per provider" — confirm; (2) O1 was asked 3× on Gemini across owner-requested retries (spec: one retry per question); (3) both keys were pasted in chat — rotate; (4) Mistral never observed; F13 stays UNKNOWN.

NOTHING COMMITTED. Docs-only branch `docs/G05-answer-path-observations`; whether to commit/PR is the owner's call.
NEXT: `/review G05`.

## Update 2026-09-30 — audit fixes applied
Stale "unobserved/UNKNOWN" statements reconciled across backlog, feature inventory, requirements and gap analysis (dated UPDATE notes, Gemini-only wording); AC8 re-verified. Unfixable and recorded: R1 cap not re-confirmed in-session; raw output of attempts 1–3 lost. No code changed; G29/G30 remain separate backlog items. Nothing committed. Still open for the owner: confirm per-provider 20-call cap, rotate both pasted keys, decide on commit/PR (see review question).

## Update 2026-10-01 — Groq run (OpenAI-compatible path) + live G29 check
17 calls, details in `docs/implementation/G05-observations.md` (attempt 5). G05 results reproduced on a second model family; new finding: one answer used a full-width `【1】` marker. G29: real 404 → generic 500 with fixed message (observed); no real 429/503 could be provoked (8 rapid calls all 200), so that mapping is still offline-verified only. Key not on disk (verify with grep). Nothing committed, no PR opened; waiting for owner's go.
