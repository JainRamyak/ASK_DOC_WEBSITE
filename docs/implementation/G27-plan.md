# Implementation Plan: G27 — Dedup identical re-uploads within a session

Session: PLAN-G27-2026-09-27 · Branch `fix/G27-dedup-reupload` (base `main` @ `d8760a5`, verified equal to `origin/main`) · Spec `docs/specs/G27.md` (APPROVED)

## Implementation outcome (IMPL-G27-2026-09-27)
Implemented exactly as designed below — no plan row required revision. All 9 new tests in `backend/tests/test_upload_dedup.py` pass, plus the 25 existing G01/G02 regression tests (2 with the pre-planned assertion updates) and the CI command (32 tests). `backend/tests/test_pipeline.py` was not run (needs an LLM key; CLAUDE.md). `collection.get(where=..., limit=1, include=[])` was confirmed working against the installed chromadb 1.5.9 before writing `ChromaStore.add()` (see Risks below — 0.6.3 was not checked, flagged for validation). Frontend `npm run lint` and `npm run build` both pass with no new errors. A real backend (uvicorn, local embedder, no API keys) was smoke-tested over HTTP: uploading the same file twice to one session returns `already_indexed` with the file's actual SHA-256 hash on the second call, and the collection holds exactly one copy of the chunk (verified by reading the chroma store directly). AC11's full browser-driven UI check was not done in this session — left for validation, matching the precedent set by G02's AC11.

## Context
`docs/specs/G27.md` is APPROVED (Option B, resolved 2026-09-27): re-uploading a file whose bytes are already indexed in a session must not create a second copy of its chunks. Identity is the SHA-256 hash of the file's raw bytes (or, for `/upload-url`, of the fetched/extracted text). A repeat is reported truthfully via a new, additive `already_indexed` field — never silently merged into `filenames` or G02's `skipped`. Today `ChromaStore.add()` always appends with positional ids and nothing anywhere computes or stores a content identity, so every re-upload doubles that file's chunks with no signal to the user.

This plan implements Option B end-to-end: hashing, a dedup-aware store write, pipeline plumbing, the two endpoint responses, and the frontend display — while leaving G01's staging, G02's skip-reporting, retrieval, and the chunk-id scheme untouched, per the spec's Regression Requirements.

## Design

### 1. `backend/src/storage/chroma_store.py` — dedup-aware `add()`
Extend `add(session_id, chunks, embeddings, metadatas)` in place (same signature, same callers) so it:
- Reads `metadatas[i].get("content_hash")` per chunk. A chunk with no `content_hash` is always kept (preserves today's behavior for any caller that doesn't stamp one — none in this codebase after this change, but keeps `chunk_documents`'s output self-consistent for its own tests).
- For each **unique** hash present, checks once — under the existing `self._add_lock` — whether `collection.get(where={"content_hash": h}, limit=1, include=[])["ids"]` already has a match. If yes, every chunk with that hash is dropped from this call. If no, every chunk with that hash is kept, and the hash counts as "newly added."
- Assigns ids to the surviving chunks with the unchanged `f"{session_id}_{existing_count + i}"` scheme (no deletes anywhere in this design, so the positional scheme stays valid — Regression Requirements).
- Returns `set[str]` of hashes that were newly added (was `None`; additive change, no caller currently uses the return value).
- Doing the check-then-add inside the current `_add_lock` block is what makes this race-safe (R6): two concurrent uploads of the same file to the same session serialize through this one call, so only one of them can "win" the hash.

### 2. `backend/src/pipeline.py`
- Add `import hashlib` and a small `_hash_file(path: Path) -> str` module function (streamed SHA-256, matches R1: hash of raw bytes).
- `IngestResult` gains `already_indexed: dict = field(default_factory=dict)` (filename/url → hash).
- `ingest_with_report(directory, session_id)`:
  1. `docs = load_documents(directory)` — unchanged call, unchanged signature (Regression Requirements).
  2. Hash each on-disk file that produced at least one doc: `file_hashes = {f: _hash_file(Path(directory)/f) for f in {d["file"] for d in docs}}`.
  3. **Within-batch dedup first**: walk `docs` in order, and for each file's hash, the *first* file to show that hash is the batch "winner"; any later file in the same request sharing that hash (same content under any name — covers the spec's explicit same-name case and the general same-content case) never reaches the store. This is what makes the "two identical files in one request" edge case correct — the DB-level check alone can't see it, since neither has been stored yet.
  4. Stamp `d["content_hash"]` only on docs belonging to winner files; pass only those docs into `_store_docs`.
  5. `_store_docs` now returns `(added_count, added_hashes)` (see below). Build:
     - `indexed = {f for f in all_files if f is a winner and file_hashes[f] in added_hashes}` (gated by `count` as today, for the existing "0 aggregate chunks ⇒ nothing claimed indexed" defensive style).
     - `already_indexed = {f: file_hashes[f] for f in all_files if f is not a winner, or its hash was not in added_hashes}`.
  6. Return `IngestResult(chunks=added_count, indexed=indexed, skipped=skipped, already_indexed=already_indexed)`.
