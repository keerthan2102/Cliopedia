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

**Status: P0 proven end to end** — a real question returns a grounded answer
citing printed page numbers, running locally against Ollama `llama3.1:8b`
over **9275 chunks** across all three OpenStax books. **P1 (Streamlit UI) is
built but not yet exercised by a human.** P2 is next.

### Retrieval baseline — three books, measured 2026-08-10

The same 15 hand-verified questions in `eval/questions.txt`, before and after
the corpus grew from one book (3775 chunks) to three (9275 chunks). Every
question is still a U.S. History question; the two World History volumes are
pure distractors here, which is exactly what makes this an interference test.

| k | hit rate (1 book) | hit rate (3 books) | MRR (1 book) | MRR (3 books) |
|---|---|---|---|---|
| 1 | 53.3% | 46.7% | 0.533 | 0.467 |
| 2 | 66.7% | 53.3% | 0.600 | 0.500 |
| 4 | 86.7% | **60.0%** | 0.656 | 0.517 |
| 6 | **100.0%** | 86.7% | 0.680 | 0.568 |
| 8, 9 | 100.0% | 86.7% | 0.680 | 0.568 |
| 10–14 | — | 93.3% | — | 0.574 |
| **15** | — | **100.0%** | — | 0.579 |
| 16 | 100.0% | 100.0% | 0.680 | 0.579 |

**The expansion cost real accuracy, and that is the finding.** At the
configured k=6, hit rate fell 100% → 86.7%. The worst damage is at k=4:
86.7% → 60.0%. MRR fell at every single k, which is the more diagnostic
number — the correct pages did not merely get crowded out, they got
**out-ranked** by world-history passages that do not answer the question.

**`RETRIEVAL_K` stays at 6 — decided 2026-08-10, deliberately.** The old policy
(smallest k retrieving every known-correct page) would now select 15. The
per-question view says not to pay it: **13 of 15 questions have identical ranks
at k=6, 10 and 15.** Going 6→15 costs nine extra passages on every query to fix
two questions, found at ranks 10 and 15 — deep enough to be buried anyway. On a
15-question set where one item is worth 6.7 points, that is tuning to the test.

| | k=6 | k=10 | k=15 |
|---|---|---|---|
| hit rate | 86.7% | 93.3% | 100.0% |
| MRR | 0.568 | 0.574 | 0.579 |
| questions whose rank changed | — | 1 | 2 |

**Where the real waste is: 23% of retrieval slots are duplicate pages.**
Several chunks from one page rank together, and each copy consumes a slot and
prompt space while adding almost nothing.

| k | slots | distinct pages | wasted | effective pages/query |
|---|---|---|---|---|
| 6 | 90 | 69 | 23.3% | **4.6** |
| 10 | 150 | 118 | 21.3% | 7.9 |
| 15 | 225 | 176 | 21.8% | 11.7 |

So k=6 delivers 4.6 pages of evidence, not 6. Page-level deduplication would
give ~6 distinct pages from a depth of about 8 — cheaper than k=15 and aimed at
the actual waste. Not implemented: two chunks from one page can carry different
content, and the citation UI shows a snippet per chunk, so it is a design
decision rather than a tweak.

The diagnosis behind all of this is **ranking, not depth**. For the Glorious
Revolution question the gold page (93–94) sits behind `us-history` 107 and 92 —
retrieval lands *adjacent* to the right passage and ranks its neighbours above
it. Chunking, reranking over a wider candidate set, and hybrid keyword+vector
search all move MRR. Raising k does not.

### Measured and rejected: filtering retrieval by chapter — 2026-08-10

Do not retry this without new evidence. It was proposed to fix a real grounding
failure (a 2008 question answered partly from 1929 passages — see `prompts.py`),
by dropping passages whose chapter differs from the top-ranked passage's.

| variant | hit rate | MRR | passages/query |
|---|---|---|---|
| baseline k=6 | **93.5%** | **0.699** | 6.0 |
| filtered from k=6 | 80.6% | 0.655 | 4.3 |
| filtered from k=18, take 6 | 83.9% | 0.661 | 5.8 |

**It fixes one question and breaks four** — the 1787 constitution, first European
settlements, utopian socialism and Lend-Lease all stop working. Backfilling from
a deeper pool recovers only one of them.

