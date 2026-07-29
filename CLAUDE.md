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
| Corpus | OpenStax *U.S. History*, CC BY 4.0 |

---

## 3. Commands

> Not yet implemented — these are the target commands defined in `SPEC.md`.
> Update this section as each lands, and never document a command that doesn't
> run.

```bash
# Setup
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in local values

# Local model (dev)
ollama pull llama3.1:8b
ollama serve

# Fetch the corpus into data/raw/  (git-ignored)
python scripts/download_sources.py

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
- **Branching:** commit directly to `main` and push after each completed and
  explained step. **No feature branches on this project — deliberate, not an
  oversight.** Do not set up a `PreToolUse` branch-guard hook.
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
- Attribution to OpenStax (CC BY 4.0) in README and UI is a **licence
  obligation**, not a courtesy. The OpenStax name, logo, and cover art are not
  covered by the licence and must not be reproduced.

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

*(empty — rules get added as they're learned)*
