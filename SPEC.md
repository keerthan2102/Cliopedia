# Cliopedia — SPEC.md

The **blueprint**: a structured decision record of what Cliopedia is and how it
gets built. Written before any application code.

Once building starts this file is **read-only** — a snapshot of intent, not a
living document. Decisions that change later get logged in `CLAUDE.md`; they do
not silently rewrite history here.

- Run/setup instructions → [`README.md`](README.md)
- Working rules, conventions, learned rules → [`CLAUDE.md`](CLAUDE.md)

---

## 1. Overview

**Cliopedia** is a local, open-source **RAG** (Retrieval-Augmented Generation)
study assistant for history students.

A student asks a history question. The app finds the passages in its document
library that are most relevant to that question, hands those passages to an open
language model, and the model writes an answer **using only those passages** —
showing citations back to the exact page it used.

### Why RAG at all

A language model on its own answers from memory. It will produce a confident,
fluent, and sometimes entirely invented answer, and the student has no way to
check it. That failure mode is called **hallucination**, and it is disqualifying
for a study tool.

RAG fixes this by changing the question the model is asked. Instead of:

> "When did the Louisiana Purchase happen?"

the model is asked:

> "Here are three passages from a history textbook. Using only these passages,
> answer: when did the Louisiana Purchase happen?"

The model stops being the source of truth and becomes a **summariser of
retrieved text**. The textbook is the source of truth. And because we know
exactly which passages were handed over, we can show the student the citation
and let them verify it themselves.

**The citation is not a nice-to-have feature. It is the product.**

### Non-goals

- Not a general-purpose chatbot. Off-corpus questions should be refused, not guessed at.
- Not a multi-user or authenticated service. No accounts, no user data stored.
- Not a model-training project. No fine-tuning. Retrieval quality is the work.

---

## 2. Tech stack (with reasoning)

| Layer | Choice | Why this, not the alternative |
|---|---|---|
| Language | **Python 3.11+** | Locked. Every library in this stack is Python-first. |
| Env / deps | **`venv` + `pip` + `requirements.txt`** | Standard library, no extra tooling to learn. Streamlit Community Cloud reads `requirements.txt` natively — one dependency file for laptop and deploy. |
| RAG framework | **LangChain** (thin usage — see §2.1) | Locked, and a real résumé keyword. Used for loaders, splitters, and the Chroma wrapper only. |
| Vector store | **ChromaDB**, persisted to disk | Locked. Runs in-process, no server to install or host. Persists to a plain folder we can commit. |
| Embeddings | **`all-MiniLM-L6-v2`** (384-dim) | ~90MB, CPU-only, free forever, no API key. Identical vectors on laptop and on Streamlit Cloud — see §2.2 for the runtime decision. |
| LLM (dev) | **Ollama**, `llama3.1:8b` | Locked. Free, fully local, fits 16GB RAM + 6GB GPU. |
| LLM (deploy) | **Groq** free tier, OpenAI-compatible | Locked. Ollama also exposes an OpenAI-compatible endpoint, so both are reached through one client (§2.3). |
| UI | **Streamlit** | Locked, and consistent with two of your existing projects. Free hosting on Community Cloud. |
| PDF loading | **`pypdf`** via LangChain's `PyPDFLoader` | Gives a real `page` number per document — which our citation format requires. |
| Documents | **OpenStax U.S. History** (CC BY 4.0) | See §3. |
| Tests | **`pytest`**, added at P0 for the retrieval layer only | Retrieval is the part that silently degrades. Everything else is visible on screen. |

### 2.1 Pushback: use LangChain, but keep it thin

LangChain has a prebuilt `RetrievalQA` chain that does this whole project in
about five lines. **We are not going to use it**, for two reasons.

1. **You would learn nothing.** The five lines hide chunking, retrieval, prompt
   construction, and answer parsing — the exact four things an interviewer will
   ask you to explain.
2. **It breaks.** LangChain's high-level APIs churn fast enough that tutorials
   go stale within months.

So: use LangChain for the boring, stable parts — document loaders, text
splitters, the Chroma wrapper — and write the **retrieve → build prompt →
call model → attach citations** loop explicitly, in our own code.

Roughly 40 extra lines. In exchange you can explain every step of your own
pipeline. That is the entire point of this project.

### 2.2 Open decision: how we *run* the embedding model

The model is settled (`all-MiniLM-L6-v2`). **How we run it is not**, and it
must be settled before P0 builds the index — the embedding model is baked into
the vectors, so changing it later means a full rebuild.

