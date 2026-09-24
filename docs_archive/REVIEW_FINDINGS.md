# Review Findings — AskMyDocs

Produced by `/loop-project`, reviewing the backend + frontend built across
the last two `/continue-project` sessions (the extracted rewrite, the
CPU device-pinning fix, the Next.js CVE bump, and the fresh web-ingestion
feature). Baseline before any fix: `pytest tests/test_embedder.py
tests/test_web_loader.py` — 23/23 pass; `npm run lint` — clean.

Each finding below is `[fix]` (safely auto-fixable) or `[flag]` (a
judgment call for a human). `/fix-review` acts on `[fix]` findings only.

---

## F1 — [fix] Path traversal / arbitrary file write via unsanitized upload filename

**File:** `backend/api/main.py` (`upload_documents`, around the `tmp_path = os.path.join(...)` line)

**Severity:** High (security)

**Issue:** `tmp_path = os.path.join(tmp_dir, file.filename)` uses the client-supplied multipart filename directly, with no sanitization. `os.path.join` with an absolute path as the second argument discards the first argument entirely (e.g. `os.path.join("/tmp/rag_sessions/x", "/etc/passwd")` → `/etc/passwd`), and a filename containing `../` sequences can escape `tmp_dir` even with a relative path. A malicious client can set `filename` to an absolute path or a `../../` traversal in the multipart request and have the server write attacker-controlled content to an arbitrary path the process can write to.

**Failure scenario:** `curl -F "files=@payload.txt;filename=/tmp/rag_sessions/../../home/user/.bashrc" http://api/upload` writes outside the intended session directory.

