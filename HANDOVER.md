# HANDOVER.md

**Relay baton. Read this, then DELETE this file, then continue the work.**
A stale handover from two sessions ago poisons the current one. Pick it up,
throw it away, keep running.

**Written:** 2026-07-29 · P0 steps 1–3 complete · `main` @ `27f822c`

---

## 0. Read these first, in this order

1. `CLAUDE.md` — the working agreement. **§7 behavioural rules are literal**
   (one step at a time, explain before *and* after, show options and wait,
   status line at the end of every step). **§8 has eight learned rules; six of
   them were added this session.** Do not re-learn them.
2. `SPEC.md` — the blueprint. **Read-only.** It still contains one known-wrong
   claim (see §5 Gotcha 1). Corrections go in `CLAUDE.md` §8, never into SPEC.
3. `.claude/soul.md` — git-ignored, exists only on the author's machine. If
   absent: MS AI student at Kent State, graduating May 2026. **Strong** in
   Python / pandas / ML / DL / Streamlit. **Beginner** at RAG, LangChain,
   embeddings, vector stores, chunking, prompt design, Ollama — wants those
   taught thoroughly. Direct tone, no filler, no cushioning. **Blunt ≠ terse:**
   generous explanation is the deliverable, not padding.

---

## 1. What this project is

**Cliopedia** — a local, open-source RAG study assistant for history students.
Question → retrieve passages from a document library → an open LLM answers using
**only** those passages → answer displayed with citations to the exact page.

Portfolio project. Audience: a hiring manager reading the repo cold, and the
author defending it in an interview. **The citation is the product**, not a
feature. An answer that can't be traced to a source has failed.

---

## 2. What was accomplished this session

Sixteen commits, all on `main`. Chronological:

| Commit | What |
|---|---|
| `3a2c7cc` | removed the previous `HANDOVER.md` on pickup |
| `475e3e8` | `requirements.txt` + `.env.example` |
| `6a69c2e` | Rule 1 — LangChain 1.x package split |
| `d575032` | **corpus licence corrected to CC BY-NC-SA 4.0**; branching rule rewritten |
| `1442384` | `scripts/download_sources.py`, `.gitignore` gains `data/raw/` |
| `c02519d` | Windows setup commands promoted to first-class blocks |
| `da82d2b` | Rule 5 — commit-message quoting |
| `1c38a64` | Rule 6 — history-rewrite safety |
| `e467100` | download: compare bytes against `Content-Length` |
| `faec8b6` | download: `--inspect` diagnostic mode |
| `898d39e` | `DEFAULT_URL` marked known-broken; EOF scan widened to 128 KiB |
| `6107d11` | **switched to the WEB edition PDF**; verify `%%EOF` on download |
| `b05e825` | refreshed `CLAUDE.md` §3 commands |
| `5537d9f` | licence match across line breaks |
| `7b0695b` | licence match on a canonical form |
| `27f822c` | **`cliopedia/config.py`** + `cliopedia/__init__.py` |

**P0 progress: steps 1–3 of 8 done.** Dependencies, config, corpus fetcher.

---

## 3. Current state

### Works, verified

- **`requirements.txt`** — exact `==` pins, resolved together with
  `pip install --dry-run` (140 packages, exit 0, PyTorch 2.13.0 included).
- **`.env.example`** — all six variables documented, no secrets.
- **`scripts/download_sources.py`** — verified end to end on the author's
  Windows machine. Downloads, validates `%PDF-` header **and** `%%EOF` tail,
  reports page count, extracts and checks the licence.
  `--inspect` vets a URL without downloading it.
- **`cliopedia/config.py`** — tested for: non-numeric / zero / negative
  `RETRIEVAL_K` rejection, default when blank, relative vs absolute
  `CHROMA_DIR`, import from an unrelated cwd with no LLM vars, frozen
  instances, `.env` pickup, key redaction.
- **The corpus is on the author's disk and confirmed sound:**
  `data/raw/openstax-us-history.pdf`, **136,400,038 bytes, 987 pages**,
  copyright page reads `©2026 Rice University`, licence CC BY-NC-SA 4.0.

### Broken

Nothing.

### Half-done

Nothing. Every commit is a complete step.

### Not started

`ingest.py`, `retrieve.py`, `prompts.py`, `generate.py`, `citations.py`,
`ask.py`, `tests/`, `app.py`, `eval/`.

### Environment split — important

The author runs **Windows**, in
`C:\Users\minnu\OneDrive\Documents\GitHub\Cliopedia`, with the venv active and
all dependencies installed. **The Claude session runs in a Linux cloud container
that does NOT have the corpus** (`data/raw/` is git-ignored and the container's
network policy blocks openstax.org — see Gotcha 3). The working split is:
**Claude writes and unit-tests code; the author runs anything needing the
corpus, Ollama, or a real model.**

