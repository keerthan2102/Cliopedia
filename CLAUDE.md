# CLAUDE.md — Cliopedia working agreement

Project memory for Claude Code sessions on this repo. Read at session start,
alongside `.claude/soul.md` (git-ignored, personal).

- The blueprint (what we're building and why) → [`SPEC.md`](SPEC.md)
- Setup and run instructions → [`README.md`](README.md)

---

## 1. Project overview

**Cliopedia** is a local, open-source **RAG** (Retrieval-Augmented Generation)
study assistant for history students. A student asks a history question; the app
retrieves the most relevant passages from its document library; an open language
model writes an answer grounded **only** in those passages, with citations back
to the exact page.

**The citation is the product**, not a feature bolted on top. An answer that
can't be traced to a source has failed, even if it happens to be correct.

This is a **portfolio project**. Its audience is a hiring manager reading the
repo cold, and the author defending it in an interview. That governs every
tradeoff: clarity over cleverness, explainability over brevity.

**Status: Phase 0 (planning) complete. No application code exists yet.**

---

## 2. Tech stack — locked

Do **not** substitute any of these. If one looks like the wrong tool, say so —
then use it anyway unless told otherwise in the current message.

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Env / deps | `venv` + `pip` + `requirements.txt` |
| RAG framework | LangChain — **thin usage only**, see §4.1 |
| Vector store | ChromaDB, persisted to `data/chroma/` |
| Embeddings | `all-MiniLM-L6-v2` (384-dim) via `sentence-transformers` |
| LLM (dev) | Ollama, `llama3.1:8b`, local |
| LLM (deploy) | Groq free tier, OpenAI-compatible |
| UI | Streamlit → Streamlit Community Cloud |
| PDF loading | `pypdf` via LangChain's `PyPDFLoader` |
| Tests | `pytest` |
| Corpus | OpenStax *U.S. History*, CC BY-NC-SA 4.0 (see §8 Rule 3) |

---

## 3. Commands

> Not yet implemented — these are the target commands defined in `SPEC.md`.
> Update this section as each lands, and never document a command that doesn't
> run.

```bash
# Setup — activation is the one platform-specific line.
# The author develops on Windows; do not hand them a bare `source` line.
python -m venv venv
venv\Scripts\activate              # Windows CMD
.\venv\Scripts\Activate.ps1        # Windows PowerShell
source venv/bin/activate           # macOS / Linux
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env

# Local model (dev)
ollama pull llama3.1:8b
ollama serve

# Fetch the corpus into data/raw/  (git-ignored)
# Verifies the %PDF- header AND the %%EOF marker, then prints page count
# and the licence line off the PDF itself — read it.
python scripts/download_sources.py
python scripts/download_sources.py --force        # refetch over an existing file

# Check a candidate URL WITHOUT downloading it (see §8 Rule 7).
# One HEAD plus a 128 KiB range request; costs seconds, not megabytes.
python scripts/download_sources.py --url <pdf-url> --inspect

# Build the Chroma index  (run after any corpus or embedding-model change)
python -m cliopedia.ingest

# Ask a question from the terminal (P0)
python -m cliopedia.ask "What caused the Louisiana Purchase?"

# Run the UI (P1)
streamlit run app.py

# Tests
pytest
```

---

## 4. Architecture

```
question
  → retrieve.py    embed question, cosine search Chroma, top k=4 chunks
  → prompts.py     build one prompt: passages + question + grounding rules
  → generate.py    OpenAI-compatible call (Ollama locally / Groq deployed)
  → citations.py   attach Citation records to the answer
  → answer + sources
```

Offline, run separately and **never at query time**:

```
data/raw/*.pdf
  → PyPDFLoader                      one Document per page, carries page number
  → RecursiveCharacterTextSplitter   chunk_size=1000, chunk_overlap=150
  → HuggingFaceEmbeddings            each chunk → 384-number vector
  → Chroma(persist_directory="data/chroma")
```

Folder layout, component specs, and the UI wireframe are in `SPEC.md` §4–6.

### 4.1 LangChain is used thinly — this is deliberate

Use LangChain for **document loaders, text splitters, and the Chroma wrapper**.

Do **not** use `RetrievalQA` or any other prebuilt chain. The retrieve → build
prompt → call model → attach citations loop is written explicitly in this
repo's own code.

Reason: the prebuilt chain hides chunking, retrieval, prompt construction, and
answer parsing — the four things the author must be able to explain in an
interview. Costs ~40 extra lines; buys an explainable pipeline. **Do not
"simplify" this into a chain.**

### 4.2 One LLM client, no backend branching

Ollama and Groq are both OpenAI-compatible. There is **one** client, configured
by environment variables. Never write `if backend == "ollama"`. Switching from
local to deployed is a config change only.

### 4.3 Embedding model must match between ingest and query

Vectors from different models are not comparable. `EMBEDDING_MODEL` is read in
`config.py` and used by both `ingest.py` and `retrieve.py`. Changing it requires
a **full index rebuild** — a stale index with a new model produces confidently
wrong citations.

### 4.4 Refusing to answer is a success case

With a single-textbook corpus, many reasonable history questions have no answer
here. The correct behaviour is to say **"this isn't covered in the source
material."** Never let the model fall back on its own memory to fill the gap —
that silently destroys the grounding guarantee the whole project rests on.

---

## 5. Conventions

- **Commits:** Conventional Commits — `feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`.
- **Branching: `main` is the trunk, and all work lands there.** Commit directly
  to `main` and push after each completed and explained step. **No feature
  branches by choice — deliberate, not an oversight.** Do not set up a
  `PreToolUse` branch-guard hook.
  - **When a harness forces work onto a branch** (some Claude Code environments
    mandate one and refuse pushes to `main`), that is not a reason to abandon
    the rule. Open a **pull request into `main` and merge it** before the
    session ends. Work must never be left stranded on a branch — a branch
    nobody merges is work nobody has.
  - Never leave a stale branch behind on `origin` after its PR merges.
- **Package name is `cliopedia/`, never `lib/`.** The seeded Python
  `.gitignore` contains `lib/` and `lib64/`; a source folder named `lib/` would
  be **silently untracked**. Sidestep by name; do not edit the ignore rule.
- **Config in one place.** Every environment variable is read in `config.py`
  and nowhere else.
- **Prompts live in `prompts.py`**, not inline in logic files.
- **Docstrings explain *why*, not *what*.** The reader is learning RAG.
- **The index is a committed build artifact.** Rebuild and commit it whenever
  the corpus or embedding model changes.
- **`SPEC.md` is read-only once code starts.** Changed decisions get logged in
  §8 here, not silently rewritten there.

---

## 6. Security rules — non-negotiable

**This repo is going public.** History is permanent; a leaked key means
rewriting history *and* rotating the credential.

- **Never commit API keys, tokens, or any secret.** Ever.
- `LLM_API_KEY` is the only real secret. It lives in a git-ignored `.env`
  locally and in **Streamlit Cloud secrets** in production. Never in code,
  never in `.env.example`, never in a commit, never in a screenshot.
- `.env.example` is committed and documents variable *names* with placeholder
  values only.
- **Before every commit:** `git add -A`, then inspect `git diff --cached`, then
  commit. Confirm nothing sensitive is staged.
- **Extend `.gitignore`, never remove seeded entries.**
- `.claude/soul.md` is git-ignored — it contains personal data. The rest of
  `.claude/` is tracked on purpose.
- Attribution to OpenStax (**CC BY-NC-SA 4.0** — see §8 Rule 3) in README and UI
  is a **licence obligation**, not a courtesy. A *wrong* attribution is a
  violation, not a typo. The OpenStax name, logo, and cover art are not covered
  by the licence and must not be reproduced.
- **ShareAlike travels with the passages.** `data/chroma/` embeds verbatim
  textbook text, so it ships under CC BY-NC-SA 4.0, not under the repo's MIT
  `LICENSE`. Never relicense the index. Never make the deployed demo commercial.

---

## 7. Behavioural rules

### Working method

1. **One step at a time.** Never batch multiple steps into one turn.
2. **Explain before building.** Before each step, say in plain, beginner-level
   language *what* we're doing and *why* it matters. Define jargon on first use.
3. **Explain after building.** Walk through new code line group by line group.
   Thorough explanation is the deliverable here, not padding.
4. **Show 2–3 options with honest tradeoffs** for any real decision, and wait
   for a choice. Do not pick silently.
5. **Ask, don't assume.** If anything is unclear, ask before writing a line of
   code. Never code on a guess.
6. **Simplest thing that works, first.** No abstractions that weren't requested.
7. **Never touch unrelated code.** Only files and lines belonging to the current
   step. Notice something else worth fixing? Mention it. Do not touch it.
8. **Flag uncertainty explicitly, before relying on it.** "I'm not certain about
   this" beats a confident guess. Never fill a gap with plausible-sounding
   detail — no invented API signatures, benchmark numbers, dates, or quotes.
9. **Confirm before anything destructive.** Before deleting or overwriting a
   file, list exactly what is affected and wait for a yes *in the current
   message*.
10. **End every step with a status line:** what changed, what was left untouched,
    what's next.

### Tone

- **No filler.** Never open with "Great question!", "Certainly!", "Absolutely!".
  Lead with the answer.
- **Direct, no cushioning.** "That won't work because X" — no diplomatic wrapper.
- **Blunt ≠ terse.** Direct in tone, generous in explanation. Not in conflict.
- **Match length to need.** No recaps that repeat what was just done.

### Calibration

Strong in and needs no re-teaching: Python, pandas/numpy, classical ML and deep
learning, model training/evaluation, Streamlit, data visualisation.

Beginner at, and wants taught thoroughly: RAG architecture, LangChain,
embeddings, vector stores, chunking strategy, prompt design, retrieval
evaluation, running local models with Ollama.

---

## 8. Learned Rules

Every correction becomes a permanent rule here, so no mistake happens twice.

<!--
Format:
### Rule N: <short title>
- **Trigger**: what Claude did wrong
- **Correct behavior**: what it should do instead
- **Date**: YYYY-MM-DD
-->

### Rule 1: LangChain 1.x is several packages, and `langchain` isn't one of ours

- **Trigger**: §2 above and `SPEC.md` name "LangChain" as if it were one
  dependency. As of 1.x it is not, and the planned dependency list was wrong —
  it omitted `langchain-huggingface` entirely, so `HuggingFaceEmbeddings` would
  have failed to import at ingest time.
- **Correct behavior**: install only the packages we import from —

  | Import | Package |
  |---|---|
  | `PyPDFLoader` | `langchain-community` |
  | `RecursiveCharacterTextSplitter` | `langchain-text-splitters` |
  | `Chroma` | `langchain-chroma` |
  | `HuggingFaceEmbeddings` | `langchain-huggingface` |

  The `langchain` meta-package is **deliberately not installed**: in 1.x it is
  `langchain-core` plus LangGraph, neither of which the thin usage in §4.1
  touches, and both are weight on a deploy target whose limits are unverified
  (`SPEC.md` §2.2). Corollary: any tutorial doing
  `from langchain.text_splitter import ...` is pre-1.x and stale — the import
  path moved.
- **Date**: 2026-07-29

### Rule 2: verify a pin set resolves before committing it

- **Trigger**: `requirements.txt` uses exact `==` pins, and a pinned set that
  cannot co-install fails on Streamlit Cloud rather than on the laptop — far
  from the commit that caused it.
- **Correct behavior**: run `pip install --dry-run -r requirements.txt` and
  confirm it exits 0 before committing any change to `requirements.txt`.
- **Date**: 2026-07-29

### Rule 3: never state a licence you have not read from the source

- **Trigger**: `SPEC.md` §3, README, and §6 above all asserted OpenStax
  *U.S. History* is **CC BY 4.0**. It is not. It is **CC BY-NC-SA 4.0**. The
  claim came from search summaries and third-party listings — "OpenStax is
  CC BY 4.0" is true of *many* OpenStax books but not this one, and the
  generalisation was repeated as fact across three files. Attribution is a
  licence obligation, so a wrong attribution is a licence violation, not a typo.
- **Correct behavior**: read the licence from a source the rights-holder
  controls before writing it anywhere. Confirmed here from OpenStax's own
  repository, `openstax/osbooks-us-history`, in two independent places:

  - `collections/us-history.collection.xml` →
    `<md:license url="http://creativecommons.org/licenses/by-nc-sa/4.0/">`
    (collection `col11740`, uuid `a7ba2fb8-8925-4987-b182-5f4429d48daa`)
  - the repository's own `LICENSE` file and `README.md`

  Consequences that follow, and must not be quietly dropped: **NC** means the
  project stays non-commercial — no ads, no paid tier on the deployed demo.
  **SA** means the committed index in `data/chroma/`, which carries verbatim
  passages, is redistributed under CC BY-NC-SA 4.0 and **cannot** be covered by
  this repo's MIT `LICENSE`. README documents the split. `SPEC.md` is read-only
  and still says CC BY 4.0; this rule is the correction of record.
- **Date**: 2026-07-29

### Rule 4: the author develops on Windows — never hand over a bare `source` line

- **Trigger**: setup instructions were given as a Unix block with the Windows
  variant demoted to a trailing comment —
  `source venv/bin/activate  # Windows: venv\Scripts\activate`. That reads as
  one command with an aside, not as two alternatives, and `source` does not
  exist in Command Prompt at all. The author had to stop and ask.
- **Correct behavior**: when a command differs by platform, give the Windows
  form as a **first-class, separately labelled block**, not a comment. Applies
  to venv activation (`venv\Scripts\activate` for CMD,
  `.\venv\Scripts\Activate.ps1` for PowerShell) and to `cp` → `copy`. Path
  separators need no special handling: Python normalises `scripts/x.py` fine on
  Windows. Worth volunteering unprompted: PowerShell blocks `Activate.ps1` under
  the default execution policy, and a bare `python` can resolve to the Microsoft
  Store stub — `py -3.11` is the more reliable launcher there.
- **Date**: 2026-07-29

### Rule 5: never put backticks in a double-quoted `git commit -m` string

- **Trigger**: a commit body written as `-m "... `source` does not exist ..."`
  lost the word entirely. Backticks inside double quotes are command
  substitution in bash, so the shell ran `source` and pasted its (empty) output
  into the message. The commit looked fine until it was read back.
- **Correct behavior**: write commit bodies without backticks, or pass them via
  `git commit -F <file>` / a quoted heredoc. Markdown formatting in a commit
  message buys nothing — Git renders it as plain text. Always read the message
  back with `git log -1 --format=%B` after committing.
- **Date**: 2026-07-29

### Rule 6: a history rewrite starts with a backup ref and checks every step

- **Trigger**: rewriting a pushed commit message, the chained recovery used
  `git cherry-pick <sha> -q`. There is no `-q` on cherry-pick, so both picks
  failed with a usage error — and `set -e` did not stop the script, so the
  following `git commit --amend` landed on the *wrong* commit and silently
  discarded two commits' worth of work from `HEAD`.
- **Correct behavior**: before any `reset --hard` / `cherry-pick` / rebase
  sequence, create a backup ref (`git branch backup-before-x`). Check each
  command's exit status explicitly rather than trusting `set -e` through a
  pipeline. Prove the rewrite is content-neutral by comparing tree hashes
  (`git rev-parse backup^{tree}` vs `HEAD^{tree}`) — an empty `git diff` is
  weaker evidence than identical tree hashes. Only then force-push, and use
  `--force-with-lease`, never bare `--force`.
- **Date**: 2026-07-29

### Rule 7: HTTP 200 is not verification — check the artifact's structure

- **Trigger**: `DEFAULT_URL` in `scripts/download_sources.py` was a guess at
  OpenStax's asset naming. It returned HTTP 200 and downloaded 324 MB, so it was
  marked "verified working". It was not: the object was a stale 2016 upload
  (`Last-Modified` 2016-04-29, S3 multipart ETag ending `-5`), truncated to
  324,153,344 bytes — an exact multiple of 4096 — with no `%%EOF` marker. It
  cost two full downloads and a wrong-headed truncation diagnosis to find.
- **Correct behavior**: a fetch is verified when the *artifact* is checked, not
  when the request succeeds. For a PDF that means the `%PDF-` header **and** a
  `%%EOF` marker in the tail; `download_sources.py` now enforces both before the
  file is kept. Check a candidate URL with `--inspect` — one HEAD plus a 128 KiB
  range request — before spending a full download on it. Two signals worth
  reading: a size that is an exact multiple of 4096 is almost never a real
  document's length, and `Last-Modified` catches a stale asset instantly.
  Prefer OpenStax's `_-_WEB.pdf` over `-OP.pdf`: this pipeline only extracts
  text, so print-resolution imagery is pure cost.
- **Date**: 2026-07-29
