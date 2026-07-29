# HANDOVER.md

**Relay baton. Read this, then DELETE this file, then continue the work.**
A stale handover from two sessions ago poisons the current one. Pick it up,
throw it away, keep running.

**Written:** 2026-07-29 · Phase 0 complete, no application code exists yet.

---

## 1. Read these first, in this order

1. `.claude/soul.md` — who the author is and how to talk to them.
   **Git-ignored**, so it exists only on the author's machine. If it's missing,
   the essentials are: MS AI student at Kent State (graduating May 2026),
   strong in Python/ML/DL/Streamlit, **beginner at RAG/LangChain/embeddings/
   vector stores/Ollama**. Wants those taught **thoroughly**. Direct tone, no
   filler, no cushioning — but blunt ≠ terse, explanations should be generous.
2. `CLAUDE.md` — the working agreement. §7 has the behavioural rules; follow
   them literally.
3. `SPEC.md` — the blueprint. **Read-only now that Phase 0 is agreed.** Changed
   decisions get logged in `CLAUDE.md` §8, not silently rewritten in SPEC.

---

## 2. What this project is

**Cliopedia** — a local, open-source RAG study assistant for history students.
Question → retrieve passages from a document library → open LLM answers using
**only** those passages → answer shown with citations back to the exact page.

It is a **portfolio project**. Audience: a hiring manager reading the repo cold,
and the author defending it in an interview. That governs every tradeoff.

---

## 3. What was accomplished this session

Phase 0 (setup) is **complete**. Four commits on `main`:

| Commit | What |
|---|---|
| `4846aad` | `chore:` git-ignore `.claude/soul.md` |
| `afeabb0` | `docs:` add `SPEC.md` |
| `a95759e` | `docs:` add `CLAUDE.md`, expand `README.md` |
| *(this)* | `docs:` add `HANDOVER.md` |

Also done: read the résumé and both reference PDFs (6-file system, 21
instructions); reviewed the author's `keerthan2102/AutoApply` repo to match
conventions; wrote `.claude/soul.md` (on disk, git-ignored).

---

## 4. Current state

- **Working:** nothing runtime — there is no application code yet, by design.
- **Broken:** nothing.
- **Half-done:** nothing. Phase 0 is a clean stopping point.
- **Working tree:** clean, `main` pushed to origin.

Repo contents: `SPEC.md`, `CLAUDE.md`, `README.md`, `HANDOVER.md`, `LICENSE`,
`.gitignore`, `references/` (3 PDFs), `.claude/soul.md` (untracked).

---

## 5. Exact next steps — start of P0

Work **one step at a time**, explaining before and after each. Do not batch.

1. **`requirements.txt` + `.env.example`** — pin `langchain`, `langchain-community`,
   `langchain-chroma`, `chromadb`, `sentence-transformers`, `pypdf`, `openai`,
   `python-dotenv`, `streamlit`, `pytest`. `.env.example` holds variable *names*
   with placeholders only — see `SPEC.md` §7 for the exact list.
2. **`cliopedia/config.py`** — read every env var here and **nowhere else**.
3. **`scripts/download_sources.py`** — fetch OpenStax *U.S. History* PDF into
   `data/raw/`. **Confirm the CC BY 4.0 licence line on the PDF's copyright
   page** — see the open question in §7 below.
4. **`cliopedia/ingest.py`** — `PyPDFLoader` → `RecursiveCharacterTextSplitter`
   (1000/150) → `HuggingFaceEmbeddings` → `Chroma(persist_directory=...)`.
5. **`cliopedia/retrieve.py`** + `tests/test_retrieve.py` — top `k=4`.
6. **`cliopedia/prompts.py`** + **`cliopedia/generate.py`** — grounded-answer
   prompt, OpenAI-compatible client.
7. **`cliopedia/citations.py`** — the `Citation` record (`SPEC.md` §6.4).
8. **`cliopedia/ask.py`** — CLI entrypoint tying it together.