---

## 4. Exact next steps

Work **one step at a time**. Explain before and after. Do not batch.

### Step 4 — `cliopedia/ingest.py` (next)

```
data/raw/*.pdf
  → PyPDFLoader                     from langchain_community.document_loaders
  → RecursiveCharacterTextSplitter  from langchain_text_splitters, 1000/150
  → HuggingFaceEmbeddings           from langchain_huggingface
  → Chroma(persist_directory=...)   from langchain_chroma
```

Read `settings.chroma_dir` and `settings.embedding_model` from
`cliopedia.config`. **Never re-read `os.environ`.** Runnable as
`python -m cliopedia.ingest`. This is the first step that takes real minutes on
the author's machine (987 pages, ~140MB, CPU embedding) — warn them.

**Decision to raise before writing it:** what to do when `data/chroma/` already
exists. Rebuild from scratch, or refuse without a `--force` flag? A stale index
silently merged with new chunks produces duplicate retrievals.

### Step 5 — `cliopedia/retrieve.py` + `tests/test_retrieve.py`

Embed the question with the **same** model used at ingest, cosine search,
return top `settings.retrieval_k` (4) chunks with metadata.

**The author already approved "option D": the retrieval test must build a tiny
Chroma index from a handful of known passages** — not the 987-page textbook — so
tests are fast, deterministic, and runnable in the Linux container and in CI.
This is agreed, not a suggestion.

### Steps 6–8

- `cliopedia/prompts.py` — grounded-answer prompt. Prompts live here, never
  inline in logic files.
- `cliopedia/generate.py` — one OpenAI-compatible client via `llm_settings()`.
- `cliopedia/citations.py` — the `Citation` record, shape fixed in `SPEC.md`
  §6.4: `source_title`, `source_type`, `locator` (a tagged
  `{"kind": "page", "value": 214}`), `snippet`.
- `cliopedia/ask.py` — CLI entrypoint tying it together.

**P0 is done when** a real history question returns a correct answer with a page
number, running locally against Ollama.

---

## 5. Decisions made, and why — do not silently reverse these

### From this session

1. **Corpus licence is CC BY-NC-SA 4.0, not CC BY 4.0.** Confirmed from three
   independent sources. **NC** → the project and its deployed demo stay
   non-commercial. **SA** → `data/chroma/` will contain verbatim passages, so
   the index ships under CC BY-NC-SA 4.0 and **cannot** be covered by the repo's
   MIT `LICENSE`. README documents the two-part split. See `CLAUDE.md` §8 Rule 3.

2. **The `langchain` meta-package is deliberately NOT installed.** In 1.x it is
   `langchain-core` + LangGraph, neither of which this project touches. Imports
   come from `langchain-community`, `langchain-text-splitters`,
   `langchain-chroma`, `langchain-huggingface`. **Any tutorial doing
   `from langchain.text_splitter import ...` is pre-1.x and stale.**
   See §8 Rule 1.

3. **Corpus is the WEB edition PDF, not the print edition.** `DEFAULT_URL` is
   `.../US_History_-_WEB.pdf`. There is also a `USHistory-OP.pdf` at the same
   prefix — **it is broken** (see Gotcha 2). WEB is also correct on the merits:
   less than half the size, and this pipeline only extracts text.

4. **Config is a hybrid, chosen by the author from three options.** Index
   settings default and validate at import; LLM settings are required and read
   **on demand** via `llm_settings()`, so `pytest` and `ingest` import fine
   without an API key.

5. **Exact `==` version pins.** Streamlit Cloud installs from the same file, so
   pins are what make laptop and deploy identical.

### Carried over from Phase 0

6. **LangChain used thinly. No `RetrievalQA` or any prebuilt chain.** The
   retrieve → prompt → generate → cite loop is hand-written so the author can
   explain every step in an interview. **Do not "simplify" this into a chain.**
7. **"Not covered in the source material" is a success case.** Never let the
   model fall back on its own memory.
8. **Source PDFs git-ignored; the Chroma index committed.** The deployed app
   gets no database, so it ships a prebuilt index and only ever reads.
9. **One OpenAI-compatible client for both Ollama and Groq.** Never write
   `if backend == "ollama"`.
10. **Package is `cliopedia/`, never `lib/`** — the seeded `.gitignore` ignores
    `lib/`, so such a folder would be silently untracked.

---

## 6. Gotchas the next session absolutely needs

1. **`SPEC.md` still says CC BY 4.0, in six places.** It is read-only by rule and
   was deliberately left wrong. `CLAUDE.md` §8 Rule 3 is the correction of
   record. **Do not "fix" SPEC.** Do not trust its licence claim.

