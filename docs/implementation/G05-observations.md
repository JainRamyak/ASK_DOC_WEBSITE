# G05 — Observations

Status: **LIVE RUN COMPLETE for Gemini 2026-09-29 (attempt 4 succeeded after Mistral 429s and Gemini 503/429s in attempts 1–3); other providers not observed.** Attempts 1–3 are kept below as they happened. Owner confirmed provider = Mistral and supplied the key; the ≤ 20-call cap stood. The key was passed only as a process environment variable for the run (the owner pasted it in chat rather than exporting it themselves; it is not written to any file here).

## Free precheck (2026-09-29, OBSERVED, 0 provider calls)
Environment: `backend/venv` (py3.14.7), local embedder + reranker from the HF cache, throwaway Chroma dir in the scratchpad (not `outputs/chroma`), corpus `backend/docs/` → **3 chunks** (one per file; so a grounded answer has at most 3 sources). Resolved `llm_provider` = gemini (default; no env, no `.env`), threshold −3.0. Session deleted afterward (`session_exists` = False).

| Obs | Question | Gate | Top score | Top source |
|---|---|---|---|---|
| O1 | Who created Python? | PASS | 9.59 | python.txt |
| O1 | What is FastAPI built on? | PASS | 9.29 | fastapi.txt |
| O3 | What vector database does this project use? | PASS | 6.51 | sample-local-pdf.pdf#page1 |
| O4 | When was FastAPI first released? | PASS | 1.02 | fastapi.txt |
| O4 | Who maintains Python today? | PASS | −0.03 | python.txt |
| O4 | What is the license of ChromaDB? | PASS | 0.34 | sample-local-pdf.pdf#page1 |
| O5 | What is the boiling point of mercury in Kelvin? | REJECT | −11.17 | python.txt |
| O6 | When was it first released? (history: "Who created Python?") | PASS | 1.93 | python.txt |

All candidate questions behave as intended, so no swaps are needed. Side observation: the O6 follow-up passes the gate even without rewriting (1.93), so the rewrite's effect must be judged from the logged rewritten query, not from gate pass/fail.

## Live observations O1–O7 (provider: mistral, model `mistral-small-latest` — the default, `MISTRAL_MAX_TOKENS`=2048)
Driver: scratchpad only, not committed. Corpus ingested into a throwaway session (3 chunks), deleted afterward (`session_exists` = False). **Total provider calls: 8** (all rejected with 429; the cap of 20 was not approached).

Every attempted call failed immediately (0.5–0.7 s) with `SDKError`, status **429**, body `{"type":"rate_limited","message":"Rate limit exceeded","code":"1300"}`, starting with the very first call.

| Obs | Result | Status |
|---|---|---|
| O1 (×2) | 429 on both attempts | NOT OBSERVED |
| O2 | no grounded answer, so no markers to check | NOT OBSERVED |
| O3 | 429 (gate PASSED, top 6.51, `sample-local-pdf.pdf#page1`, before the call) | NOT OBSERVED |
| O4 (×3) | 429 on all three (gates passed: 1.02, −0.03, 0.34) | NOT OBSERVED |
| O5 | Gate reject at −11.17; answer == `NOT_FOUND_MESSAGE`, `grounded:false`, `sources:[]`, **0 provider calls** (counter unchanged) | OBSERVED (AC3 met) |
| O6 | The rewrite call got 429; `rewrite_query` swallowed it and logged `Query rewrite failed, using original question: API error occurred: Status 429 …` (2 calls incl. the answer call, which also got 429) | PARTLY: observed the designed failure fallback only; no rewritten query seen |
| O7 | The default model ID was never evaluated — a 429 is not a model-not-found and says nothing about whether `mistral-small-latest` resolves | INCONCLUSIVE |

### What this does and does not show
- OBSERVED: the Mistral SDK import/construct/call path reaches Mistral's API from this code (consistent with the archive's historical claim) and the key/account was rate-limited at the time of the run. The rewrite failure fallback works as designed.
- NOT shown: whether the 429 is a per-key/free-tier quota, a temporary burst limit, or an account issue — only the owner can tell from the Mistral console. The 429 from the very first call suggests a quota/limit condition on the key rather than burst traffic from this run (INFERRED, not verified).
- Deviation from the spec (R2/Edge Cases: "429 mid-run: stop, do not loop"): the driver aborted only on 401/403/404, so it went through all 8 planned calls instead of stopping after the first 429. Effect: 7 extra rejected calls, no retries, well under the cap. Any future driver must abort on the first 429.
- Side observation (out of scope, for the backlog, not fixed): a provider 429 propagates from `_answer_mistral` as a raw `SDKError` (not `LLMConfigError`); how `/query` maps it is a G13-area question — worth checking separately.

## Live attempt 2 — Gemini (2026-09-29, owner switched provider after the Mistral 429s)
Model `gemini-3.6-flash` (the default; `GEMINI_MAX_OUTPUT_TOKENS`=2048), key via process env only, fresh throwaway session (deleted; `session_exists` = False). **8 provider calls** (Gemini's own cap of 20 per provider was not approached; Mistral's 8 are separate). No answer obtained.

