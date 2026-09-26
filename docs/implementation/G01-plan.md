# G01 — Implementation Plan (concurrent same-session uploads)

## Context
`/upload` stages every request into `/tmp/rag_sessions/<session_id>/`. `pipeline.ingest` ingests the whole directory, and each request `rmtree`s it. Overlapping same-session requests therefore ingest each other's files, misreport `chunks`, and can delete each other's staged files (observed: 15 chunks where 6 were expected). Spec: `docs/specs/G01.md` (R1–R8, AC1–AC8). The user approved the spec as written in this session: same-name uploads are distinct uploads (A2), and the CI file is NOT edited (U2).

Session bookkeeping done at the start of implementation (not possible in plan mode):
- Set `docs/specs/G01.md` Status to `APPROVED`.
- Copy this plan to `docs/implementation/G01-plan.md`.
- Write `docs/handoffs/PLAN-G01-2026-09-26-plan.md`.
- Create the branch from base.

## Base / branch (confirmed read-only)
- Current branch `main` @ `bd69010`, equal to `origin/main`; `git fetch --dry-run` shows nothing new.
- The tree has only untracked workflow files (`.claude/`, `CLAUDE.md`, `docs/`), and no tracked changes. These carry over harmlessly to the new branch.
- Create `fix/G01-concurrent-upload-staging` from `main`. Nothing is committed or pushed by this plan, and `main` is never pushed to.

## Chosen approach
**Per-request staging directory.** This is the direct fix for the stated root cause. A lock would still leave same-name overwrite (R5) and stale carry-over (R6) unaddressed.

Single change in `backend/api/main.py` `/upload` (line ~133):
```python
tmp_dir = f"/tmp/rag_sessions/{uuid.uuid4().hex}"   # keyed by request, not session
```
- Update the adjacent comment/docstring to say why it is request-keyed.
- `session_id` is still passed to `pipeline.ingest(tmp_dir, session_id=...)`, so the collection is unchanged.
- No other change:
  - the existing `rmtree` calls in the success, `HTTPException` and generic-exception paths now touch only this request's own dir (R4);
  - `disambiguate_filename` still handles same-name files within one batch;
  - `ChromaStore`, `pipeline` and `loader` are untouched, and `_add_lock` keeps id uniqueness.
- Nothing else in the repo uses `/tmp/rag_sessions/<session_id>`. Checked: `Dockerfile`s only `mkdir /tmp/rag_sessions`, and no deploy config change is needed.
- Not addressed: dirs orphaned by a hard kill mid-request. That is pre-existing, and R6 only requires that such dirs are never ingested by another request, which per-request keys guarantee. A startup sweep is out of scope and would go to the found-but-out-of-scope log.

Size: about 2 changed lines in `main.py`, plus one new test file.

## Requirement → change → test → verification

| Req / AC | Code change | Test (in `tests/test_upload_concurrency.py`) | Verification |
|---|---|---|---|
| R1, R2, R3 / AC1 | request-keyed `tmp_dir` | N=4 concurrent uploads, distinct 1-chunk files, one existing session: all 200, each `chunks==1`, total = pre + 4, each source once | fails on current `main`, passes after |
| R3 / AC2 | same | 3 concurrent uploads of files yielding 1/2/3 chunks. Expected counts are computed via `chunk_documents` on the same text (no hard-coded numbers). Each response equals its file's count; total is the sum | same |
| R4 / AC3 | same (own-dir cleanup) | 2 good uploads plus 1 upload of a `.exe` file, overlapping: the bad one returns 400, the good ones return 200 with correct counts and full indexing | same |
| R5 / AC4 | same | 2 overlapping uploads with the same filename but different content: both contents present in the collection (compare `collection.get()["documents"]`), each response counts only its own chunks | same |
| R6 / AC5 | same | before the request, write `stray.txt` into `/tmp/rag_sessions/<session_id>/` (test removes it in `finally`); after upload, no stray chunks and `chunks` = uploaded file only | same |
| R4 / AC7 | same | snapshot `os.listdir("/tmp/rag_sessions")` before and after all requests (success and failure); no new entries | regression guard |
| R7 / AC6 | none (behavior-preserving) | sequential new-session upload and append: response keys `session_id, filenames, chunks, status`, `status=="ready"`, `filenames` unchanged. Error paths: too many files, invalid session id, unsupported type, whitespace-only file → 400 "No readable text…" (no session created for a new session) | passes before and after |
| R8 | none | none. Note in the plan/handoff only (single process, REQ-B09) | n/a |
| AC8 | none | no CI edit. Run the CI command unchanged | exit 0 |