2. **`USHistory-OP.pdf` is a trap and cost two 324MB downloads.** It returns
   HTTP 200 and downloads happily, but the object is a stale 2016 upload
   (`Last-Modified` 2016-04-29) truncated to 324,153,344 bytes — an exact
   multiple of 4096 — with no `%%EOF` marker anywhere. **An HTTP 200 is not
   verification.** Use `--inspect` on any candidate URL before spending a
   download. See §8 Rule 7.

3. **The Claude container's network policy blocks nearly everything.** The
   gateway answers `403` to `CONNECT` for openstax.org, archive.org,
   huggingface.co, gutenberg.org, github.com, api.github.com. **Reachable:**
   `pypi.org`, `files.pythonhosted.org`, `raw.githubusercontent.com`, npm /
   crates / Go proxies. This is the *environment*, not the sites. The author's
   machine has no such restriction. `curl -sS "$HTTPS_PROXY/__agentproxy/status"`
   shows the live policy and recent rejections.

4. **A tested fallback corpus exists if the PDF route ever dies:** OpenStax
   publishes the whole book as **177 CNXML modules** under
   `raw.githubusercontent.com/openstax/osbooks-us-history/main/modules/<id>/index.cnxml`,
   reachable from the container. **Cost: CNXML has no page numbers**, so
   citations would key on paragraph IDs. `SPEC.md` §6.4's tagged locator already
   supports that shape, but it changes P0's done-criterion. Not needed now.

5. **PDF text extraction wraps mid-sentence.** `page.extract_text()` preserves
   the *visual* line breaks of a printed page, not sentence structure. This bit
   the licence checker twice. **It will bite `ingest.py`:**
   `RecursiveCharacterTextSplitter` prefers line breaks as split points, and
   those "lines" are column-width artifacts, so it can cut mid-sentence while
   believing it found a natural boundary. It will also bite P1, where citation
   snippets are shown verbatim. See §8 Rule 8.

6. **The author is on Windows.** Never hand over a bare `source venv/bin/activate`
   line, and never demote the Windows form to a trailing comment — that already
   cost a round trip. CMD: `venv\Scripts\activate`. PowerShell:
   `.\venv\Scripts\Activate.ps1` (blocked by default execution policy —
   `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`). `cp` → `copy`.
   Forward slashes in Python paths are fine. See §8 Rule 4.

7. **Branching: the harness may force a feature branch.** `CLAUDE.md` §5 now says
   `main` is the trunk and all work lands there; if forced onto a branch, open a
   PR into `main` and merge before the session ends. This session was forced onto
   `claude/handover-continuation-uumnnu`, and the author explicitly authorised
   committing directly to `main` instead.

8. **`origin/claude/handover-continuation-uumnnu` still exists and should be
   deleted.** It is fully contained in `main`. **Claude cannot delete it** — the
   git proxy returns `HTTP 403` on ref deletion, confirmed across five attempts
   with backoff. The author has been asked to delete it from GitHub's UI and has
   not yet confirmed doing so. Do not retry the proxy delete; just remind them.

9. **Never put backticks in a double-quoted `git commit -m` string.** Bash treats
   them as command substitution and silently eats the word. Use
   `git commit -F <file>`, and read the message back with
   `git log -1 --format=%B`. See §8 Rule 5.

10. **Before any history rewrite, create a backup ref.** A chained
    `reset --hard` / `cherry-pick` / `--amend` recovery already went wrong this
    session — `git cherry-pick` has no `-q` flag, `set -e` did not halt the
    script, and the amend landed on the wrong commit. The backup ref made it a
    non-event. Prove content-neutrality with tree hashes, not an empty diff.
    See §8 Rule 6.

11. **Unverified, and flagged to the author:** whether Streamlit Community Cloud
    exposes its secrets as environment variables. `config.py` reads
    `os.environ`. If secrets turn out to be reachable only via `st.secrets`,
    `config.py` needs a small adapter at P3. **Do not assert either way.**

12. **Unverified:** Streamlit Cloud's memory/storage limits, and whether a
    PyTorch install fits. `SPEC.md` §2.2 documents Chroma's ONNX embedder as the
    fallback; switching costs one full index rebuild. Live risk at P3.

13. **Unverified:** Groq's current free-tier model lineup. Deferred to P3. **Do
    not guess a model name.**

14. **Security, every commit:** `git add -A`, inspect `git diff --cached`, then
    commit. `LLM_API_KEY` is the only real secret. The repo is going public.

---

## 7. Open questions for the author

1. `ingest.py` behaviour when `data/chroma/` already exists — rebuild, or refuse
   without `--force`? (Ask before writing step 4.)
2. Has the stale branch been deleted from GitHub yet? (Gotcha 8.)
3. Does OneDrive need excluding for `data/raw/`? The repo lives inside a OneDrive
   folder and the corpus is 136MB of git-ignored, re-fetchable data. Raised once,
   not answered.