The reason is the whole point: **when rank 1 is in the wrong chapter, anchoring
on it entrenches the error** and deletes the gold page sitting deeper. For
"What was the Lend-Lease Act?" the gold page is in chapter 13 of World History
Volume 2 and rank 1 is not, so the correct passage is thrown away.

Anchoring on the *majority* chapter is worse still, and was rejected before
testing: in the 2008 case the majority is chapter 25 (four passages of six) —
the **wrong** era. Filtering to it would delete both correct passages.

The general lesson: a post-hoc filter cannot be more reliable than the ranking
it trusts. At MRR 0.57 the top result is wrong often enough that anchoring on it
loses more than it saves. **Fix the ranking first**; filtering only becomes safe
once rank 1 is dependable.

### Measured and adopted: cross-encoder reranking — 2026-08-10

Acting on "fix the ranking first". Retrieve a wider candidate pool with the
embedding model, then re-score every candidate against the question with a
cross-encoder and keep the best `RETRIEVAL_K`. Over 31 questions:

| variant | hit rate | MRR |
|---|---|---|
| baseline (no rerank) | 93.5% | 0.699 |
| **rerank top-6 from 20** | **100.0%** | **0.883** |
| rerank top-6 from 30 | 100.0% | 0.882 |
| rerank top-6 from 50 | 100.0% | 0.882 |

**MRR 0.699 → 0.883 is the largest gain recorded in this project**, and depth 20
matches 50, so the cheapest setting wins. Read MRR rather than hit rate here:
100% on 31 questions is a ceiling, and says only "no known question fails".

Why it works where raising k did not: the embedding model encodes question and
passage *separately* and compares vectors, which is what makes searching 9275
chunks cheap and its ordering weak. A cross-encoder reads the pair together —
far more accurate, far too slow for the whole corpus. Cheap search casts the
net, expensive scoring picks the winners. It cannot promote a passage the
search never returned, so `RERANK_DEPTH` still sets recall.

On the 2008 grounding case it moves 2008 passages from 2 of 6 to 4 of 6,
holding ranks 1–3, and surfaces p.890 — a relevant page the embedding search
never returned at any depth the model saw. **Two 1929 passages still remain at
ranks 4–5**, so this improves the odds rather than closing the bug.

**`RERANK` defaults to off, and that is a deployment decision, not a quality
one.** It loads a second model (~80 MB; no new pip dependency, `CrossEncoder`
ships inside `sentence-transformers`) and adds ~450 ms per query — 36 ms → 487 ms
— which is negligible beside LLM generation but real. `SPEC.md` §2.2 records
that Streamlit Community Cloud's memory limits are unverified for even the first
model. Turn it on locally freely; settle the deployed default at P3, when the
limits are actually tested.

Two integers were measured individually per §8 Rule 14, because the doubling
grid put the plateau somewhere in (8, 16] and could not resolve it. The
rule's MRR cross-check predicted the newly-found pages would sit near rank 12;
they came in at 10 and 15.

### Per-book coverage — 30 questions, measured 2026-08-10

Fifteen World History questions were added, so the set now covers every book.
At the configured k=6:

| book | questions | hit rate | MRR |
|---|---|---|---|
| us-history | 15 | 86.7% | 0.568 |
| world-history-1 | 8 | 100.0% | 0.875 |
| world-history-2 | 7 | 100.0% | 0.738 |
| all | 30 | 93.3% | 0.689 |

**The new books are retrievable.** That is what these questions were for, and
it is a real answer: the expansion did not bury two volumes that can never be
reached. Not one World History question missed.

**Do not read the per-book gap as a quality comparison.** The two groups were
written by different people using different methods, which confounds it:

- The World History questions lean on distinctive proper nouns — *Çatalhöyük*,
  *cartaz*, *Songhai*, *Siemens-Martin*, *Lend-Lease* — which embed nearly
  uniquely and are therefore easy to retrieve.
- The U.S. History questions are deliberately in a student's voice, several
  paraphrased away from the textbook's own wording ("Tell me about the Glorious
  Revolution"). That is the harder case, and the more realistic one.
- Pages were also chosen for having clearly distinctive content, which biases
  toward retrievable pages.

So 0.875 versus 0.568 measures **question style at least as much as retrieval
quality**. Compare within a book over time, not across books.

**The "all" row is the least trustworthy number here.** Hit rate rose from
86.7% to 93.3% purely because easier questions were added — the retriever did
not change. Adding items to a benchmark moves its aggregate for reasons that
have nothing to do with the system, so track the per-book rows.

