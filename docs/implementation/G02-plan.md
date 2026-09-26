<!-- Plan for docs/specs/G02.md (APPROVED). Branch: fix/G02-report-skipped-files, from main @ d782338. -->
# G02 implementation plan — report skipped files truthfully on `/upload`

## Context
`/upload` lists every saved file as "indexed" even when the loader produced no text for it (`api/main.py` echoes `saved_filenames`; `loader.py` swallows per-file failures and returns `[]`; `pipeline.ingest` returns only an int). Spec `docs/specs/G02.md` (approved by the user this session as written; tolerant mixed-batch policy kept, D-U11 untouched) requires: `filenames` = files that contributed ≥1 chunk; a new always-present `skipped` list (`filename` + reason, "could not be read" vs "no extractable text"); correct handling of duplicate names; UI shows skipped files. Base: `main` @ `d782338` (G01 merged).

Decisions taken this session
- User approved spec → on start of implementation set `Status: APPROVED` in `docs/specs/G02.md`.
- User chose: edit the single G01 assertion `test_sequential_new_and_append_response_contract` (key set now includes `skipped`, asserted `[]`). Amend spec AC8 to "unmodified except this assertion". No other G01 test edits.
- User chose: persistent local test venv → `backend/venv/` (already gitignored in `.gitignore` and `backend/.gitignore`), Python 3.14 (matches the `requirements.txt` pins; CI's 3.11 is a known inconsistency, not fixed).

## Design (mechanism; satisfies R1–R11)
Hard constraint found: `test_upload_concurrency.py::_install_gate` monkeypatches `pipeline_module.load_documents` with `gated(directory)` → `real(directory)`. So `pipeline.ingest*` must keep calling `load_documents(directory)` with exactly one arg, and its return must pass through the wrapper. `tests/test_pipeline.py` and `scripts/calibrate_threshold.py` need `ingest()->int` and `load_documents()->list[dict]` unchanged.

1. **Loader** (`backend/src/ingestion/loader.py`)
   - `load_documents(directory)` keeps signature; returns `LoadedDocuments`, a `list` subclass (list of `{"text","source",...}` as today) with an extra `.skipped: dict[str, str]` mapping on-disk filename → reason code (`"unreadable"` | `"no_text"`). Each doc dict also gets `"file": filepath.name` (chunker copies only text/source/page/chunk_index, so it is never stored in Chroma metadata).
   - Private `_load_text/_load_docx/_load_pdf` stop swallowing: parse/open failures raise a private `_UnreadableFile` (logged as today). `ImportError` still propagates exactly as today. `_load_pdf` mid-file failure with some pages already extracted still returns those pages (current behavior); with none, raises.
   - Per-file in `load_documents`: `_UnreadableFile` → `skipped[name]="unreadable"`; empty result → `skipped[name]="no_text"`. Unsupported extensions stay silently ignored (unreachable from `/upload`; `validate_file` rejects them).
2. **Pipeline** (`backend/src/pipeline.py`)
   - New `ingest_with_report(directory, session_id) -> IngestResult(chunks:int, indexed:set[str], skipped:dict[str,str])` (small dataclass). It calls `load_documents(directory)` (gate-compatible), `_store_docs`, and computes `indexed` = `{d["file"] for d in docs}` (A2: non-empty text ⇒ ≥1 chunk; covered by a test).
   - `ingest()` becomes `return self.ingest_with_report(...).chunks` — same int, same logging.
3. **Endpoint** (`backend/api/main.py` `/upload`)
   - Keep `staged: list[tuple[original, disk_name]]` instead of `saved_filenames`.
   - U4 fix (R4): after `disambiguate_filename`, loop while `disk_name` already used in this batch (`used_disk_names` set) and call it again. Resolves `a.txt, a.txt, a (1).txt` collisions that today silently overwrite a staged file. Touches only the previously-buggy collision case; `validators.py` untouched.
   - Call `pipeline.ingest_with_report` via `run_in_threadpool`. Then: `filenames=[orig for orig,disk in staged if disk in result.indexed]`; `skipped=[{"filename": orig, "reason": code, "message": MSG[code]} for ... if disk not in indexed]` (unknown/missing outcome falls back to `no_text` so every uploaded file is in exactly one list, R2).
   - Response adds `skipped` (always a list). `chunk_count == 0` → 400 with unchanged message and `_cleanup_if_new`; all other error paths untouched. `/upload-url` untouched.
   - User-safe messages (module constants, no exception text/paths/disk names): `unreadable` → "Couldn't be read — the file may be corrupt or not a valid document."; `no_text` → "No text could be extracted — it may be empty, made of scanned images, or contain only tables." (does not claim OCR is available). Wording is spec Unknown U3 → flag for human review at PR time.
4. **Frontend**
   - Before writing any code: `npm install` in `frontend/` and read the relevant guide(s) under `node_modules/next/dist/docs/` (`frontend/AGENTS.md`, `frontend/CLAUDE.md`).
   - `frontend/lib/types.ts`: add `SkippedFile {filename; reason: "unreadable"|"no_text"; message}` and optional `skipped?: SkippedFile[]` on `UploadResponse` (optional because `/upload-url` doesn't send it, R11).
   - `frontend/app/app/page.tsx`: new `skipped` state, accumulated on append and reset on a new session (satisfies AC11; backend reports latest request only). Both `handleUpload` and the (untouched-semantics) URL handler keep `filenames` = indexed only. Render a compact, non-blocking notice under the banner listing `shortName(filename) — message`; questioning stays enabled.

## Requirement → change → test → verification
| Req / AC | Code change | Test | Verify |
|---|---|---|---|
| R1, R2, R6 / AC1, AC4 | endpoint builds `filenames`/`skipped` from `IngestResult`; loader `.skipped`/`"file"` | `test_skipped_file_not_reported_indexed` (good + whitespace-only; also asserts stored count == `chunks`); `test_every_upload_in_exactly_one_list` | pytest; must FAIL on current `main` first |
| R3 / AC2 | loader `_UnreadableFile` vs empty; message constants | `test_reason_categories_and_safe_messages` (good + blank + non-PDF bytes as `broken.pdf`; assert differing reason codes, no `Traceback`/`/tmp`/`rag_sessions`/exception-class text) | pytest (needs pymupdf installed) |
| R4 / AC3 | `used_disk_names` loop in endpoint | `test_duplicate_names_attributed_correctly` (both orders); `test_literal_name_collision_with_disambiguated` (`a.txt, a.txt, a (1).txt` → all 3 handled, none overwritten) | pytest |
| R5, R7 / AC5, AC6, AC7 | additive `skipped: []` | new sequential new+append asserts `skipped == []`; all-skipped → 400 + message + no orphan session + existing session survives; existing `test_error_paths_unchanged` unchanged | pytest |
| R9, R10 / AC8 | `ingest`/`load_documents` contracts preserved; gate still hits `pipeline_module.load_documents` | full `test_upload_concurrency.py` (one assertion edited, see above) + new `test_concurrent_upload_with_a_blank_file_reports_correctly` | pytest |
| R11 / AC9 | none to `/upload-url` | `test_upload_url_response_unchanged` calling `api.upload_url` with `pipeline.ingest_url` monkeypatched; record in validation | pytest |
| Regression: callers | `ingest()->int`, `load_documents()->list` | `test_ingest_still_returns_int` and `test_load_documents_result_is_plain_list_of_dicts` (isinstance list, keys `text`,`source`); A2 test: chunking any non-empty text yields ≥1 chunk | pytest |
| R8 / AC10, AC11 | types.ts, page.tsx | none (no frontend test framework; D-META3) | `npm run lint`, `npm run build`; manual UI pass (AC11) doubles as V-F28 for this area |
| AC12 | — | CI command unchanged | `pytest tests/test_embedder.py tests/test_web_loader.py -v` exits 0 |

## Files
Modify: `backend/src/ingestion/loader.py`, `backend/src/pipeline.py`, `backend/api/main.py`, `backend/tests/test_upload_concurrency.py` (one assertion), `frontend/lib/types.ts`, `frontend/app/app/page.tsx`, `docs/specs/G02.md` (Status → APPROVED; AC8 wording), `docs/PROJECT_BACKLOG.md` (G02 status line).
Create: `backend/tests/test_upload_skipped_files.py` (imports the `api`/`api_main` fixtures and helpers from `tests.test_upload_concurrency` to reuse the stubbed embedder — no duplication, no G01 file changes beyond the one assertion), `docs/implementation/G02-plan.md`, `docs/handoffs/PLAN-G02-<date>-plan.md`.
Not touched: `validators.py`, `chroma_store.py`, `chunker.py`, `/upload-url`, CI, deploy configs, CORS/allowlists, `test_pipeline.py`, `scripts/`.

## Steps (implementation session order)
0. Env: `python3 -m venv backend/venv` (gitignored), `pip install -r backend/requirements.txt` (network; heavy: torch). Confirm `pytest tests/test_upload_concurrency.py -v` passes on `main` as baseline. Do not touch root `venv/`.
1. Branch: `git fetch`; confirm `main` == `origin/main` (currently `d782338`; local tree only has untracked/modified docs, same as G01 — surface, don't stash); `git switch -c fix/G02-report-skipped-files`.
2. Write `test_upload_skipped_files.py` first; run against unmodified code; AC1/AC2/AC3 must fail (converts spec Unknown U1 to observed).
3. Implement loader → pipeline → endpoint; edit the one G01 assertion; all backend tests green.
4. Frontend: `npm install`, read Next docs, implement, lint + build, manual UI run (AC11).
5. Run CI command; do NOT run `test_pipeline.py` (paid API) without OK.

## Risks
- pymupdf's behavior on non-PDF bytes named `.pdf` (assumed to raise → `unreadable`); verified in step 2, adjust fixture (e.g. truncated real PDF) if not.
- Torch/sentence-transformers install size/time for the venv; tests use stubs so nothing is downloaded at test time.
- Python 3.14 venv vs CI 3.11: green locally ≠ green in CI; noted, not fixed.
- `LoadedDocuments` list-subclass carries data implicitly; mitigated by a plain-list contract test and a docstring.
- Frontend written against un-rendered UI (V-F28) and un-read Next 15.5 docs until step 4.
- U3 wording and CI wiring (U2) remain human decisions; CI left unchanged.
- Out-of-scope observation to log via `found-but-out-of-scope-template.md`: none found beyond the `a (1).txt` overwrite, which this plan fixes only insofar as R4 requires.

## Verification (end-to-end)
`cd backend && venv/bin/pytest tests/test_upload_skipped_files.py tests/test_upload_concurrency.py -v`; CI command; `cd frontend && npm run lint && npm run build`; manual: run backend + frontend locally, upload `good.txt` + blank + corrupt PDF, check banner/skipped notice, then append another skipped file.

---
## Implementation outcome (IMPL-G02-2026-09-26)
All plan rows implemented as planned, with these differences:
- **Env:** first `pip install` failed with `ENOSPC` because pip unpacked into `/tmp` (a 3.9G tmpfs) and the torch wheels exceed it. Re-run with `TMPDIR=~/.cache/pip-tmp` succeeded. `backend/venv/` (py3.14) is now the persistent test env.
- **Tests:** written first and run on unmodified code: 8 failed for the expected reasons (`KeyError: 'skipped'`; blank/duplicate names listed as indexed); 9 caller-contract/regression tests and all 8 G01 tests passed. pymupdf raises `FileDataError` on non-PDF bytes, so the `unreadable` assumption held. After implementation: 25/25 pass (`test_upload_skipped_files.py` + `test_upload_concurrency.py`); CI command 32/32 pass.
- **Frontend docs:** `frontend/AGENTS.md` says to read `node_modules/next/dist/docs/`; that directory does not exist in the installed Next 15.5. The change only adds React state and JSX to an existing client component (no Next APIs). `npm run lint` clean; `npm run build` succeeds.
- **Not done here (validation session):** manual UI check (AC11) and the AC9 note that `/upload-url` is covered by a stubbed-`ingest_url` test, not a real fetch.
- One code-style tweak vs. plan: `skipped` list built with a plain loop, not a comprehension.
