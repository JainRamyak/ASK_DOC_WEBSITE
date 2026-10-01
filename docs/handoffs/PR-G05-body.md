## Summary

G05 is an **evidence run, not a code change**: until now no real LLM answer had ever been observed for any provider, so the product's headline behavior (cited, grounded answers) and the claims in G03/G04/V-F16/REQ-U09 rested on source reading. This PR adds the spec, plan, observations, and validation for a bounded, owner-approved keyed run. **No file under `backend/`, `frontend/`, config, CI or deploy is touched.**

Implements `docs/specs/G05.md` (`Status: APPROVED`). Owner decisions: one provider first, ≤ 20 provider calls per provider, spend re-confirmed at run time.

## What was observed (details: `docs/implementation/G05-observations.md`)
- **Gemini `gemini-3.6-flash` (default), N=1 per question:** 4 grounded answers correct, each cited `[1]` (in range), sources numbered, PDF source carried `page`; 3/3 related-but-unanswered questions returned the exact refusal sentence (`grounded:false`, `sources:[]`); an unrelated question was rejected by the gate with 0 provider calls; query rewriting worked once ("When was it first released?" → "When was Python first released?"). Default model ID valid.
- **OpenAI SDK path against Groq's compatible API (`openai/gpt-oss-20b`)**, through the real `/query` handler: same behavior. Not OpenAI itself. 1 of 8 repeats used a full-width `【1】` marker instead of `[1]` (noted on G30).
- Earlier failed attempts are kept as they happened: Mistral 429 on 8/8 calls; Gemini 503 "high demand" then free-tier 429 (5 req/min).
- This evidence produced G29 (provider 429/503 → distinct statuses, now merged as #13) and G30 (uncited chunks shown as sources).

## Validation (`docs/implementation/G05-validation.md`, incl. 2026-10-01 re-validation)
- AC1–AC9 VERIFIED (AC2: each provider ≤ 20 calls; Gemini 17, Mistral 8, Groq 17).
- Key search over the repo found no key material; scratch sessions deleted after every run.
- CI command 32 passed; full key-free backend suite 148 passed (run on the G29 branch).

## Not verified / for the reviewer
- Mistral (never responded), OpenAI proper, Anthropic; the UI; single samples on one model.
- Spec wording says "≤ 20 calls total" while the recorded decision says "per provider" — please confirm the latter.
- Raw run records for the Mistral/Gemini attempts were lost (scratch dir cleared); the observations file keeps verbatim answers.
- Three provider keys were pasted in chat during the runs (never written to any file) — they should be rotated.

## Scope of this PR
Only the G05 documents (spec, plan, observations, validation, handoffs, this body). Deliberately **not** included: the shared, untracked `docs/DECISIONS.md`, `docs/PROJECT_BACKLOG.md` and `docs/project-assessment/` (their G05-related edits stay local, per the convention of the G03/G04 PRs).

CI: this PR touches no `backend/**` path, so the `backend-tests` workflow is not expected to run (NOT a pass; no CI evidence for this change).
