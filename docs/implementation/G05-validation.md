# G05 — Validation

Session: VALID-G05-2026-09-29 · Spec `docs/specs/G05.md` (APPROVED) · Plan `docs/implementation/G05-plan.md` · Branch `docs/G05-answer-path-observations` (base `main` @ `09432cb`). G05 is an evidence run (no product code), so "the diff" is docs only and there is no bug reproduce→fix chain (NOT_APPLICABLE).

## Acceptance Criteria

| AC | Result | Evidence |
|---|---|---|
| 1. Observations file has an entry for O1–O7 (or a reason) | **VERIFIED** | `G05-observations.md` attempt 4 table covers O1×2, O3, O4×3, O5, O6, O7; O2 as the marker column plus findings. Attempts 1–3 (Mistral 429, Gemini 503/429) documented with reasons. |
| 2. Provider/model recorded; call count; final ≤ 20 | **VERIFIED against the owner's per-provider cap; spec wording inconsistent** | Recorded: Gemini/`gemini-3.6-flash` 17 calls (9 in runs 2–3, 8 in run 4); Mistral/`mistral-small-latest` 8. Owner chose "≤ 20 per provider" (`DECISIONS.md`), but the spec's Scope/R2 say "≤ 20 total". Total across providers is 25. Flagged, not silently reinterpreted: needs owner acknowledgement (see Findings). |
| 3. O5: `grounded:false`, exact message, no provider call | **VERIFIED** | Runs 2 and 4: `exact_refusal:true`, `calls_this_q:0`, counter unchanged (6→6). |
| 4. O1/O3 `grounded` + sources numbering; `page` for PDF | **VERIFIED** (Gemini, N=1 each) | O1/O3/O6 sources n=1..3 in order; O3 n=1 `sample-local-pdf.pdf#page1` `page:1`. |
| 5. O4 classified per attempt | **VERIFIED** | 3/3 "exact refusal" (verbatim text recorded). Classification checked by reading the text, not only the driver heuristic. |
| 6. No key in repo/evidence; only docs changes | **VERIFIED** | Key-prefix grep over the repo (excl. node_modules/venv/.git) and the scratchpad: no key found (the only textual match is this file's own description of the grep pattern). `git diff --stat` for `backend frontend railway.toml render.yaml vercel.json .github docker-compose.yml`: empty. `git status` outside `docs/`, `.claude/`, `CLAUDE.md`: empty. |
| 7. Throwaway session deleted | **VERIFIED** | Driver printed `session exists after delete: False` in every run (1–4). |
| 8. Status changes match evidence, others stay UNVERIFIED | **VERIFIED** (re-verified 2026-09-30 after the reconciliation below; originally downgraded by the audit) | F12/F16/REQ-U09/D-U09/V-F16/G05 row and the G03/G04 Unknowns updated only "for Gemini"; Mistral/OpenAI/Anthropic explicitly left unverified. The G05 backlog *entry body* still said "UNVERIFIED/Blocked"; corrected during validation. F13 left UNKNOWN. |
| 9. Defects/surprises logged, not fixed | **VERIFIED** (after this session's fix) | Initially only in the observations file; **validation found the gap** and added backlog entries G29 (provider 429/503 → generic 500, no retry) and G30 (uncited chunks listed as sources). No code changed. |

## Findings (deviations, for the reviewer)
1. **Cap wording (AC2):** the spec text says 20 calls total; the recorded owner decision says 20 per provider. Both runs stayed ≤ 20 per provider. Recommend the owner confirm per-provider is what was meant (I treated the decision as authoritative).
2. **R2 retries:** the spec allows at most one retry per question. Because runs 2 and 3 (503) were followed by run 4, O1 "Who created Python?" was asked three times on Gemini. Each re-run was explicitly requested by the owner ("retry"), and 503 is not an auth/model error, but it exceeds "one retry per question" literally.
3. **R2 stop rule:** the driver used in runs 1–2 did not stop at the first 429/503 (7 extra rejected Mistral calls; 6 Gemini 503s). Fixed for runs 3–4.
4. **R3 key handling:** the plan asked the owner to export the key with `!` in the shell; instead both keys were pasted into chat. They were only passed as process env vars and appear in no file, but they are in the conversation transcript — **rotate both**.
5. **Mistral was never observed** (429 from the first call); F13 remains UNKNOWN.
6. Small sample: every conclusion is N=1 per question on one model.

## Regression / other checks
- CI command `cd backend && venv/bin/pytest tests/test_embedder.py tests/test_web_loader.py -q`: **32 passed** (using a scratch `CHROMA_PERSIST_DIR`).
- `test_pipeline.py` was not run (per CLAUDE.md; the live run used a driver instead).
- Lint/build: NOT_APPLICABLE (no source changed).

## Definition of Done — G05

- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G05.md` Status APPROVED (owner, 2026-09-29)
- [x] Implementation plan created — APPLICABLE+VERIFIED — `G05-plan.md`, owner-approved
- [x] Code implemented — NOT_APPLICABLE — evidence run, no code by spec
- [x] Unit tests pass — NOT_APPLICABLE — no code/tests added
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — CI command 32 passed
- [x] Integration tests pass — NOT_APPLICABLE — live driver observations replace them; `test_pipeline.py` deliberately not run
- [x] Original bug reproduced before fix — NOT_APPLICABLE — UNKNOWN-type item, not a bug
- [x] Original bug verified fixed — NOT_APPLICABLE — same
- [x] Acceptance criteria verified — APPLICABLE+VERIFIED — table above (AC2 with the flagged wording issue)
- [x] Regression check performed — APPLICABLE+VERIFIED — no source diff + CI command
- [x] Diff reviewed — APPLICABLE+VERIFIED — docs-only; key grep clean
- [x] No unrelated changes — APPLICABLE+VERIFIED — `git diff --stat` on code/config/deploy empty (tracked workflow-doc modifications for G01–G27 pre-existed this session)
- [x] Documentation updated — APPLICABLE+VERIFIED — observations, backlog (incl. G29/G30), F12/F16, REQ-U09, G03/G04 Unknowns
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — nothing committed; owner has not asked
- [ ] Branch pushed — NOT_APPLICABLE until a commit is requested (docs-only; owner's call)
- [ ] PR created — NOT_APPLICABLE until a commit/push is requested
- [ ] CI passed — NOT_APPLICABLE (CI triggers on `backend/**`; no such change)
- [ ] Review completed — APPLICABLE+NOT_YET_VERIFIED — next session
- [ ] Merge completed — NOT_APPLICABLE / pending human
- [ ] Post-merge verification completed — NOT_YET_VERIFIED — after merge, if any
- [ ] Branch cleanup completed — NOT_YET_VERIFIED — after merge, if any

## Outcome
Validation **passes** with the findings above. No spec error found. Next: review (`/review G05`).

## Audit addendum (2026-09-29, owner asked to re-check implementation and validation)
- AC8 downgraded: stale statements remain in `PROJECT_BACKLOG.md` (V-F16 body, Coverage rows F12/F16), `04-feature-inventory.md` (F12/F16 detail sections), `05-requirements.md` (REQ-E02–E04 "unobserved" cells), `06-gap-analysis.md` (G05 entry). Not yet reconciled.
- R1 (owner re-confirms provider, key **and cap** in-session) was only partly met: provider and key were given; the cap was carried over from the spec decision, not re-confirmed.
- Raw evidence for attempts 1–3 exists only in the session transcript and the summaries in `G05-observations.md`; the scratchpad JSON survives for attempt 4 only (it was cleared once and overwritten per run).

## Reconciliation (2026-09-30, implementation of the audit findings)
- Annotated (originals kept, dated UPDATE note added): `04-feature-inventory.md` F12, F13, F16 (summary rows and detail headers), `05-requirements.md` REQ-E02/E03/E13, `06-gap-analysis.md` G05 (index row and entry), `PROJECT_BACKLOG.md` V-F16 body and Coverage rows F12/F13/F16. Each states "Gemini only; other providers unobserved".
- Not changed on purpose: `07-completion-plan.md` (historical plan), G05 spec (contract), any code (G29/G30 need their own specs/decisions).
- Open from the audit and NOT fixable after the fact: R1 cap re-confirmation, and lost raw output for attempts 1–3. Both are recorded, not repaired.

---
# Re-validation — VALID-G05-2026-10-01 (fresh run of every check)

Context: after attempt 5 (Groq via the OpenAI-compatible path + live G29 check) and the G29 remaining-work notes. Checkout during this session: `fix/G29-provider-429-503-status` (G05's own branch `docs/G05-answer-path-observations` has **0 commits**; all G05 files are untracked docs).

## Acceptance Criteria (re-checked)

| AC | Result | Evidence (this session) |
|---|---|---|
| 1. O1–O7 entries | **VERIFIED** | `G05-observations.md` sections: precheck; Mistral attempt; Gemini attempts 2–4; Groq attempt 5. O1–O7 all covered for Gemini (attempt 4) and Groq (attempt 5). |
| 2. Provider/model + call counts, ≤ 20 | **VERIFIED per provider** | Gemini 17, Mistral 8, Groq/openai-path 17 — each ≤ 20. Groq count re-checked against `groq_records.json` (17 records, `total`=17). The spec's "≤ 20 total" wording vs. the owner's "per provider" decision is still unresolved (total across providers = 42). |
| 3. O5 gate-only, 0 calls | **VERIFIED** | Groq records: O5 `calls`=0, exact refusal; same in Gemini run 4 and run 2. |
| 4. Numbered sources, `page` for PDF | **VERIFIED** | Groq records: sources n=1..3, PDF entry `page:1`; Gemini run 4 as documented. |
| 5. O4 classified | **VERIFIED** | Groq records: 3/3 `grounded:false`, `exact_refusal:true`; Gemini 3/3 earlier. |
| 6. No key; docs-only | **VERIFIED** | Grep for the three providers' key patterns (by prefix and distinctive leading characters; the patterns are deliberately not written out here) over repo + scratchpad: 0 files. Working tree has no changes under `backend/ frontend/ railway.toml render.yaml vercel.json .github docker-compose.yml Dockerfile`. `git diff main docs/G05-answer-path-observations`: empty. |
| 7. Throwaway sessions deleted | **VERIFIED** | Every run printed `session exists after delete: False` (runs 1–5; attempt 5 re-seen this session). |
| 8. Status changes match evidence | **VERIFIED** | Spot-checked REQ-E02/E03/E13, F12/F13/F16, V-F16, G05 row/entry, G03/G04 Unknowns: all say "observed on Gemini (and Groq-compat path), others unobserved". Remaining "unobserved" hits in the backlog are the original G05 title and the unrelated G20. |
| 9. Defects logged | **VERIFIED** | G29 (now implemented separately, see its validation) and G30 entries exist. New finding from attempt 5 (full-width `【1】` marker) is recorded in the observations file; **not yet** a backlog entry — see Findings 4. |

## Regression
- CI command: **32 passed** (on the G29 branch; G05 changed no code).
- Full key-free suite (`pytest tests --ignore=tests/test_pipeline.py`): **148 passed**.
- `test_pipeline.py` not run (paid key; the live drivers replaced it).
- Lint/build: NOT_APPLICABLE (no source changed by G05).

## Findings (new or still open)
1. **Raw-evidence loss, again:** the scratchpad was cleared between sessions — the Gemini run-4 JSON that existed on 2026-10-01 is gone; only `groq_records.json` survives. For Mistral and Gemini the evidence is the transcript plus the summaries in the observations file (verbatim answers are included there). Recommendation for any re-run: write records under `docs/implementation/evidence/` (redacted) instead of the scratchpad.
2. **Scope growth, owner-driven:** the spec said "one provider first"; three were tried (Mistral, Gemini, Groq). Each used owner-supplied keys and stayed ≤ 20 calls, but R1's in-session cap re-confirmation was not asked again for Groq.
3. **Groq ≠ a supported provider.** It exercised the OpenAI SDK code path only; F13/OpenAI proper stays UNKNOWN. Stated in the docs.
4. **Open item:** the `【1】` marker variation (1 of 8 Groq repeats) should become a backlog note (affects any future parsing of `[n]`, e.g. G30). Logged now as part of this session: see G30 entry update.
5. **Branch hygiene:** two tracked G29 docs are modified and uncommitted on the G29 branch (remaining-work notes); G05 files are all untracked. Neither is committed; keep G29 and G05 commits separate when the owner decides.
6. Still open from before: cap-wording decision, key rotation (now **four** keys in the transcript: Mistral, Gemini, Groq — rotate all), commit/PR decision.

## Definition of Done — G05 (re-run)

- [x] Specification approved — APPLICABLE+VERIFIED — Status APPROVED
- [x] Implementation plan created — APPLICABLE+VERIFIED — `G05-plan.md`
- [x] Code implemented — NOT_APPLICABLE — evidence run by spec
- [x] Unit tests pass — NOT_APPLICABLE — none added
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — 32 (CI) and 148 (full key-free)
- [x] Integration tests pass — NOT_APPLICABLE — live drivers instead; `test_pipeline.py` not run
- [x] Original bug reproduced before fix — NOT_APPLICABLE — not a bug
- [x] Original bug verified fixed — NOT_APPLICABLE
- [x] Acceptance criteria verified — APPLICABLE+VERIFIED — table above
- [x] Regression check performed — APPLICABLE+VERIFIED
- [x] Diff reviewed — APPLICABLE+VERIFIED — G05 branch == main; no code/config/deploy changes in the working tree
- [x] No unrelated changes — APPLICABLE+VERIFIED — see Finding 5 for the separate G29 doc edits
- [x] Documentation updated — APPLICABLE+VERIFIED — observations, backlog, inventory, requirements, gap analysis, G03/G04 Unknowns, G29 remaining work
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — nothing committed (owner's go pending)
- [ ] Branch pushed — NOT_YET_VERIFIED / NOT_APPLICABLE until a commit
- [ ] PR created — NOT_YET_VERIFIED / NOT_APPLICABLE until a commit
- [ ] CI passed — NOT_APPLICABLE (no `backend/**` change in G05)
- [ ] Review completed — APPLICABLE+NOT_YET_VERIFIED
- [ ] Merge completed — pending human
- [ ] Post-merge verification completed — NOT_YET_VERIFIED
- [ ] Branch cleanup completed — NOT_YET_VERIFIED

## Outcome
Validation **passes** with the findings above; no spec error found. Next: review (`/review G05`) when the owner gives the go.
