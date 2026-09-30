# Validation: G29 — provider 429/503 shown to users as a generic 500

Session: VALID-G29-2026-09-30 · Branch `fix/G29-provider-429-503-status` (base `main` @ `09432cb`, uncommitted) · Spec `docs/specs/G29.md` (APPROVED) · Plan `docs/implementation/G29-plan.md`
Environment: scratch venv in the session scratchpad (outside the repo), `pip install -r backend/requirements.txt` with CPU-only torch; pinned SDKs installed (google-genai 1.73.1, anthropic 0.94.1, openai 2.32.0, mistralai 2.9.4). No provider API call was made at any point.

## Bug reproduction chain (evidence)
Driver script (scratchpad-style, deleted after use, never committed) builds **real SDK exception objects offline** (`google.genai.errors.ServerError/ClientError`, `openai.RateLimitError`, `anthropic.APIStatusError`), makes the provider function raise them, and calls `api.query_document` with the real `answer()` dispatch.

1. **REPRODUCE ORIGINAL FAILURE** — fix stashed (`git stash push -- backend/api/main.py backend/src/generation/answer_chain.py`):
```
gemini 503: status=500 detail='Something went wrong while processing your request. Please try again.'
gemini 429: status=500 detail='Something went wrong while processing your request. Please try again.'
openai 429: status=500 detail='Something went wrong while processing your request. Please try again.'
anthropic 529: status=500 detail='Something went wrong while processing your request. Please try again.'
```
Confirms the spec's Current Behavior (previously code-read only; now OBSERVED through the endpoint function).
2. **APPLY FIX** — `git stash pop`; `git status --short backend` shows the two modified files plus the untracked new test file.
3. **REPRODUCE SAME SCENARIO**:
```
gemini 503: status=503 detail='The assistant is busy right now. Please try again in a moment.'
gemini 429: status=429 detail='The assistant is receiving too many requests right now. Please wait a moment and try again.'
openai 429: status=429 detail='The assistant is receiving too many requests right now. Please wait a moment and try again.'
anthropic 529: status=503 detail='The assistant is busy right now. Please try again in a moment.'
```
4. **VERIFY FAILURE IS GONE** — above, plus `tests/test_provider_throttling.py` → 34 passed (13 of the 25 original tests failed on the unchanged code in the red run; the other 12 pin unchanged behaviour).
5. **VERIFY NO REGRESSION** — CI command `pytest tests/test_embedder.py tests/test_web_loader.py -v` → 32 passed, exit 0. `tests/test_error_responses.py` (G13) → 10 passed. Full key-free suite (`pytest tests --ignore=tests/test_pipeline.py`) → 148 passed.

## Acceptance Criteria
| AC | Status | Evidence |
|---|---|---|
| AC1 (429 → HTTP 429, fixed message, no raw text) | **VERIFIED** | `test_429_maps_to_429` ×4 providers; chain step 3 with real `ClientError`/`RateLimitError`; `"SECRET"` not in `detail` |
| AC2 (503 and 529 → HTTP 503 busy message, ≠ config message; other/non-int status → generic 500) | **VERIFIED** | `test_503_and_529_map_to_503_busy` ×8; `test_unclassified_errors_stay_generic_500` ×7 (500, 401, 404, `"429"`, `True`, `code=None`, no attribute); real anthropic 529 in chain step 3 |
| AC3 (all four providers, shaped exceptions; real classes where importable) | **VERIFIED** | stand-in tests for gemini (`.code`), mistral/openai/anthropic (`.status_code`); `test_real_sdk_exceptions_are_classified` ×8 and `test_real_anthropic_529_is_classified` use real SDK classes for all four. Real mistralai **2.9.4** only (see Caveats) |
| AC4 (generic still 500; `LLMConfigError` still 503 config) | **VERIFIED** | `test_config_error_still_503_config_message`; existing G13 tests still pass |
| AC5 (raw exception still logged) | **VERIFIED** | `test_raw_error_still_logged` (429 and 503) asserts raw text in `caplog.text` |
| AC6 (success / `grounded:false` paths unchanged) | **VERIFIED** | `test_pipeline_grounding.py`, `test_citation_sources.py` pass unmodified in the 148; diff touches only the `answer()` dispatch `return` (wrapped) and `/query` except branches |
| AC7 (exactly one provider call, no retry) | **VERIFIED** | `test_provider_called_exactly_once` (429, 503) |
| AC8 (no change under `frontend/`, `config.py`, `.env.example`, deploy files) | **VERIFIED** | `git status --short backend frontend .github railway.toml render.yaml vercel.json docker-compose.yml Dockerfile` → only `backend/api/main.py`, `backend/src/generation/answer_chain.py` (M), `backend/tests/test_provider_throttling.py` (new); `git diff --stat -- backend`: 2 files, 55 insertions, 2 deletions |
| AC9 (CI command exits 0; new tests need no key) | **VERIFIED** | 32 passed, exit 0; new tests ran with no API key set |