**P0 is done when** a real history question returns a correct answer with a page
number, running locally against Ollama.

---

## 6. Decisions made, and why (do not silently reverse these)

- **Corpus: OpenStax *U.S. History* (CC BY 4.0), not Project Gutenberg.**
  US public domain = published pre-1929, so any public-domain history book is
  ~century-old scholarship — a correctness problem for a study tool. Gutenberg
  may be added later as *primary sources* (period documents), clearly labelled.
- **LangChain used thinly. No `RetrievalQA` or any prebuilt chain.** The
  retrieve → prompt → generate → cite loop is hand-written so the author can
  explain every step in an interview. **Do not "simplify" this into a chain.**
- **"Not covered in the source material" is a success case.** Never let the
  model fall back on its own memory to fill a gap — that destroys the grounding
  guarantee the project rests on.
- **Embeddings: `all-MiniLM-L6-v2` via `sentence-transformers`.** Chroma's ONNX
  embedder is the documented fallback if Streamlit Cloud hits resource limits at
  P3. Switching costs one full index rebuild.
- **One OpenAI-compatible client for both Ollama and Groq**, selected by env
  vars. **Never write `if backend == "ollama"`.**
- **Source PDFs git-ignored; Chroma index committed.** Queries never open the
  PDFs (snippets live in index metadata), and the deployed app must read a
  prebuilt index with no database to host.
- **Package is `cliopedia/`, never `lib/`** — see gotcha below.
- **Citations are a tagged locator record**, not a bare page number, so
  page-less plain-text sources fit the same shape later without a UI change.
- **Commit directly to `main`.** No feature branches on this project — the
  author's deliberate choice. **Do not set up a `PreToolUse` branch-guard hook.**

---

## 7. Gotchas the next session absolutely needs

- **`lib/` is a trap.** The GitHub-seeded Python `.gitignore` contains `lib/`
  and `lib64/`. A source folder named `lib/` would be **silently untracked** —
  code that looks committed but isn't. The package is `cliopedia/`. Sidestep by
  name; do **not** edit the seeded ignore rule.
- **This repo is going public.** Never commit a secret. `LLM_API_KEY` is the
  only real one, and it lives in a git-ignored `.env` locally / Streamlit Cloud
  secrets in production. Before every commit: `git add -A`, inspect
  `git diff --cached`, then commit.
- **Extend `.gitignore`, never remove seeded entries.**
- **The embedding model is baked into the index.** Changing `EMBEDDING_MODEL`
  requires a full rebuild; a stale index + new model produces confidently wrong
  citations.
- **A stop hook enforces "no untracked files."** It fired once this session when
  a draft was held back for review. Commit completed work rather than parking it
  untracked; drafts can be revised in follow-up commits.
- **Unverified, flagged in `SPEC.md` §3:** openstax.org returned HTTP 403
  through this environment's proxy, so the CC BY 4.0 licence, ISBN
  978-1-938168-36-9, and April 2026 revision date came from search summaries and
  third-party listings — **not** from OpenStax directly. **Confirm on the PDF's
  own copyright page during step 5.3.** Attribution is a licence obligation.
- **Unverified:** Streamlit Community Cloud's current memory/storage limits, and
  whether a PyTorch install fits inside them. Live risk for P3 (`SPEC.md` §2.2).
- **Unverified:** Groq's current free-tier model lineup. Deferred to P3; do not
  guess a model name.
- **A stale branch `claude/cliopedia-portfolio-setup-x2hnt0` still exists on
  origin.** Identical to `main` at the point it was abandoned. The author was
  told it should be deleted during the pre-public cleanup pass but has **not**
  approved that yet. Do not delete without asking.

---

## 8. Open questions for the author

1. Confirm the OpenStax licence/edition details against the downloaded PDF.
2. Delete the stale `claude/cliopedia-portfolio-setup-x2hnt0` branch on origin?
3. `MEMORY.md` has not been seeded yet — let it accumulate, or seed it?