**Recommended fix:** Sanitize the filename before joining — take `os.path.basename(file.filename)` and reject (400) if the result is empty, `.`/`..`, or still differs suspiciously from the original (or simplest: reject if `file.filename` contains `/`, `\`, or `..` at all, matching the existing `validate_file` boundary-validation pattern in `src/utils/validators.py`).

**Status:** fixed — `validate_file()` in `src/utils/validators.py` now rejects any filename where `os.path.basename(filename) != filename`, or that is `.`/`..`, or contains a backslash. Verified: `pytest tests/test_embedder.py -k validate_file` (added `test_validate_file_rejects_absolute_path` and `test_validate_file_rejects_path_traversal`, both pass; existing 5 validator tests still pass).

---

## F2 — [fix] Non-Gemini LLM providers can crash on empty/None response content

**File:** `backend/src/generation/answer_chain.py` (`_answer_mistral`, `_answer_openai`, `_answer_anthropic`)

**Severity:** Medium (correctness / error handling)

**Issue:** `_answer_gemini` guards against an empty response with `response.text or NOT_FOUND_MESSAGE`, but the other three providers assign `answer_text` directly from the API response (`response.choices[0].message.content`, `message.content[0].text`) with no null/empty check, then immediately call `len(answer_text)` in the log line.

**Failure scenario:** if a safety filter or refusal causes the provider to return `None`/empty content (a documented real behavior for all three SDKs), `logger.info("...chars=%d", len(answer_text))` raises `TypeError: object of type 'NoneType' has no len()` — the request 500s with a confusing traceback instead of a sensible "no answer" response.

**Recommended fix:** Apply the same `answer_text = ... or NOT_FOUND_MESSAGE` fallback in `_answer_mistral`, `_answer_openai`, and `_answer_anthropic` that `_answer_gemini` already uses.

**Status:** fixed — all three now do `... or NOT_FOUND_MESSAGE` before the `len()` log call. Verified: `py_compile` clean; a full mocked round-trip test wasn't added because verifying `_answer_mistral` specifically surfaced F7 below (its import is currently broken independent of this fix) — `_answer_openai`/`_answer_anthropic`'s imports were confirmed still valid against the installed SDK versions, and the fix itself is a direct copy of the already-working `_answer_gemini` pattern.

---

## F3 — [fix] SSRF guard only validates the IPv4 address; a differing AAAA record can bypass it

**File:** `backend/src/ingestion/web_loader.py` (`_validate_url`)

**Severity:** Medium-High (security)

**Issue:** `_validate_url` resolves the hostname with `socket.gethostbyname(hostname)`, which only returns an IPv4 (A record) address. The actual fetch is done by `requests.get()`, which does its own DNS resolution and — depending on the system's `getaddrinfo` ordering — may prefer an IPv6 (AAAA) address if the hostname publishes one. A hostname that publishes a public A record (passes validation) alongside a private/internal AAAA record (e.g. `::1`, `fe80::...`, a ULA range) would pass the guard but could still be fetched over the unvalidated IPv6 address.

**Recommended fix:** Resolve with `socket.getaddrinfo(hostname, None)` instead of `gethostbyname`, and reject the URL if *any* returned address (IPv4 or IPv6) is private/loopback/link-local/reserved/multicast/unspecified, not just the first IPv4 one.

**Status:** fixed — `_validate_url` now uses `getaddrinfo` and checks every resolved address. Verified: added `test_validate_url_rejects_private_ipv6_even_with_public_ipv4` (mocks a hostname with a public IPv4 + private IPv6 address, confirms rejection) — all 9 `test_web_loader.py` tests pass.

---

## F4 — [fix] Ingestion failures in `/upload` and `/upload-url` aren't logged server-side

**File:** `backend/api/main.py` (`upload_documents`, `upload_url`)

**Severity:** Low-Medium (error handling / operability)

**Issue:** `/query`'s exception handler calls `logger.exception("Query failed")` before raising the `HTTPException`, so failures are visible in server logs. `/upload`'s and `/upload-url`'s `except Exception as e:` blocks raise `HTTPException(status_code=500, detail=f"...: {e}")` directly with no server-side log call — a production ingestion failure (e.g. a corrupt PDF, an unexpected ChromaDB error) is only visible to the client, not in the server's own logs, making it hard to debug after the fact.

**Recommended fix:** Add `logger.exception(...)` in both `except Exception` blocks, matching the pattern already used in `query_document`.

**Status:** fixed — both blocks now call `logger.exception(...)` before raising, identical pattern to `query_document`. Verified: `py_compile` clean; live server test confirmed the surrounding cleanup/response behavior is unaffected (`/upload-url` against a private-IP URL still correctly returns 400 and cleans up).

---

## F5 — [fix] Session-cleanup-on-failure logic duplicated 4x across the upload endpoints

**File:** `backend/api/main.py`

**Severity:** Low (maintainability / DRY)

**Issue:** The `if is_new_session: pipeline.chroma_store.delete_session(session_id)` pattern is repeated in `upload_documents` (2x) and `upload_url` (3x), each inline. Any future change to this cleanup logic (e.g. adding a log line) needs to be made in five places consistently.

**Recommended fix:** Extract a small helper, e.g. `def _cleanup_if_new(session_id: str, is_new_session: bool) -> None`, and call it from all five sites.

**Status:** fixed — `_cleanup_if_new()` added and used at all 5 call sites in `/upload` and `/upload-url`. Verified: `py_compile` clean, full test suite still 26/26, live server test confirmed a rejected `/upload-url` still cleans up the orphaned session correctly.

---

## F6 — [fix] `/query`'s `question` field has no length cap

**File:** `backend/api/main.py` (`query_document`), `backend/config.py`

**Severity:** Low (robustness / cheap resource-exhaustion vector)

**Issue:** File uploads are bounded by `MAX_FILE_SIZE_MB`, but `/query`'s `question` string has no equivalent cap — a client can submit an arbitrarily large string, which gets embedded (and potentially reranked against) at full cost. This is a system boundary (public API) that the codebase's own convention (config-driven limits, validated before use) already covers for file uploads but not for this field.

**Recommended fix:** Add a `MAX_QUESTION_LENGTH` setting (config.py, e.g. default 2000 chars, following the same `_optional`/env-var pattern as the existing limits) and reject (400) questions longer than that in `query_document`, before calling `pipeline.ask()`.

**Status:** fixed — `settings.max_question_length` (default 2000, `.env.example` documented) added; `query_document` rejects with 400 before calling `pipeline.ask()`. Verified live over HTTP: a 2500-char question got rejected with the expected message; a normal question still passed through to the grounding gate/LLM call unaffected.

---

## F7 — [flag → fixed] `mistralai==2.9.4` no longer exports `Mistral` from the top-level package — `_answer_mistral` will ImportError at runtime

**File:** `backend/src/generation/answer_chain.py` (`_answer_mistral`)

**Severity:** High (correctness — the `mistral` LLM provider path is completely broken, not just an edge case)

**Discovered while verifying F2** (not originally in scope): `_answer_mistral` does `from mistralai import Mistral`. Confirmed by direct import in this project's venv that this raises `ImportError: cannot import name 'Mistral' from 'mistralai'` — the installed `mistralai==2.9.4` restructured its package (client code moved under `mistralai.client`; `from mistralai.client import Mistral` works, `from mistralai import Mistral` does not). This means **every attempt to use `LLM_PROVIDER=mistral` fails immediately**, not just on malformed input — a much more serious break than F2's edge case.

**Why this is `[flag]` and not fixed inline:** per the run's scope rule ("if you spot something extra, add it as a new finding instead of fixing it inline"), this wasn't part of the original review pass and its fix should be reviewed/verified on its own, not folded into F2's diff. It's also worth a human decision on whether to pin `mistralai` to an older, still-`Mistral`-exporting version instead of changing the import (both are valid; changing the import keeps the newer SDK, repinning is more conservative) — see `PROJECT_DECISIONS.md`'s open questions on provider pins.

**Recommended fix (either one):**
1. Change the import to `from mistralai.client import Mistral`, or
2. Pin `mistralai` in `requirements.txt` to a version that still exports `Mistral` at the top level, and verify which version that last was.

Either way, this needs an actual `MISTRAL_API_KEY` to verify end-to-end (or at minimum, a mocked test asserting the import + client construction succeed) before calling it fixed — not done as part of this pass.

**Resolution (follow-up pass):** asked the user whether upgrading `mistralai` would fix this on its own before picking an approach — checked directly and `2.9.4` is already the latest available version, so an upgrade alone cannot help; the import genuinely has to change. Fixed by changing `from mistralai import Mistral` to `from mistralai.client import Mistral`, keeping the current SDK version rather than downgrading (per D19's option 1).

**Status:** fixed — verified three ways: (1) `py_compile` clean, (2) `from mistralai.client import Mistral` imports and `Mistral(api_key=...)` constructs with `chat.complete` present, (3) calling `_answer_mistral()` directly with a fake key reaches the real Mistral API and returns `SDKError: API error occurred: Status 401. Body: {"detail":"Invalid API Key"}` — proving the whole path works up to needing a real key, not an import/attribute error. Full regression suite: 26/26 pass. Still needs a real `MISTRAL_API_KEY` to confirm the happy path end-to-end, same caveat as the other 3 providers.

---

## Summary

All 7 findings are now fixed and verified — 6 `[fix]` items from the
original pass, plus F7, which surfaced mid-verification, was correctly
held back as `[flag]` at the time, and was fixed in a follow-up pass
once the user confirmed the right approach (upgrading `mistralai`
wouldn't help, since 2.9.4 is already latest — so the import itself
needed to change). Final state: `pytest tests/` (excluding the
LLM-key-gated `test_pipeline.py`) — **26/26 pass** (3 new regression
tests: 2 for F1, 1 for F3). Frontend was untouched this pass (no
findings touched it), so `npm run build`/`lint` weren't re-run.

Known, already-accepted trade-offs (DNS rebinding on URL ingestion, no
auth/rate-limiting, OCR for scanned PDFs, `RELEVANCE_THRESHOLD`
calibration) are recorded as open decisions in `PROJECT_DECISIONS.md`
and weren't re-flagged here.
