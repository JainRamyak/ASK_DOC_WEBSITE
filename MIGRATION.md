# Applying this to your GitHub repo (JainRamyak/ASK_DOC_WEBSITE)

Do these in order. Step 1 blocks everything after it — a 1.1GB file
in your working directory will make `git push` fail outright.

## 1. Clean up repo cruft (do this first — it blocks step 3 otherwise)

Your working directory has accumulated files that were never meant to
be part of the actual project:

```bash
cd /path/to/your/local/clone

# The entire original dead project (pre-rewrite), including its own
# embedded 200MB+ old codedump.md
rm -rf ASK_MY_DOC/

# Root-level dump/deliverable files — NOT project code, over 1GB combined
rm -f codedump.md code.md AskMyDocs_Full_Codebase.md

# Optional: REVIEW_FINDINGS.md is legitimate and useful (documents 7
# real bug fixes) — keep it, or move it into docs_archive/ if you'd
# rather it not sit at repo root:
mkdir -p docs_archive
mv REVIEW_FINDINGS.md docs_archive/ 2>/dev/null || true

# .claude/launch.json is a harmless Claude Code debug config — fine to
# keep or gitignore, no secrets in it, your call
```

Verify nothing huge is left before continuing:
```bash
du -sh * .[^.]* 2>/dev/null | sort -rh | head -10
```
Nothing here should be anywhere near 100MB — GitHub hard-rejects any
single file over that size.

## 2. Rotate every API key

Your old `.env` (OpenAI, Anthropic, Gemini, Mistral keys) was pasted
into a chat as part of a code dump. Treat all four as compromised:

1. Go to each provider's dashboard and revoke/regenerate:
   - platform.openai.com → API keys
   - console.anthropic.com → API keys
   - aistudio.google.com → API keys
   - console.mistral.ai → API keys
2. Only put the *new* keys in your local `backend/.env` — never in
   code, never in a commit, never pasted into a chat again.

**Note:** the live repo's git history was checked directly
(`git log --all -- backend/.env` against `JainRamyak/ASK_DOC_WEBSITE`)
and zero commits ever touched that path — the leaked keys were in a
chat/file dump, not committed to git. That means a `git filter-repo`
history purge is very likely unnecessary. Still rotate the keys
regardless — they were exposed to a chat log either way — but run
`git log --all --full-history -- backend/.env` yourself before
assuming this and before doing anything destructive to git history.

## 3. Replace the code with the merged version

```bash
cd /path/to/your/local/clone

# Remove everything except .git and whatever you chose to keep from step 1
git rm -rf --cached .
find . -mindepth 1 -maxdepth 1 ! -name '.git' ! -name 'docs_archive' -exec rm -rf {} +

# Copy in the merged project (unzip wherever you downloaded it)
cp -r /path/to/askmydocs/* .
cp -r /path/to/askmydocs/.github .
cp /path/to/askmydocs/.gitignore .

git add .
git status   # sanity-check: should NOT show ASK_MY_DOC/, codedump.md, code.md
git commit -m "Merge: reconcile independent bug-fix session with rate limiting, session cleanup, OCR, query rewriting; remove repo cruft"
git push origin main
```

## 4. Set environment variables in each hosting dashboard

- **Render**: Dashboard → your service → Environment → set the
  rotated `GEMINI_API_KEY`. `render.yaml` defines the rest with
  working defaults — review them, but you shouldn't need to set most
  manually. Confirm `EMBEDDER_TYPE=gemini` (not `local`) is actually
  applied if you're on the free plan.
- **Vercel**: Project → Settings → Environment Variables →
  `NEXT_PUBLIC_API_URL` = your Render backend URL, must start `https://`.

## 5. Verify before trusting any of it

```bash
cd backend && pip install -r requirements.txt
pytest tests/test_embedder.py tests/test_web_loader.py -v   # should be clean, no LLM key needed
cd ../frontend && npm install && npm run build               # never verified in my environment
```
See `SESSIONS.md` for the full verification runbook, and
`BUILD.md` for what's still outstanding after this merge.

## 6. Update the repo itself

- The GitHub "About" description should match current reality
  (ChromaDB + cross-encoder rerank + grounding gate, live-URL
  ingestion, rate limiting, session cleanup — not the old FAISS/BM25
  claims from the very first version).
- Review and close-or-rebase the one pull request that predates all
  of this, if it's still open.