**The World History answer key is human-verified — 2026-08-10.** The entries
were written from `pypdf`-extracted text rather than the rendered page, so five
were spot-checked against the PDFs by the author: printed 61, 178 and 690 in
Volume 1, and 85 and 534 in Volume 2 — both books, spread early to late. Each
passed three checks: the folio typeset on the page matches the `pages:` value,
the quoted sentence is present and intact rather than split across a caption,
and the page genuinely answers the question.

The folio check is the one that mattered most. It confirms the **offset of 10**
on real rendered pages rather than on extracted text, and a wrong offset would
have made every World History citation point at the wrong page. `_folio_offset`
derived 10 automatically; a person has now seen it printed.

Rule 13's lesson is that an unverified answer key is worth nothing, so this is
what makes the World History rows above trustworthy rather than merely
plausible.

**Still a floor, not a triumph.** Thirty-one questions means one item is worth
3.2 points, and the remaining ten World History entries are verified only by the
extraction they were written from.

Re-run `python -m cliopedia.evaluate --sweep` after any change to the corpus,
the chunking, or the embedding model, and update this table.

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
| Reranker (optional) | `cross-encoder/ms-marco-MiniLM-L-6-v2`, **off by default** — see §1 |
| LLM (dev) | Ollama, `llama3.1:8b`, local |
| LLM (deploy) | Groq free tier, OpenAI-compatible |
| UI | Streamlit → Streamlit Community Cloud |
| PDF loading | `pypdf`, read directly (see §8 Rule 9) |
| Tests | `pytest` |
| Corpus | OpenStax *U.S. History*, CC BY-NC-SA 4.0 (see §8 Rule 3) |

**The corpus is declared once, in `cliopedia/corpus.py`** — URL, filename,
citation title and source type per book. `scripts/download_sources.py` and
`ingest.py` both read it, so a book cannot be fetchable but uncitable.
`url = None` means **not yet established**, never a guess; the download script
reports those and says where to get the link.

All three books are registered with verified URLs. World History Volumes 1 and 2
were confirmed **CC BY-NC-SA 4.0** on 2026-08-05 from OpenStax's own
`collections/*.collection.xml`, and their PDFs `--inspect`ed on 2026-08-06
before the links were written down — both structurally complete, both
`Last-Modified 2026-04-21`, the same batch as *U.S. History*.

---

## 3. Commands

> Every command below runs. Update this section as each new one lands, and
> never document a command that doesn't.

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
# Fetches every book in the registry whose URL is known, and names the ones
# still waiting for a URL. Verifies the %PDF- header AND the %%EOF marker,
# then prints page count and the licence line off the PDF itself — read it.
python scripts/download_sources.py
python scripts/download_sources.py --force              # refetch existing files
python scripts/download_sources.py --book us-history    # just one book

# Check a candidate URL WITHOUT downloading it (see §8 Rule 7).
# One HEAD plus a 128 KiB range request; costs seconds, not megabytes.
# Do this before adding any URL to the registry.
python scripts/download_sources.py --url <pdf-url> --inspect

# Show the resolved configuration (API key redacted).
# First thing to run when a deployment behaves differently from local.
python -m cliopedia.config

# Build the Chroma index  (run after any corpus or embedding-model change)
python -m cliopedia.ingest

# Inspect retrieval on its own — no model needed, useful for debugging
python -m cliopedia.retrieve "What caused the Louisiana Purchase?"

# Same, with the cross-encoder reranker on for one command (Windows: set RERANK=on)
RERANK=on python -m cliopedia.retrieve "What caused the Louisiana Purchase?"

# Measure retrieval against eval/questions.txt (P3)
python -m cliopedia.evaluate
python -m cliopedia.evaluate --sweep        # hit rate at k = 1,2,4,6,8,16
python -m cliopedia.evaluate -k 5           # one specific k

# Ask a question from the terminal (P0)
python -m cliopedia.ask "What caused the Louisiana Purchase?"
python -m cliopedia.ask "..." --snippets    # show the verbatim passages

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
  → load_pages() (pypdf)             one Document per page, carries page number
  → RecursiveCharacterTextSplitter   chunk_size=1000, chunk_overlap=150
  → HuggingFaceEmbeddings            each chunk → 384-number vector
  → Chroma(persist_directory="data/chroma")
