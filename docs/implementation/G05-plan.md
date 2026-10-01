# G05 — Implementation Plan

Spec: `docs/specs/G05.md` (APPROVED). Base: `main` @ `09432cb` (== `origin/main`; `backend/` and `frontend/` trees clean; the working tree's untracked/modified files are workflow docs only).
Branch: `docs/G05-answer-path-observations` — **already created** from `main` @ `09432cb`.
Plan persisted at `docs/implementation/G05-plan.md`; handoff to write: `docs/handoffs/PLAN-G05-2026-09-29-plan.md`.

## Status update (this revision)
- DONE: branch, persisted plan, free `precheck` (0 calls; all candidate questions gate as intended; corpus = 3 chunks; results in `docs/implementation/G05-observations.md`).
- REMAINING: write `PLAN-G05` handoff; then, only after the owner confirms provider + key (via `!` shell env) + ≤ 20 calls, the `live` phase and evidence-driven doc updates (R8). Live driver to be written from the precheck script (`<scratchpad>/g05_precheck.py`), adding the call counter.
- Refinement from precheck: O5 is a free control; O6's follow-up passes the gate unrewritten (1.93), so O6 is judged by the logged rewritten query only. Live call budget ≈ 8 (O1×2, O3×1, O4×3, O6×2).

## Context
No LLM answer has ever been observed. G05 is an evidence run, not a code change: no product, config, test, CI or deploy file changes. Output: `docs/implementation/G05-observations.md` plus status updates that follow from it. Spend needs the owner's run-time confirmation (R1).

## Repo facts checked (read-only)
- `backend/venv` (py3.14.7) has chromadb, sentence-transformers, fitz, langchain-text-splitters, google-genai, mistralai, openai, anthropic, dotenv, pytest. (The root `venv/` has none of these; use `backend/venv`.)
- Embedder/reranker models are in the HF cache, so no download is expected.
- No `backend/.env` and no `.env` in the repo root or its parent; no `*_API_KEY`/`LLM_PROVIDER` in the shell environment. The `override=True` risk (R3) is therefore absent, but the driver still prints the resolved `settings.llm_provider`/model at start as a guard.
- Corpus `backend/docs/`: `python.txt` (created by Guido van Rossum, 1991, dynamically typed…), `fastapi.txt` (created by Sebastian Ramirez, Starlette/Pydantic, Swagger UI/ReDoc), `sample-local-pdf.pdf` (ChromaDB persists embeddings across restarts; "sample PDF used for testing the ingestion pipeline"). Sources on the PDF will be `sample-local-pdf.pdf#page1`.
- `pipeline.ask(question, session_id, history)` does exactly 1 answer call (+1 rewrite when `ENABLE_QUERY_REWRITING` is set and `history` non-empty); gate rejection makes 0 calls. `settings` reads env at import, so `ENABLE_QUERY_REWRITING` must be in the env before the driver imports `config`.
- Logging is never configured in `api/`/`src/`, so the driver calls `logging.basicConfig(level=INFO)` to see `Query rewritten`.

## Design: throwaway driver (not committed)
`<scratchpad>/g05_run.py`, run as `cd backend && venv/bin/python <scratchpad>/g05_run.py --phase {precheck|live}`. Lives in the scratchpad, never in the repo.

1. **Call counter** — wrap `answer_chain._call_llm_plain` and the four `_answer_*` functions (monkeypatch on the module, dispatch table is built inside `answer()` from module globals, so patching the module attributes works) to increment a counter and hard-abort at 20 (R2). No retries on auth/404; the single retry (model override) requires an explicit `--retry-with-model` flag set by the owner.
2. **Phase `precheck` (free, no LLM, no key)** — build `AskMyDocsPipeline()`, ingest `backend/docs/` into `g05-verify-<timestamp>`, call `retrieve_and_rerank` for candidate questions and print top score vs. `settings.relevance_threshold` and the top chunk's source. Candidates:
   - O1: "Who created Python?"; "What is FastAPI built on?"
   - O3: "What vector database does this project use?" (PDF-only)
   - O4 (related but unanswered; must pass the gate): "When was FastAPI first released?", "Who maintains Python today?", "What is the license of ChromaDB?"
   - O5: "What is the boiling point of mercury in Kelvin?" (expect gate reject)
   - O6: history `["Who created Python?"]`, follow-up "When was it first released?"
   Any candidate that unexpectedly fails the gate is swapped for a more specific one before going live (no cost).
3. **Phase `live`** (only after R1 confirmation): same ingest, then run O1, O3, O4×≤3, O5, and O6 (with `ENABLE_QUERY_REWRITING=true` in the env for this process). Budget: O1×2 + O3×1 + O4×3 + O5×0 + O6×2 (rewrite + answer) = 8 calls, leaving headroom for one retry each on transient errors. O7 is read off the first call's outcome (model ID resolved, or error class/status only).
4. For each observation the driver writes a JSON record (question, provider, model, verbatim answer, `grounded`, `sources`, extracted `[n]` markers with an in-range check, call count) to the scratchpad; errors are sanitized to class + status. The driver classifies O4 replies as exact refusal / refusal with extra text / outside-knowledge answer / other, using an exact compare with `NOT_FOUND_MESSAGE`, and marks the classification as a heuristic for me to confirm by reading the text.
5. The session is deleted in a `finally` (`chroma_store.delete_session`), then `session_exists` is asserted false (AC7).

## Plan rows

| Spec item | Step | Verification |
|---|---|---|
| R1, Constraint (approval) | Before `live`: ask the owner (AskUserQuestion) to confirm provider, key supplied via process env, cap 20. Key is supplied by the owner with `!` in the session shell (`export <PROVIDER>_API_KEY=… LLM_PROVIDER=…`), never typed into chat or a file. | Confirmation recorded in the observations file header |
| R2 / AC2 | Counter + hard abort in the driver | Final count in the record ≤ 20; owner may cross-check the provider dashboard |
| R3 | Start-of-run print of resolved provider/model; `.env` absent (checked) | Header of observations file |
| R4 / AC7 | Throwaway session id, deleted in `finally` | `session_exists` false printed |
| O1, O3 / AC1, AC4 | Live questions above; record `grounded`, `sources` (`n`, `page`) | Sources match chunk numbering (n=1..len; `page` present for the PDF) |
| O2 | Regex `\[(\d+)\]` over each grounded answer, check `1 ≤ n ≤ len(sources)`; note unmarked claims by reading | Table in the observations file |
| O4 / AC5 | Up to 3 related-but-unanswered questions | Per-attempt classification reviewed by reading the text |
| O5 / AC3 | Gate-only unrelated question | `grounded:false`, exact `NOT_FOUND_MESSAGE`, counter unchanged across the call |
| O6 | `ENABLE_QUERY_REWRITING=true`, INFO logging on; capture the `Query rewritten` line | Rewritten query shown; confirms a rewrite call occurred |
| O7 | Outcome of the first call | Model ID recorded; on failure, error class/status only |
| R6/R7 | Failures recorded as observations; OBSERVED vs. UNVERIFIED listed (other 3 providers, other models, streaming, load) | Observations file sections |
| R8 / AC8, AC9 | After the run, update only what the evidence supports: G05 row/entry, F12, F16, REQ-U09/D-U09, G03/G04 Unknowns (cite observation IDs). If O4 shows trailing text, add a follow-up backlog entry for G03's exact-match limit (no fix). Defects → new backlog entry / found-out-of-scope note. | Diff of docs only, each change cites an O-id |
| AC6 | `grep -rn` for the key value/prefix over `docs/` and the repo (owner supplies the prefix via a shell variable so it is never printed); `git status` shows docs-only changes | Empty grep; `git diff --stat` has only `docs/` paths |
| Regression | No edits to `backend/`, `frontend/`, config/deploy; `git diff --stat -- backend frontend` empty; CI command `cd backend && venv/bin/pytest tests/test_embedder.py tests/test_web_loader.py -v` still exits 0 | Command output |

## Files
- Create: `docs/implementation/G05-plan.md`, `docs/implementation/G05-observations.md`, `docs/handoffs/PLAN-G05-2026-09-29-plan.md`.
- Modify (after run, evidence-driven): `docs/PROJECT_BACKLOG.md`, `docs/project-assessment/04-feature-inventory.md` (F12/F16), `05-requirements.md` (REQ-U09), `docs/specs/G03.md` / `G04.md` (Unknowns only).
- Not touched: everything under `backend/`, `frontend/`, `railway.toml`, `render.yaml`, `vercel.json`, CI, real env files, `test_pipeline.py` (not run).

## Risks
- Default model ID invalid at the provider (e.g. `gemini-3.6-flash`, `claude-sonnet-5`): recorded as O7; at most one retry with an owner-supplied `*_MODEL` override, counted.
- Tiny corpus: gate may reject an intended O1/O3 — caught free in `precheck`.
- LLM variance: conclusions worded "observed in N samples".
- Quota/429: stop, record, no loop.
- Answers are verbatim provider output on the repo's own sample docs; no personal data, so they are safe to commit. Not committing anything unless the owner asks.

## Migration notes
None (no schema/config/data change).

## Verification
Run `precheck`, then (after confirmation) `live`; check each AC from the table; run the CI command and the two greps; confirm `git diff --stat` is docs-only.
