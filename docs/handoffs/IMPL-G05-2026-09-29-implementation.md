# Handoff: IMPL-G05-2026-09-29

SESSION TYPE: IMPLEMENTATION (free part only) · Spec `docs/specs/G05.md` (APPROVED) · Branch `docs/G05-answer-path-observations` from `main` @ `09432cb`.

CURRENT STATE: Plan persisted; free precheck done; **paid live run not started — awaiting owner confirmation (provider, key via process env, ≤ 20 calls).** Nothing committed.

DONE:
- Created branch; persisted `docs/implementation/G05-plan.md` (copy of the plan; the plan-mode exit had been declined and the owner then chose "accept plan, start free part").
- Ran the free precheck with a throwaway script in the scratchpad (not in the repo): 0 provider calls; all candidate questions gate as intended; session deleted.
- Wrote `docs/implementation/G05-observations.md` (precheck section only).

FILES CHANGED (docs only): `docs/implementation/G05-plan.md`, `docs/implementation/G05-observations.md`, `docs/handoffs/IMPL-G05-2026-09-29-implementation.md`. No `backend/`/`frontend/` changes.

DEVIATION: precheck used a scratchpad Chroma dir via `CHROMA_PERSIST_DIR` rather than the default store (less side effect than the plan said).

NEXT (owner action): decide the provider and, in this session shell, `! export <PROVIDER>_API_KEY=… LLM_PROVIDER=…` (never paste the key into chat), then confirm the 20-call cap. Then I write and run the live driver (O1–O7, ~8 calls), finish the observations file, and apply evidence-driven status updates (R8). After that: validation-and-review.

## Update — live run attempt (Mistral)
Owner supplied provider = Mistral and the key in chat. Run: 8 provider calls, all HTTP 429 "Rate limit exceeded" (code 1300) from the first call; O5 (gate-only) observed with 0 calls; O1–O4, O6, O7 NOT observed. Stopped, no retries. Deviation: driver did not abort on the first 429 (7 extra rejected calls). Key not written to any file (repo grep clean; `backend/`, `frontend/` untouched). Details in `docs/implementation/G05-observations.md`.
NEXT (owner): check the Mistral console for quota/limits (or supply another key/provider), and rotate the pasted key. Then re-run the live phase with abort-on-first-429; remaining budget ≤ 12 calls of the 20 cap.

## Update — live run attempt 2 (Gemini)
Owner switched to Gemini (key in chat; again not written to any file). 8 calls: 6× 503 "high demand", then 429 free-tier quota (5 req/min/model). No answer observed; O5 gate control observed again. Findings and the pacing correction are in `docs/implementation/G05-observations.md`.
NEXT (owner decision): one more paced attempt (≥ 13 s between calls, stop on first 429/503) on Gemini — possibly with a model override such as a stable Flash model via `GEMINI_MODEL`, if `gemini-3.6-flash` stays overloaded — or a paid/higher-quota key. Rotate both pasted keys (Mistral and Gemini).

## Update — live attempt 3 (Gemini, paced)
1 call, 503 "high demand" on `gemini-3.6-flash`, stopped by design. Gemini total 9/20. Awaiting owner decision on a `GEMINI_MODEL` override (the single override the spec allows) or another provider/key. Key not on disk.

## Update — live attempt 4 (Gemini) SUCCEEDED; implementation complete
Default `gemini-3.6-flash`, paced, 8 calls (Gemini total 17/20; Mistral 8, all 429). Grounded cited answers, exact refusals (3/3), rewrite, gate control all observed; model ID valid. Evidence in `docs/implementation/G05-observations.md`. Statuses updated only for Gemini: backlog G05/V-F16/D-U09, F12, F16, REQ-U09, G03 and G04 Unknowns. Not observed: Mistral, OpenAI, Anthropic; UI; `/query` mapping of provider errors.
Key not in any file; `backend/`, `frontend/` untouched; nothing committed. Rotate the Mistral and Gemini keys pasted in chat.
NEXT: `validation-and-review` for G05.