| Option | Install size | Risk |
|---|---|---|
| **A. `sentence-transformers`** | Pulls PyTorch, several hundred MB | The standard, best-documented path. Risk: may strain Streamlit Community Cloud's free-tier resources. |
| **B. Chroma's built-in ONNX embedder** | ~90MB, no PyTorch | Same underlying model, exported to ONNX. Much lighter deploy. Risk: less common in tutorials, so you're on a quieter path. |

**Decided: option A**, because it's the best-documented path while you're
learning. B is the documented fallback if deployment hits resource limits at P3.

> **Uncertainty, stated plainly:** I have *not* verified current Streamlit
> Community Cloud memory/storage limits, and I have *not* benchmarked whether a
> PyTorch install fits inside them. Do not treat "A will deploy fine" as
> established. This gets tested for real at P3, and switching to B costs one
> index rebuild.

### 2.3 The swappable LLM layer

Both Ollama and Groq speak the **OpenAI-compatible chat-completions API**. So
there is exactly one client in the codebase, and the backend is chosen by
environment variables:

| | Development | Deployment |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | `llama3.1:8b` | a Groq-hosted open model |
| `LLM_API_KEY` | `ollama` (ignored placeholder) | real key, from env or Streamlit secrets |

**No `if backend == "ollama"` branching anywhere.** Switching is a config
change, exactly as specified.

> **Uncertainty:** Groq's free-tier model list and rate limits change. The exact
> deploy model gets confirmed at P3, not guessed at now.

---

## 3. Data sources

**Primary corpus: OpenStax *U.S. History*** — ISBN 978-1-938168-36-9,
licensed **CC BY 4.0**, last updated April 2026.

Why this and not Project Gutenberg:

US public domain means **published before 1929**. Any history book old enough to
be public domain carries roughly century-old scholarship. Project Gutenberg
states this about its own collection — it does not avoid topics "for which
societal views, or state-of-the-art knowledge, is vastly different from
contemporary literature."

For a study assistant students are meant to trust, that is a **correctness**
problem. OpenStax is openly licensed rather than public domain, which is
strictly better here: current, peer-reviewed, actively maintained, and CC BY 4.0
explicitly permits redistribution with attribution.

**Attribution obligation (CC BY 4.0):** the README and the app UI must credit
OpenStax and link the source. The OpenStax name, logo, and cover art are *not*
covered by the licence and must not be reproduced.

**Primary sources, later (P2+):** Project Gutenberg texts get added not as
factual authorities but as **period documents** students analyse critically. A
Lincoln speech being "of its time" is the point. Each document is labelled
`secondary` or `primary` in its metadata so the UI can distinguish them.

> **Verify on download:** licence and revision date above come from search
> summaries and third-party listings; openstax.org returned HTTP 403 through
> this environment's proxy. Confirm the licence line on the PDF's own copyright
> page.

---

## 4. Folder structure

```
Cliopedia/
├── .claude/
│   ├── soul.md                 # git-ignored — personal, contains PII
│   └── settings.json           # hooks config (P1+)
├── app.py                      # Streamlit entrypoint (P1)
├── cliopedia/                  # the package — NOT "lib/", see note below
│   ├── __init__.py
│   ├── config.py               # env vars → settings, one place only
│   ├── ingest.py               # load → chunk → embed → persist to Chroma
│   ├── retrieve.py             # question → ranked chunks + metadata
│   ├── generate.py             # chunks + question → grounded answer
│   ├── citations.py            # the Citation record (§6.4)
│   └── prompts.py              # prompt templates, kept out of logic files
├── data/
│   ├── raw/                    # source PDFs — GIT-IGNORED (§4.1)
│   └── chroma/                 # the persisted index — COMMITTED (§4.1)
├── scripts/
│   └── download_sources.py     # fetches the corpus into data/raw/
├── tests/
│   └── test_retrieve.py
├── eval/                       # P3 — question/answer set + scoring
├── .env.example                # documents required vars, holds NO secrets
├── .gitignore
├── requirements.txt
├── CLAUDE.md
├── SPEC.md
└── README.md
```

**Why `cliopedia/` and not `lib/`:** the GitHub-seeded Python `.gitignore` in
this repo contains `lib/` and `lib64/` (intended for virtualenv internals). A
source folder named `lib/` would be **silently untracked by Git** — code that
looks committed but isn't. We sidestep it by name rather than by editing the
ignore rule.

### 4.1 Why raw PDFs are ignored but the index is committed