- `_store_docs(docs, session_id)` changes its return from `int` to `tuple[int, set[str]]`: chunk the docs, embed all of them (no pre-embed dedup — see Risks), call the extended `chroma_store.add()`, and compute `added_count` as the number of chunks whose `content_hash` is `None` or is in the returned `added_hashes` set.
- `ingest(directory, session_id) -> int` stays exactly `self.ingest_with_report(...).chunks` — untouched, satisfies the protected `pipeline.ingest` contract.
- `ingest_url(url, session_id)` changes its return from `int` to `IngestResult` (its only caller is `/upload-url`; the only test stubbing it is updated in step 4). Body: fetch via `load_url` (unchanged), hash `docs[0]["text"]` with SHA-256 (R1's URL identity), stamp it, call `_store_docs`, and return `IngestResult(chunks=count, indexed={url})` if the hash was newly added, else `IngestResult(chunks=0, already_indexed={url: content_hash})`.

### 3. `backend/src/ingestion/chunker.py`
`chunk_documents` copies `doc["content_hash"]` into each resulting chunk dict **only if present** on the input doc — one line, fully additive. Existing callers that build doc dicts without `content_hash` (e.g. `_expected_chunks` in the test suite) are unaffected.

### 4. `backend/api/main.py`
- `/upload`: replace the current two-way `skipped` partition loop with a three-way partition over `staged`: a file lands in `filenames` (via `result.indexed`), `already_indexed` (via `result.already_indexed`, `{"filename": original, "hash": ...}`), or `skipped` (today's fallback), in that priority order — mirrors the existing "every file lands in exactly one list" structure, just extended.
- Change the failure gate from `if result.chunks == 0:` to `if result.chunks == 0 and not result.already_indexed:` — a batch that is entirely repeats is a 200 with `chunks: 0`, not the "no readable text" 400 (a genuinely-all-unreadable batch, with no repeats, is unaffected and still 400 — G02's AC6 stays true).
- Add `"already_indexed": already_indexed` to the response dict.
- `/upload-url`: `result = await run_in_threadpool(pipeline.ingest_url, ...)` now returns an `IngestResult`. Same gate change (`result.chunks == 0 and not result.already_indexed`). Response gains `"already_indexed"` (0 or 1 entries, keyed by the URL string) and `"filenames"` becomes `[url] if result.indexed else []` (was unconditional — a repeat URL now correctly reports no new filename).

### 5. Frontend
- `frontend/lib/types.ts`: add `already_indexed?: { filename: string; hash: string }[];` to `UploadResponse`, following the same optional-field pattern as `skipped?`.
- `frontend/app/app/page.tsx`: add `alreadyIndexed` state alongside `skipped`, updated identically in `handleUpload`/`handleUrlSubmit` (append vs. replace, same shape as the existing `skipped` handling) and cleared wherever `filenames`/`skipped`/`chunkCount` are reset. Render a small informational block near the existing amber "skipped" banner — neutral styling (not a warning color), text like "`<name>` was already indexed" — per R10 it must not read as an error and must not double the accumulated file list (it already won't, since `already_indexed` items never appear in `filenames`).
- No change needed to `frontend/lib/api.ts` (generic JSON passthrough).
- After `npm install` (needed anyway — `node_modules` absent), read `node_modules/next/dist/docs/` per `frontend/AGENTS.md` before touching `page.tsx`, then run `npm run lint` && `npm run build`.

## Requirement → Change → Test → Verification

| Spec req/AC | Code change | Test | Verification |
|---|---|---|---|
| R1 (identity) | `pipeline._hash_file`; `ingest_url`'s `hashlib.sha256(text)` | AC1/AC2 assert exact hash-bearing responses | pytest |
| R2, AC1 | `ingest_with_report` hash-check-before-store; `ChromaStore.add()` dedup | `test_upload_dedup.py::test_identical_reupload_is_skipped` | pytest + collection count assertion |
| within-batch edge case | `ingest_with_report` winner-per-hash pass | `test_upload_dedup.py::test_duplicate_within_one_batch` (same name and different name) | pytest |
| AC2 (content, not name) | same as R2 | `test_upload_dedup.py::test_rename_is_still_a_repeat` | pytest |
| AC3 (same name, new content) | winner logic keys on hash, not name | `test_upload_dedup.py::test_same_name_different_content_indexes_both` | pytest |
| AC4 (3-way partition) | `main.py` partition loop | `test_upload_dedup.py::test_mixed_batch_partitions_correctly` | pytest |
| AC5, R6 (concurrency) | `ChromaStore.add()` lock-scoped check+add | `test_upload_dedup.py::test_concurrent_identical_reupload` (reuses `_install_gate`) | pytest, run a few times locally |
| AC6, R5 (session isolation) | per-session collection scoping (unchanged) | `test_upload_dedup.py::test_same_content_different_sessions_both_index` | pytest |
| AC7 (regression) | — | `test_upload_concurrency.py`, `test_upload_skipped_files.py` (with the two named test updates below) | run unmodified test files, confirm pass |
| AC8, R4 (`/upload-url` parity) | `ingest_url` → `IngestResult`; `main.py` gate + response | `test_upload_dedup.py::test_upload_url_repeat` (stub `pipeline_module.load_url`) | pytest |
| AC9, R9 (retrieval untouched) | none — `retrieve_and_rerank`/`answer_chain` not touched | diff review; optional smoke query test | manual + code review |
| AC10 (types/lint/build) | `types.ts`, `page.tsx` | — | `npm run lint`, `npm run build` |
| AC11 (manual UI) | `page.tsx` banner | — | manual: upload, re-upload, observe banner + question still works |
| AC12 (CI) | — | — | `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` |

### Required updates to existing tests (approved, additive — not drive-by)
- `test_upload_concurrency.py::test_sequential_new_and_append_response_contract` (line 270): `assert set(first) == {...}` gains `"already_indexed"`.
- `test_upload_skipped_files.py::test_upload_url_response_is_unchanged` (line 165): the stub `lambda url, session_id="default": 3` must become `lambda url, session_id="default": IngestResult(chunks=3, indexed={url})` (import `IngestResult` from `src.pipeline`), and its key-set assertion gains `"already_indexed"`.

## Files
- `backend/src/storage/chroma_store.py` — `add()` extended
- `backend/src/pipeline.py` — hashing, `IngestResult.already_indexed`, `ingest_with_report`, `_store_docs`, `ingest_url`
- `backend/src/ingestion/chunker.py` — one-line `content_hash` passthrough
- `backend/api/main.py` — `/upload`, `/upload-url` response building and 400-gate
- `backend/tests/test_upload_dedup.py` — new
- `backend/tests/test_upload_concurrency.py` — one assertion updated
- `backend/tests/test_upload_skipped_files.py` — one stub + assertion updated
- `frontend/lib/types.ts` — `UploadResponse.already_indexed`
- `frontend/app/app/page.tsx` — `alreadyIndexed` state + banner

## Risks / notes
- **Embedding not pre-filtered**: `_store_docs` still embeds every chunk (including ones later dropped as duplicates by `chroma_store.add()`), since the DB-level dedup happens after chunk/embed. This is correct but not maximally efficient on a repeat upload of a large file. Not required by any AC; flagged, not fixed here.
- **`chromadb` version pin mismatch** (pre-existing, per CLAUDE.md — not to be "fixed" here): `requirements.txt` pins `1.5.9` (local venv), `requirements.prod.txt` pins `0.6.3` (Docker/Railway). The `where={"content_hash": h}` equality-filter and `include=[]` are standard, long-stable Chroma API surface, but this plan's implementation session should sanity-check `collection.get(..., include=[])` doesn't error against whichever version is actually exercised, and note if `0.6.3` needs `include=["metadatas"]` instead of `[]`.
- Environment blocker carried over from specification: `backend/venv` currently lacks `pytest`/`chromadb`/`fastapi`. The implementation session must get these importable before writing/running `test_upload_dedup.py`.

## Verification (end-to-end)
1. Backend: `cd backend && pytest tests/test_upload_dedup.py tests/test_upload_concurrency.py tests/test_upload_skipped_files.py -v` — all green.
2. CI parity: `pytest tests/test_embedder.py tests/test_web_loader.py -v` from `backend/` exits 0 (AC12).
3. Frontend: `cd frontend && npm install && npm run lint && npm run build`.
4. Manual: run backend + frontend locally (local embedder), upload a file, upload the identical file again — banner shows it as already indexed, not double-counted, question box still works (AC11).