| Obs | Result | Status |
|---|---|---|
| O1 (×2), O3, O4 (×3) | 6 consecutive calls: `ServerError` **503 UNAVAILABLE** "This model is currently experiencing high demand… try again later" (calls took 2–12 s) | NOT OBSERVED |
| O5 | Gate reject −11.17, exact `NOT_FOUND_MESSAGE`, `grounded:false`, 0 provider calls | OBSERVED (AC3 met again) |
| O6 | Rewrite call: `ClientError` **429 RESOURCE_EXHAUSTED**, quota metric `generate_content_free_tier_requests`, **limit 5 (per minute, per project, per model, free tier)**, retry in ~42 s; rewrite fell back to the original question as designed; the answer call then also got 429 | PARTLY (fallback only) |
| O2, O7 | No grounded answer; model-ID validity not established (503/429 are not model-not-found, though the call did reach `gemini-3.6-flash` and it was not rejected as unknown) | INCONCLUSIVE |

### Findings
- OBSERVED: the Gemini path reaches the API with this key and the default model ID is not rejected as not-found in this run (weak evidence for REQ-U09/D-U09, not proof — no successful generation).
- OBSERVED: the free tier allows **5 requests/minute/model**; a burst of 8 calls exceeds it. The 503s (transient overload of `gemini-3.6-flash`) also appear to have counted toward the limit (INFERRED from the 429 arriving after 6 requests, 5 being the limit).
- Plan correction for any further run: pace calls (≥ 13 s apart, ideally ~15 s), abort on the first 429 (the driver now does; it did not abort on 503, which let 6 calls through — a 503 should also stop the run or allow at most one paced retry).
- Same side note as Mistral: provider 503/429 escape `_answer_gemini` as raw SDK errors; how `/query` reports them is a separate (G13-area) question, not fixed here.

## Live attempt 3 — Gemini, paced, stop-on-error (2026-09-29, owner: "retry")
Same default model `gemini-3.6-flash`; the driver was rebuilt (the scratchpad had been cleared) with a 15 s pause between questions and an abort on the first 429/5xx. **1 provider call**: O1 "Who created Python?" → `ServerError` **503 UNAVAILABLE** ("high demand", 3.4 s). Run stopped by design; session deleted. Running total for Gemini: 9 calls (cap 20); Mistral: 8.
OBSERVED: the 503 on `gemini-3.6-flash` is persistent across three runs spanning the session, so it is not a per-minute quota effect (a fresh minute, first call). This is a provider-side capacity problem with that model at this time (INFERRED cause: overload of that specific model; not tested on others). No answer observed; O1–O4, O6 still NOT OBSERVED.

## Live attempt 4 — Gemini, paced, default model (2026-09-29, owner: "retry") — SUCCESS
`gemini-3.6-flash` (default, no override), `ENABLE_QUERY_REWRITING=true`, 15 s pacing, stop-on-error. 3 chunks (one per file). **8 provider calls** this run; Gemini total 17 of 20 (Mistral separately 8). Session deleted (`session_exists` = False). Key via process env only. All results below are verbatim, single samples (N=1 per question, except O4 N=3 different questions).

| Obs | Question | Answer (verbatim) | grounded | Markers | Sources |
|---|---|---|---|---|---|
| O1 | Who created Python? | "Python was created by Guido van Rossum [1]." | true | [1] ✓ in range | n=1 python.txt (9.59), n=2 fastapi.txt (2.96), n=3 sample-local-pdf.pdf#page1 p1 (−11.34) |
| O1 | What is FastAPI built on? | "FastAPI is built on top of Starlette for the web parts and Pydantic for the data validation parts [1]." | true | [1] ✓ | n=1 fastapi.txt (9.29), n=2 python.txt, n=3 PDF p1 |
| O3 | What vector database does this project use? | "This project uses ChromaDB as its vector database [1]." | true | [1] ✓ | n=1 `sample-local-pdf.pdf#page1` with `page: 1`, n=2 fastapi.txt, n=3 python.txt |
| O4 | When was FastAPI first released? (gate top 1.02) | "I could not find this in the provided documents." | false | – | `[]` |
| O4 | Who maintains Python today? (gate top −0.03) | same exact sentence | false | – | `[]` |
| O4 | What is the license of ChromaDB? (gate top 0.34) | same exact sentence | false | – | `[]` |
| O5 | boiling point of mercury in Kelvin? | exact `NOT_FOUND_MESSAGE`, gate reject −11.17, **0 calls** | false | – | `[]` |
| O6 | "When was it first released?" + history ["Who created Python?"] | log: `Query rewritten: 'When was it first released?' -> 'When was Python first released?'`; answer "Python was first released in 1991 [1]." | true | [1] ✓ | n=1 python.txt (8.45), n=2 fastapi.txt, n=3 PDF p1 |
| O7 | default model ID | `gemini-3.6-flash` resolved and generated text (also in runs 2–3 it was reached and not rejected as unknown) | – | – | – |