This looks backwards — committing a build artifact while ignoring its source —
so here's the reasoning.

The index is committed **because the deployment plan requires it**. Streamlit
Community Cloud gives us no database. Shipping a prebuilt Chroma folder means
the deployed app only ever *reads* — no ingest at startup, no database to host,
no cost. That was a locked requirement.

The raw PDFs are ignored **because nothing at query time needs them**. Citations
carry the quoted snippet in the index metadata, so the original file is never
opened during a query. Committing a large PDF would bloat the repo permanently —
Git history keeps every version forever — to no benefit.

`scripts/download_sources.py` makes this reproducible: anyone can refetch the
corpus and rebuild the index from scratch. The index is committed for
*convenience*, not because it's unreproducible.

---

## 5. Screen design (P1)

Single page. No navigation, no sidebar tabs — one job done clearly.

```
┌──────────────────────────────────────────────────────────────┐
│  📚 Cliopedia                                                │
│  Ask a history question — every answer cites its source.     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────┐  ┌────────┐  │
│  │ What caused the Louisiana Purchase?        │  │  Ask   │  │
│  └────────────────────────────────────────────┘  └────────┘  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ANSWER                                                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Jefferson pursued the purchase after Napoleon, facing  │  │
│  │ war with Britain and the loss of Saint-Domingue,       │  │
│  │ offered the whole territory rather than New Orleans    │  │
│  │ alone. [1] The sale doubled the size of the United     │  │
│  │ States for roughly $15 million. [2]                    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  SOURCES                                                     │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ▸ [1] OpenStax U.S. History — p. 214                    │  │
│  │ ▾ [2] OpenStax U.S. History — p. 215                    │  │
│  │      "The Louisiana Purchase of 1803 nearly doubled    │  │
│  │       the land area of the young nation…"              │  │
│  │       ── retrieved passage, verbatim ──                │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  Sources: OpenStax U.S. History (CC BY 4.0). Answers are     │
│  generated from retrieved passages and may contain errors.   │
└──────────────────────────────────────────────────────────────┘
```

Design notes:

- **`[1]`, `[2]` markers link answer text to a specific source card.** A
  citation the student can't trace to a sentence isn't a citation.
- **Snippets are collapsed by default, expandable.** The verbatim retrieved
  passage is what lets a student check the model didn't drift from the source.
- **The disclaimer is permanent, not dismissible.** Honest about what a
  generated answer is.

---

## 6. Core components

### 6.1 `ingest.py` — build the index (run offline, not at query time)

```
data/raw/*.pdf
  → PyPDFLoader            one Document per page, carrying page number
  → RecursiveCharacterTextSplitter   chunk_size=1000, chunk_overlap=150
  → HuggingFaceEmbeddings  each chunk → a 384-number vector
  → Chroma(persist_directory="data/chroma")
```

**Why chunk at all:** a whole book won't fit in a model's context window, and
searching by meaning works better on focused passages. Ask about the Louisiana
Purchase and you want *the paragraph*, not the chapter.

**Why 1000 characters:** roughly a paragraph or two — one coherent idea, small
enough that several fit in a prompt together.

**Why 150 characters of overlap:** chunk boundaries are arbitrary and will cut
mid-sentence. Overlap means a fact split across a boundary still appears whole
in one of the two neighbouring chunks.

**Why "Recursive":** it tries to split on paragraph breaks first, then line
breaks, then sentences, then words — preferring natural boundaries over
chopping at exactly 1000 characters.

> These numbers are **starting defaults, not tuned values.** P3's evaluation
> harness exists precisely to test them.

### 6.2 `retrieve.py` — question → relevant chunks

Embeds the question with the *same* model used at ingest (non-negotiable —
vectors from different models are not comparable), then returns the `k` nearest
chunks by cosine similarity. **`k = 4` to start.**

### 6.3 `generate.py` — chunks → grounded answer

Builds one prompt containing the retrieved passages and the question, with
instructions to answer **only** from the passages and to say so when the
passages don't contain the answer. Sends it through the OpenAI-compatible
client (§2.3).

**Refusing to answer is a success case, not a bug.** A study tool that says
"this isn't covered in the source material" is more useful than one that
invents a plausible date.

### 6.4 `citations.py` — the citation record

Settled now (per your call) so the shape never has to be retrofitted:

```
Citation:
  source_title   "OpenStax U.S. History"
  source_type    "secondary" | "primary"
  locator        {"kind": "page",      "value": 214}      # PDFs
                 {"kind": "paragraph", "value": 37}       # plain text, P2+
  snippet        the verbatim retrieved passage
```

