# Cliopedia

A local, open-source **RAG** (Retrieval-Augmented Generation) study assistant
that answers history questions for students **with cited sources**, built on
Ollama, LangChain, and ChromaDB.

> **Status: Phase 0 — planning complete, no application code yet.**
> The blueprint is in [`SPEC.md`](SPEC.md). This README documents the intended
> system and will be updated as each phase actually ships. Nothing below is
> claimed as working until it is.

---

## The problem

Ask a language model a history question and it answers from memory. Sometimes
it's right. Sometimes it produces a fluent, confident, entirely invented date —
and a student has no way to tell the difference. That failure mode is called
**hallucination**, and it disqualifies a plain chatbot as a study tool.

## The approach

Cliopedia changes the question the model is asked. Instead of:

> *"When did the Louisiana Purchase happen?"*

the model receives:

> *"Here are three passages from a history textbook. Using only these passages,
> answer: when did the Louisiana Purchase happen?"*

The model stops being the source of truth and becomes a **summariser of
retrieved text**. The textbook is the source of truth. And because the app knows
exactly which passages it handed over, it can show the student the page number
and the verbatim passage — so the claim can be checked rather than trusted.

**The citation is the product.** An answer that can't be traced to a source has
failed, even if it happens to be correct.

Two consequences fall out of that:

- **"Not covered in the source material" is a correct answer**, not a bug. The
  model is never allowed to fall back on its own memory to fill a gap.
- **The corpus is chosen for accuracy, not just for being free.** See below.

---

## How it works

```
                   ┌──────────── offline, run once ─────────────┐
                   │  PDF → pages → chunks → embeddings → Chroma │
                   └────────────────────────────────────────────┘
                                        │
   question ──► embed ──► similarity search ──► top 4 passages
                                        │
                                        ▼
                       prompt: passages + question + "use only these"
                                        │
                                        ▼
                        open LLM (Ollama local / Groq hosted)
                                        │
                                        ▼
                         answer + [1][2] citations w/ page + snippet
```

The index is **built once, offline, and committed to this repo**, so the
deployed app only ever reads — no database to run or host.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | — |
| RAG framework | LangChain (loaders, splitters, Chroma wrapper) | Used thinly on purpose — the retrieve/prompt/generate/cite loop is written explicitly, not with a prebuilt chain |
| Vector store | ChromaDB, persisted to disk | Runs in-process; no server to host |
| Embeddings | `all-MiniLM-L6-v2` (384-dim) | ~90MB, CPU-only, free, no API key |
| LLM (dev) | Ollama · `llama3.1:8b` | Fully local and free |
| LLM (deploy) | Groq free tier | OpenAI-compatible, same client |
| UI | Streamlit | Free hosting on Community Cloud |

Ollama and Groq are both OpenAI-compatible, so switching between local
development and public deployment is a **config change, not a rewrite** — one
client, no backend-specific branching.

---

## Source material

**[OpenStax *U.S. History*](https://openstax.org/details/books/us-history)** —
licensed **CC BY 4.0**, peer-reviewed and actively maintained.

Chosen deliberately over Project Gutenberg. US public domain means *published
before 1929*, so any history book old enough to be public domain carries roughly
century-old scholarship — a correctness problem for a tool students are meant to
trust. OpenStax is openly licensed rather than public domain, which is strictly
better here.

Project Gutenberg texts may be added later in a different role: as **primary
sources** (period documents to analyse critically), clearly labelled and
distinguished from the textbook.

> *U.S. History* by OpenStax is licensed under
> [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The OpenStax name,
> logo, and cover art are not covered by that licence.

---

## Getting started

> Not yet runnable. These are the target commands from [`SPEC.md`](SPEC.md) and
> will be verified as each phase ships.

```bash
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # fill in local values; never commit .env

ollama pull llama3.1:8b            # local model for development
ollama serve

python scripts/download_sources.py # fetch the corpus into data/raw/
python -m cliopedia.ingest         # build the Chroma index

python -m cliopedia.ask "What caused the Louisiana Purchase?"
streamlit run app.py               # P1
```

No API key is needed for local development — Ollama runs on your machine.

---

## Roadmap

| Phase | Scope | Done when |
|---|---|---|
| **P0** | End-to-end RAG in the terminal: load → chunk → embed → store → retrieve → answer | A real question returns a correct answer with a page number, locally via Ollama |
| **P1** | Streamlit UI with visible citations and expandable source snippets | A stranger can use it unaided and verify any claim |
| **P2** | Grade-level explanations, quiz generation, primary sources | It's a study tool, not just a search box |
| **P3** | Evaluation harness + public deployment (Streamlit Cloud + Groq) | The demo is public and retrieval hit-rate is a number, not a vibe |

Evaluation is deliberately scheduled **before "done"**: a RAG project with no
retrieval metric is a demo, not engineering.

---

## Project documents

This repo follows a six-file working system:

| File | Role |
|---|---|
| [`SPEC.md`](SPEC.md) | The blueprint — decisions made before any code |
| [`CLAUDE.md`](CLAUDE.md) | Working agreement, conventions, and learned rules |
| `HANDOVER.md` | Relay baton between sessions (ephemeral — read it, then delete it) |
| `.claude/soul.md` | Author background and preferences (git-ignored — personal) |

---

## Licence

Code: see [`LICENSE`](LICENSE).
Source material: OpenStax *U.S. History*, CC BY 4.0, attributed above.