### Findings (OBSERVED for Gemini / `gemini-3.6-flash`, N=1 each unless stated)
- **F12 (cited answer generation):** works end-to-end: grounded, concise answers, correct on all three factual questions, each with a `[1]` marker, sources numbered with the prompt labels (`n`), and the PDF entry carries `page`. O2: all 4 grounded answers used only `[1]`, always within `1..len(sources)`; no out-of-range or omitted markers, no unmarked claim (each answer is one sentence).
- **G03/G04 relevance:** in 3 of 3 related-but-unanswered samples (O4) the model returned the refusal sentence **exactly**, so the exact-match rule produced `grounded:false`, `sources:[]` as intended; no trailing text or `[n]` on the refusal, and no outside-knowledge answer. This does NOT establish it never happens (N=3, one model).
- **Observation for G04's accepted design:** every grounded answer lists all 3 retrieved chunks as sources though the answer cites only `[1]`; the other chips are low-scoring (−8 to −11.4) chunks that were not used. This is the behavior D-C05 chose ("one entry per context chunk"); flagged as a UX consideration only, no defect claimed.
- **F16 (rewriting):** observed once: the pronoun follow-up was rewritten to a standalone question, retrieval scored 8.45 (vs. 1.93 unrewritten), and the answer was correct. Rewrite call + answer call = 2 provider calls, as designed. The failure fallback was also observed earlier (runs 1–2).
- **REQ-U09/D-U09 for Gemini:** default `gemini-3.6-flash` is valid at the provider today and worked with thinking disabled and `max_output_tokens=2048`.
- **Availability caveat:** in earlier attempts the same model returned 503 "high demand" (runs 2–3), and the free tier is limited to 5 requests/min/model (run 2). 503s were transient (run 4 succeeded some time later). The 429/503 from providers reach the code as raw SDK errors (see side note), so a user would see whatever `/query` maps them to — not examined here.

## Attempt 5 — Groq via the OpenAI-compatible path, plus a live G29 check (2026-10-01, owner-supplied Groq key)
Groq is NOT one of the four supported providers. The run used `LLM_PROVIDER=openai` with `OPENAI_BASE_URL=https://api.groq.com/openai/v1`, `OPENAI_MODEL=openai/gpt-oss-20b` (picked from Groq's model list; a free `/models` call), key via process env only. So this exercises the **OpenAI SDK code path** (`_answer_openai`, `_call_llm_plain`) against Groq, **not OpenAI itself** — F13's OpenAI status stays UNKNOWN for OpenAI proper. Branch checked out: `fix/G29-provider-429-503-status` (so G29 code was live). Calls went through the real `query_document` handler. **17 provider calls** (cap 20 for this provider); session deleted.

### Phase A — G05 observations (all HTTP 200)
- O1 ×2, O3: grounded, correct, markers `[1]`, sources numbered, PDF entry `page:1` (same shape as Gemini).
- O4 ×3: exact refusal sentence, `grounded:false`, `sources:[]` (3/3, same as Gemini).
- O5: gate reject, 0 calls. O6: `Query rewritten: 'When was it first released?' -> 'When was Python first released?'`, answer "Python was first released in 1991. [1]" (2 calls).
- **New observation:** in the burst below, 1 of 8 repeats of "Who created Python?" came back as "Python was created by Guido van Rossum【1】" — a **full-width bracket marker (U+3010/3011), not `[1]`**. The answer was still `grounded:true`. Marker spacing also varied ("rossum. [1]" vs "rossum.[1]"). On Gemini the markers were always `[1]` (N=4). So `[n]` is not guaranteed across models. Whether the frontend/chips care: the chips are driven by `sources`, not by parsing the answer, so no break is implied, but any future feature that parses `[n]` (e.g. G30 option) must tolerate this (INFERRED from design; UI not viewed).

### Phase B — G29, real calls through `/query`
- B2 (real provider error): model set to a non-existent ID → Groq returned 404 `model_not_found` → `/query` returned **HTTP 500 with the fixed `GENERIC_ERROR_MESSAGE`**, and the raw error text appeared only in the server log. This matches G29's rule that unclassified statuses stay a generic 500 and raw text never reaches the client. OBSERVED live.
- B3 (burst): 8 rapid back-to-back calls → all 200 (0.3–0.7 s each); **no 429 or 503 occurred**. So the 429/503 → distinct-status path was **NOT exercised against a real provider**; it remains verified only with real SDK exception classes built offline (34 passing tests + attribute check).
- Happy path through the G29 code: 200 on every normal call, no regression seen.

### Updated "still UNVERIFIED"
G29's 429/503 mapping against a live provider; Mistral; OpenAI proper; Anthropic; the UI.

## Still UNVERIFIED
- Mistral (429 ×8, never got a response), OpenAI, Anthropic: no answer observed; F13 (provider switching) stays UNKNOWN except for Gemini. Their default model IDs are unchecked.
- Any Gemini behavior beyond N=1 per question: variance in marker use/refusal wording, multi-sentence answers, long contexts (corpus was 3 tiny chunks), PDF multi-page.
- How `/query` reports a provider 429/503 to the user (G13-area), and the UI rendering of chips (G04 AC7).
- Cost/latency: calls took ~2–5 s each.