```

Folder layout, component specs, and the UI wireframe are in `SPEC.md` §4–6.

### 4.1 LangChain is used thinly — this is deliberate

Use LangChain for **text splitters, the embeddings wrapper, and the Chroma
wrapper**. Document loading is our own code — see §8 Rule 9.

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

### Rule 8: PDF text wraps — normalise whitespace before matching anything

- **Trigger**: the licence check in `download_sources.py` matched line by line.
  OpenStax's copyright page breaks the sentence immediately after "licensed
  under a Creative Commons", so the check printed a half sentence and warned of
  a licence mismatch against words that had merely moved to the next line. The
  document was correct; the matcher was not.
- **Correct behavior**: `page.extract_text()` preserves the *visual* line breaks
  of a printed page, not sentence structure. Before searching extracted text for
  any phrase, join the pages and collapse whitespace
  (`" ".join(text.split())`). Report a window of surrounding context rather than
  "the matching line", because there is no such thing as a meaningful line here.
- **Then it failed again on punctuation**: with the wrap fixed, the check still
  warned. OpenStax prints "Attribution Non-Commercial ShareAlike"; Creative
  Commons' own name is "Attribution-NonCommercial-ShareAlike". Same licence,
  different hyphens. **Never match prose against prose.** Reduce both sides to a
  canonical form — here, strip every non-alphanumeric character — and accept any
  of the equivalent spellings (long name, short code `CC BY-NC-SA 4.0`, or the
  licence URL path). Guarding a claim this important needs a matcher that cannot
  be defeated by typography, and it must still reject near misses: CC BY 4.0,
  CC BY-NC 4.0, and BY-NC-SA **3.0** are all different licences.
- **Consequence beyond this script**: the same wrapping runs through the whole
  corpus, so it reaches chunking and retrieval too. A chunk boundary landing on
  an extracted line break is not a sentence boundary, and a citation snippet
  shown verbatim will carry those breaks into the UI. Worth remembering at
  `ingest.py` and at P1.
- **Date**: 2026-07-29

### Rule 9: `langchain-community` is sunset — read PDFs with `pypdf` directly

- **Trigger**: `SPEC.md` §2 and §8 Rule 1 both name `langchain-community` as the
  source of `PyPDFLoader`. Importing it prints a deprecation warning, and the
  package's own README states it **has been sunset**. There is no successor —
  no `langchain-pypdf` exists on PyPI.
- **Correct behavior**: `cliopedia/ingest.py` reads PDFs with `pypdf` directly
  in `load_pages()`, and `langchain-community` is removed from
  `requirements.txt` (140 → 119 resolved packages). `pypdf` is now a **direct**
  dependency rather than a transitive one. This is not a retreat from §4.1 but
  an application of it: LangChain for the boring stable parts, our own code for
  the explainable parts — and a sunset package is no longer the stable part.
  The splitter, embeddings wrapper and Chroma wrapper all stay.
- **Consequence**: `PyPDFLoader` set `page` as a **0-based** index. `load_pages()`
  emits `page_index` **1-based**, matching what a PDF viewer's page box expects.
  Do not mix the two conventions.
- **Date**: 2026-07-29

### Rule 10: cite the printed folio, never a guessed one

- **Trigger**: the PDF's page index is not the number printed on the page —
  OpenStax's front matter offsets them — so a citation reading "p. 214" would
  have pointed at the wrong printed page. For a project whose thesis is that the
  citation is the product, that is a correctness bug, not cosmetics.
- **Correct behavior**: every chunk stores **both**. `locator_value` is the PDF
  page, always correct for navigation. `printed_page` is the typeset folio, and
  is filled in only when `_folio_offset()` establishes the offset with a clear
  majority of pages agreeing — otherwise it is `-1`, meaning *not known*, never
  *probably this*. Declining to answer is the safe result here, exactly as it is
  for the model itself (§4.4).
- **Confirmed on the real corpus, 2026-08-03**: the offset came out as 16 —
  PDF page 226 is printed page 210 — checked against the PDF itself, on a
  page whose text matches the retrieved chunk. Both the number and the
  passage agree, so citations show the folio a reader actually sees.
- **Date**: 2026-07-29

### Rule 11: run the command in the exact form you document it

- **Trigger**: §3 and the README both list `pytest`. Every verification run had
  actually used `python -m pytest`. Those differ — the `-m` form puts the
  working directory on `sys.path` and the bare command does not — so the
  documented command failed with `ModuleNotFoundError: No module named
  'cliopedia'` the first time the author ran it. A suite that passes or fails
  depending on how it was invoked is worse than one that plainly fails.
- **Correct behavior**: verify the *literal* command line that appears in the
  docs, not a near-equivalent. Where two forms should both work, make them
  both work rather than documenting the one that happens to. Fixed here with
  `pytest.ini` setting `pythonpath = .`, so `pytest` and `python -m pytest` are
  interchangeable from the repo root.
- **Date**: 2026-08-03

### Rule 12: a file a human types into needs no escaping rules

- **Trigger**: the evaluation question set was TOML. Its `why` field holds
  sentences copied out of the PDF — quotation marks, apostrophes, wrapped
  lines — and a TOML `"..."` string permits none of those. The author's first
  question set failed to parse, and so did the second, on exactly that.
  Improving the error message did not help: the format was wrong for the job.
- **Correct behavior**: `eval/questions.txt` is a plain line format —
  `ask:` / `pages:` / `why:` start a field, any other line continues the one
  above, a blank line ends an entry. No quoting, no escaping, nothing that
  breaks when prose is pasted in. Twenty lines of parser in
  `cliopedia/evaluate.py`.
- **The general point**: structured formats are for machines writing to
  machines. A file maintained by hand, holding free text, should be forgiving
  by construction rather than validated after the fact. Reach for a bespoke
  line format when the alternative is teaching a person escaping rules.
- **Date**: 2026-08-03

### Rule 13: check the answer key before believing the score

- **Trigger**: the first evaluation run scored **73.3% hit rate at k=4** with
  four misses, and the obvious reading was "retrieval needs tuning". It did
  not. Two of the four gold pages were **PDF page numbers written where
  printed folios were required** — 230 instead of 214, 293 instead of 277,
  each exactly the corpus's folio offset of 16 too high. `Retrieved.cite_page`
  reports the printed folio, so the evaluator was asking retrieval to find
  pages that do not exist in the units it reports, then marking it wrong when
  it returned the correct page **at rank 1**. Corrected, the same index and
  the same code scored **86.7%**. Nothing about retrieval changed.
- **Correct behavior**: a retrieval metric is worth exactly what its answer
  key is worth, and a wrong gold label is **indistinguishable from a broken
  retriever** by the score alone — both print MISS. So when the number
  disappoints, read the misses before touching a knob. Two tells, both cheap:
  a miss whose retrieved pages sit a **constant offset** from the expected one
  is a units bug, not a ranking bug; and a hit rate that **plateaus below
  100% no matter how large k grows** means some gold page is unreachable at
  any depth, which usually means it is not a real page.
- **Why it matters more here than in most projects**: this repo carries two
  page numbers per chunk on purpose (§8 Rule 10), so "page" is ambiguous
  everywhere unless the unit is named. Anything comparing pages — the eval
  set, a bug report, a citation screenshot — must say **which** numbering it
  means. `eval/questions.txt` says so in its header; that was not enough,
  because the number still gets read off a viewer's page box.
- **The general point**: tuning against an unverified ground truth does not
  merely waste effort, it **actively degrades the system** — every "gain"
  moves retrieval toward returning the wrong page. Verify the ruler, then
  measure. Recorded also because it makes a good interview answer: the first
  eval run did not measure retrieval, it caught a bug in the measurement.
- **Date**: 2026-08-05

### Rule 14: a doubling sweep locates a plateau only to within a factor of two

- **Trigger**: `SWEEP_K` was `(1, 2, 4, 8, 16)`. The corrected sweep read
  86.7% at k=4 and 100% at k=8, flat thereafter — which invites "k=8 is where
  recall tops out". It is not: **k=6 already reached 100%**, and 8 was merely
  the first grid point past it. Setting `RETRIEVAL_K=8` off that curve would
  have bought two extra passages of pure noise per query.
- **Correct behavior**: when the quantity being read off a sweep is *where a
  curve stops climbing*, the value that matters is the **first** k on the
  plateau, and a geometric grid cannot resolve it. Find the bracket with the
  coarse grid, then measure the integers inside it — `-k` takes a single
  value, so this costs one command each. `SWEEP_K` now includes 6. A cheap
  cross-check before running anything: MRR rising only slightly between two
  grid points means the newly-found pages sit at low ranks, and dividing the
  MRR delta by the number of newly-hit questions estimates those ranks
  directly. Here it predicted ranks 5 and 6, and they were 5 and 6.
- **Date**: 2026-08-05

### Rule 15: an identifier that was unique yesterday is not unique after the corpus grows

- **Trigger**: `evaluate()` retrieved `Retrieved` objects that each know their
  `source_title`, then threw it away — `score(question, [hit.cite_page for hit
  in hits])` — and `score()` matched bare integers. Correct for exactly as long
  as the corpus held one book. Every volume has a page 210, so the moment the
  two World History volumes were registered, a World History page 210 returned
  for a U.S. History question would have scored a **hit at rank 1**. Confirmed
  against the old scorer before the fix, not assumed: pure-wrong-book results
  scored rank 1, and a wrong-book page 210 stole rank 1 from the real one.
- **Why this one is nastier than Rule 13**: both are answer-key bugs, but they
  run in opposite directions. A wrong gold page prints MISS — it depresses the
  score, and a disappointing number gets investigated. A wrong-**book** hit
  prints a rank and **raises** the number. Nothing looks wrong, so nothing gets
  looked at, and every subsequent tuning decision is made against a score that
  is partly counting noise as signal. **Prefer the failure mode that complains.**
- **Correct behavior**: `score()` takes `(source_title, printed_page)` pairs and
  both must match. `eval/questions.txt` carries a required `book:` field holding
  a corpus key, validated against `cliopedia/corpus.py` at load time — a missing
  or unknown key is refused with the valid keys listed, never defaulted. `Result`
  carries the book all the way into `_report`, so a miss prints *which book
  retrieval went to instead*, which is usually the whole diagnosis. The book
  is named per entry rather than as a file-level default: Rule 13's lesson was
  that an ambiguous unit is what lets a bad measurement pass unnoticed, and a
  default hundreds of lines above the entry is an ambiguous unit.
- **The general point, worth more than the bug**: this project deliberately
  carries two page numbers per chunk (Rule 10) and now three books, so "page
  210" has never been a complete address and is now actively ambiguous. When
  the corpus, the schema, or the key space **grows**, re-audit every place that
  compares identifiers — the code does not break, it silently starts agreeing
  with the wrong thing. Ask of any equality test: *was this unique because of a
  property I still have, or because there only used to be one of them?*
- **Not fixed here, and still open**: `cite_page` falls back to the PDF page
  when `printed_page` is `-1` (folio offset unestablished). U.S. History's
  offset is 16; the World History volumes' offsets are unknown until ingest runs
  on them. If one fails to establish, that book's pages come back in PDF units
  while `questions.txt` is in printed units and every question for it MISSes —
  loud, and therefore the safe direction, but check the ingest output for it.
- **Date**: 2026-08-07

### Rule 16: reading the index modifies it, and the index is a committed file

- **Trigger**: running `python -m cliopedia.evaluate --sweep` — a pure read —
  left `data/chroma/chroma.sqlite3` showing as modified in `git status`. Opening
  a SQLite database mutates its header (the change counter, and page bookkeeping
  on checkpoint) even when nothing is written. Same size, same rows: verified by
  hashing all 9275 embedding rows and all 64,925 metadata rows on both sides —
  **identical content, different bytes**.
- **Why it matters here specifically**: nearly every project can ignore this,
  because nearly every project keeps its database out of Git. This one commits
  the index on purpose (`SPEC.md` §4.1 — Streamlit Community Cloud gives us no
  database). So an incidental 69 MB binary diff appears after *any* query, and
  `git commit -a` would silently add 69 MB to history for a change that means
  nothing. Do that a few times and the clone is hundreds of MB of noise. Git
  stores every version forever and cannot delta-compress this file usefully.
- **Correct behavior**: after querying or evaluating, `git checkout --
  data/chroma/` to discard the churn. Only commit the index when it was
  genuinely **rebuilt** — i.e. right after `python -m cliopedia.ingest
  --rebuild`, and for a real reason (corpus, chunking, or embedding model
  changed). Treat a `data/chroma/` diff that follows a read as noise to drop,
  never as a change to record. If it is ever unclear which happened, compare
  logical content rather than bytes: row counts and a hash over the rows.
- **The general point**: "is this file modified?" and "is this file's meaning
  different?" are not the same question, and for binary build artifacts under
  version control they routinely disagree. Ask which one you actually care
  about before committing.
- **Date**: 2026-08-10