## Test design (`backend/tests/test_upload_concurrency.py`, new)
Key-free, no network, and no model loading.
- **No httpx / TestClient.** `httpx` is not in `requirements.txt`, so the test calls the async endpoint `api.main.upload_documents(files=[...], session_id=...)` directly. It builds `starlette.datastructures.UploadFile(file=BytesIO(...), filename=...)` objects and runs them with `asyncio.gather` (via `asyncio.run` inside plain sync tests, so no pytest-asyncio dependency). `HTTPException` is asserted for the 400 cases. This also bypasses the rate limiter (20 req/60s), which would otherwise interfere.
- **Import isolation.** `api.main` builds `AskMyDocsPipeline()` at import, which would load torch models. A module-scoped fixture patches `src.pipeline.get_embedder` (deterministic stub `BaseEmbedder`, small dimension, hash-based vectors) and `src.pipeline.Reranker` (dummy) and then imports `api.main`. A function-scoped fixture builds a fresh `AskMyDocsPipeline()` with `settings.chroma_persist_dir = tmp_path` and applies `monkeypatch.setattr(api_main, "pipeline", p)`. This gives isolation per test.
- **Deterministic overlap (mechanism-agnostic).** A wrapper around `src.pipeline.load_documents` waits on a `threading.Barrier(N, timeout≈2s)`, swallowing `BrokenBarrierError`. All N requests have then staged their files before any of them scans a directory. On buggy code every request sees all N files, which fails deterministically. Under per-request staging the barrier releases normally. A future lock-based fix would only see a timeout, not a deadlock, so the test stays mechanism-agnostic.
- **AC3 ordering.** The failing request waits (threading `Event`) until the good requests are staged, then fires its 400. The wrapper holds the good requests until the failing one has finished (bounded timeout). This makes the buggy shared-dir `rmtree` land mid-flight.
- Expected chunk counts come from `chunk_documents([...])` on the same text, not from constants. Files are made multi-chunk by exceeding `settings.chunk_size`.

## Files
- Modify: `backend/api/main.py` (≈2 lines and a comment)
- Create: `backend/tests/test_upload_concurrency.py`
- Create (bookkeeping, not app code): `docs/implementation/G01-plan.md`, `docs/handoffs/PLAN-G01-2026-09-26-plan.md`; edit spec Status
- NOT touched: `.github/workflows/`, deploy configs, `config.py`, `ChromaStore`, `pipeline.py`, `loader.py`, frontend

## Risks
- **Stub fidelity:** the stub embedder must satisfy `BaseEmbedder` (`embed_text`, `embed_batch`, `dimension`); `ChromaStore.add` only needs float vectors. Low risk.
- **Barrier timing:** a too-short barrier timeout makes the failing-first check flaky. Use about 2s, and tests only wait that long on a non-parallel implementation.
- **Import side effects:** `api.main` calls `setup_logging()` at import and installs the middleware. Harmless in tests. If `setup_logging` writes files, verify during implementation.
- **Not run in CI:** the CI command lists two files explicitly, so the new test is not run there unless the workflow is changed (needs explicit instruction).
- **Python/venv:** the checked-in venv lacks pytest/uvicorn (CLAUDE.md). Running tests needs a working environment. If none is available in implementation, the failing-first/passing run cannot be evidenced and that must be reported, not skipped silently.

## Migration notes
None. No API contract, data format or config changes. A request dir name changes, which is internal. Chroma collections and ids are unchanged.

## Verification (end-to-end)
1. Write the test first. Run `cd backend && pytest tests/test_upload_concurrency.py -v` on unmodified code: expect failures on AC1/AC2/AC3/AC4/AC5 (AC6/AC7 pass).
2. Apply the `main.py` change and re-run: all pass.
3. Run the exact CI command, `pytest tests/test_embedder.py tests/test_web_loader.py -v`: exit 0.
4. Optional manual: re-run the 03 §5 probe (4 parallel curl uploads, one session) against a local backend; expect `chunks` 1/1/1/1 and a collection total of 6.
5. Do not run `test_pipeline.py` (paid API).

## Implementation outcome (IMPL-G01-2026-09-26)
- `backend/api/main.py`: `tmp_dir` is now `/tmp/rag_sessions/{uuid.uuid4().hex}` with a 3-line comment, as planned. No other app file changed.
- `backend/tests/test_upload_concurrency.py`: created as planned (AC1–AC7 as 8 tests). Deviation: AC6 is split into two tests (response contract; error paths).
- **Verification run (same session, after building an env).** Env: throwaway venv at `~/.cache/claude-g01-venv` (outside the repo; Python 3.14.7), `requirements.txt` installed except `torch`, which is the CPU build from the PyTorch CPU index because the pinned wheel's `triton` download kept failing and `/tmp` (tmpfs) ran out of space. Nothing in the repo or the checked-in `venv/` was touched.
  - Unfixed code (`main.py` change stashed): `test_upload_concurrency.py` = 5 failed (AC1–AC5), 3 passed (AC6 x2, AC7). This is failing-first, as planned.
  - With the fix: 8 passed; repeated 5 more times, all 8 passed each time (no flakiness seen).
  - CI command `pytest tests/test_embedder.py tests/test_web_loader.py`: 32 passed, exit 0.