`locator` is a small tagged record rather than a bare page number so plain-text
primary sources (which have no pages) fit the same structure later without
changing the UI or the index schema.

### 6.5 `config.py` — one place for settings

Every environment variable is read **here and nowhere else**, so there is
exactly one file to check when deployment behaves differently from local.

---

## 7. Environment variables

Declared in `.env.example` (committed, no real values). Real values live in a
git-ignored `.env` locally and in Streamlit Cloud's secrets manager in
production.

| Variable | Dev value | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Which OpenAI-compatible endpoint |
| `LLM_MODEL` | `llama3.1:8b` | Which model on that endpoint |
| `LLM_API_KEY` | `ollama` | Placeholder locally; **real secret in production** |
| `CHROMA_DIR` | `data/chroma` | Where the index lives |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Must match between ingest and query |
| `RETRIEVAL_K` | `4` | How many chunks to retrieve |

**`LLM_API_KEY` is the only real secret in this project.** It never appears in
code, in `.env.example`, in a commit, or in a screenshot.

---

## 8. Deployment plan (P3)

1. Index is already committed, so the deployed app performs **no ingest**.
2. Push to GitHub; point Streamlit Community Cloud at `app.py`.
3. Set `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` in Streamlit **secrets** —
   never in the repo.
4. Same code, different config. No branch, no fork, no rewrite.

---

## 9. Phases and priorities

### P0 — end-to-end RAG, simplest possible form
No UI. A script that answers a question in the terminal, with sources.

- [ ] `requirements.txt`, `.env.example`, venv setup
- [ ] `scripts/download_sources.py` — fetch OpenStax U.S. History
- [ ] `config.py`
- [ ] `ingest.py` — load → chunk → embed → persist
- [ ] `retrieve.py` + `test_retrieve.py`
- [ ] `generate.py` with the grounded-answer prompt
- [ ] One CLI entrypoint that ties it together
- **Done when:** a real history question returns a correct answer with a page
  number, running locally against Ollama.

### P1 — Streamlit UI with visible citations
- [ ] `app.py` matching the §5 wireframe
- [ ] `[1]`/`[2]` markers linking answer text to source cards
- [ ] Expandable verbatim snippets
- [ ] Permanent attribution + disclaimer
- **Done when:** a stranger can use it without instructions and verify any claim.

### P2 — student features
- [ ] Grade-level explanation control (e.g. middle school / high school / college)
- [ ] Quiz generation from retrieved passages
- [ ] Primary-source documents added, labelled distinctly from the textbook
- **Done when:** it's a study tool, not just a search box.

### P3 — evaluation + public deployment
- [ ] `eval/` — a hand-written question set with known-correct pages
- [ ] Measure **retrieval hit rate**: was the right page in the top `k`?
- [ ] Tune `chunk_size` / `k` against that measurement, not by vibes
- [ ] Switch backend to Groq **by config only** and verify nothing else changed
- [ ] Deploy to Streamlit Community Cloud
- **Done when:** the demo is public and you can state a retrieval number out loud.

**Why evaluation is P3 and not P0:** you need a working pipeline before there's
anything to measure. But it ships before "done" — a RAG project with no
retrieval metric is a demo, not engineering, and that gap is exactly what an
interviewer probes.

---

## 10. Constraints and known limitations

- **Answers are only as good as the corpus.** One textbook means many reasonable
  history questions have no answer here. The app should say so rather than guess.
- **The 8B local model is modest.** Expect occasional clumsy phrasing. Retrieval
  quality matters more than model size for grounded answers — which is the point.
- **Streamlit Cloud free tier is unverified for this workload** (§2.2). Live
  risk, with a documented fallback.
- **The committed index must be rebuilt whenever the corpus or embedding model
  changes.** Stale index + new corpus = confidently wrong citations.
- **No user data is stored.** No accounts, no query logging, no analytics.
- **CC BY 4.0 attribution is a licence obligation**, not a courtesy.

---

## 11. Open decisions

| # | Decision | Status |
|---|---|---|
| 1 | Embedding runtime: `sentence-transformers` vs Chroma ONNX (§2.2) | **Decided: `sentence-transformers`.** ONNX is the P3 fallback |
| 2 | Exact Groq model for deployment | **Deferred to P3** — free-tier lineup changes |
| 3 | Chunk size / overlap / `k` | **Defaults now, tuned with evidence at P3** |