## Caveats / not verified
- mistralai **2.4.2** (pinned in `requirements.prod.txt`, used by the Docker image) was not tested; only 2.9.4 from `requirements.txt`. **NOT_YET_VERIFIED** for the prod image. Worst case: a different attribute name degrades to today's generic 500.
- Behaviour against a live provider 429/503 through a running server: **NOT_YET_VERIFIED** (would spend quota; not run, per CLAUDE.md). Real-SDK exception objects built offline are the evidence.
- The frontend displaying the new messages: verified by code reading only (`parseErrorDetail` reads `detail` for any non-OK status; unchanged) — no frontend test suite or browser run.
- Lint: no backend lint command exists in the repo; `pyflakes` is not installed, so not run. Modules import and execute under the tests.
- Wording of the two messages is the owner-approved text from the spec.

## Definition of Done — G29
- [x] Specification approved — APPLICABLE+VERIFIED — `docs/specs/G29.md` Status APPROVED; decision in `docs/DECISIONS.md`
- [x] Implementation plan created — APPLICABLE+VERIFIED — `docs/implementation/G29-plan.md`, approved in Plan Mode
- [x] Code implemented — APPLICABLE+VERIFIED — diff above, all plan rows done
- [x] Unit tests pass — APPLICABLE+VERIFIED — 34 passed
- [x] Relevant existing tests pass — APPLICABLE+VERIFIED — CI 32, G13 10, full key-free 148
- [ ] Integration tests pass — NOT_APPLICABLE — none exist beyond the endpoint-level tests above; `test_pipeline.py` needs a paid key and was not run
- [x] Original bug reproduced before fix — APPLICABLE+VERIFIED — chain step 1
- [x] Original bug verified fixed — APPLICABLE+VERIFIED — chain steps 3–4
- [x] Acceptance criteria verified — APPLICABLE+VERIFIED — table above (AC3 partial on mistral prod pin, see Caveats)
- [x] Regression check performed — APPLICABLE+VERIFIED — chain step 5
- [x] Diff reviewed — APPLICABLE+VERIFIED — full `git diff -- backend` read this session; wrapper re-raises unchanged for unclassified errors and config errors
- [x] No unrelated changes — APPLICABLE+VERIFIED — AC8 evidence; pre-existing uncommitted docs from earlier sessions are not part of G29
- [x] Documentation updated — APPLICABLE+VERIFIED — spec, DECISIONS, backlog (G29 entries), plan outcome section
- [ ] Commit created — APPLICABLE+NOT_YET_VERIFIED — nothing committed; waits for owner instruction
- [ ] Branch pushed — APPLICABLE+NOT_YET_VERIFIED — not pushed
- [ ] PR created — APPLICABLE+NOT_YET_VERIFIED — not created (review step next)
- [ ] CI passed — APPLICABLE+NOT_YET_VERIFIED — runs only after a PR; same command passes locally
- [ ] Review completed — APPLICABLE+NOT_YET_VERIFIED — next session
- [ ] Merge completed — APPLICABLE+NOT_YET_VERIFIED — human merge only
- [ ] Post-merge verification completed — APPLICABLE+NOT_YET_VERIFIED — after merge
- [ ] Branch cleanup completed — APPLICABLE+NOT_YET_VERIFIED — after post-merge verification
