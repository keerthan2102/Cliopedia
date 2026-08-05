# HANDOVER.md

**Relay baton. Read this, then DELETE this file, then continue the work.**
A stale handover from two sessions ago poisons the current one. Pick it up,
throw it away, keep running.

**Written:** 2026-08-03 · `main` @ `d88d43f` · P0 proven, P1 built, eval harness
awaiting its question set.

---

## 0. Read these first, in this order

1. `CLAUDE.md` — the working agreement. **§7 behavioural rules are literal**
   (one step at a time; explain before *and* after; show options and wait for a
   choice on real decisions; end every step with a status line). **§8 has ten
   learned rules.** Do not re-learn them.
2. `SPEC.md` — the blueprint. **Read-only.** Contains one deliberately-wrong
   claim, see §5 Gotcha 1.
3. `.claude/soul.md` — git-ignored, exists only on the author's machine. If
   absent: MS AI student at Kent State, graduating May 2026. **Strong** in
   Python / pandas / ML / DL / Streamlit. **Beginner** at RAG, LangChain,
   embeddings, vector stores, prompt design, Ollama — wants those taught
   thoroughly. Direct, no filler, no cushioning. **Blunt ≠ terse:** generous
   explanation is the deliverable, not padding.

---

## 1. What this project is

**Cliopedia** — a local, open-source RAG study assistant for history students.
Question → retrieve passages → an open LLM answers using **only** those
passages → answer shown with citations to the exact printed page.

Portfolio project. Audience: a hiring manager reading the repo cold, and the
author defending it in an interview. **The citation is the product.**

---

## 2. What was accomplished this session

Nineteen commits. The shape of it:

| Commit | What |
|---|---|
| `2c7578e` | `ingest.py` — PDF → chunks → embeddings → Chroma |
| `e7aaf8a` | dropped `PyPDFLoader` for `pypdf`; printed-folio detection |
| `5cf084f` | `retrieve.py` + tests; **forced cosine distance** at ingest |
| `0d6489f` | `prompts.py` + `generate.py` — the grounded-answer prompt |
| `cac85fd` | `citations.py` + `ask.py` — **P0 complete** |
| `5b34df5` | `app.py` — the Streamlit UI (P1) |
| `516e106` | streaming answers |
| `938e48e` | fixed `[2]****[4]` marker rendering; capped answer length |
| `d60ccb6` | **fixed a severe refusal-classification bug** (see §4.4) |
| `3f0084d`, `ac83c32` | warm-up: found the real first-question cost |
| `d88d43f` | `cliopedia/evaluate.py` + `eval/questions.toml` |

**P0 is proven end to end on the author's machine.** A real question returns a
grounded answer citing printed page numbers against Ollama over 3775 chunks.

---

## 3. Current state

### Works, verified on the author's Windows machine

- `python scripts/download_sources.py` — fetches, verifies `%PDF-` **and**
  `%%EOF`, reports pages, checks the licence.
- `python -m cliopedia.config` — resolved settings, key redacted.
- `python -m cliopedia.ingest` — **985 text pages of 987, 3775 chunks, folio
  offset 16** (PDF page 226 = printed page 210, confirmed against the PDF).
- `python -m cliopedia.retrieve "..."` — top-4 with similarity ~0.63 on the
  Louisiana Purchase, semantically correct passages.
- `python -m cliopedia.ask "..."` — grounded answer, `[n]` markers, sources.
- `streamlit run app.py` — streaming answers, source cards, attribution.
- `pytest` — **82 tests**, no corpus/model/network needed.

### Broken

Nothing known.

### Half-done — this is the live task

**`eval/questions.toml` needs its question set written.** It has three seeded
entries; **two are marked `UNVERIFIED`** because they came from retrieval
output. The harness runs, the data does not exist yet. See §3 below.

### Not started

P2 (grade-level explanations, quiz generation, primary sources), corpus
expansion to World History, deployment.

### Environment split — important

The author runs **Windows**, `C:\Users\minnu\OneDrive\Documents\GitHub\Cliopedia`,
venv active, corpus present, Ollama running `llama3.2:3b` on GPU. **The Claude
session runs in a Linux container with no corpus, no Ollama, and a network
policy that blocks openstax.org.** Working split: **Claude writes and
unit-tests code; the author runs anything needing the corpus or a model.**

---

## 4. Exact next steps

### Step 1 — the author writes `eval/questions.toml` (blocking, human-only)

Aim for ~15 entries. The file's own comments carry the method. **The critical
rule, repeated because getting it wrong makes the whole exercise worthless:**
do NOT write questions by running retrieval and recording what comes back —
that measures whether retrieval agrees with itself. Open the PDF, **read** a
page, write a question that page answers, record the **printed** folio.

Then:
```
python -m cliopedia.evaluate            # hit rate + MRR at current k
python -m cliopedia.evaluate --sweep    # k = 1,2,4,8,16
```
**Those numbers are the "before" baseline.** Record them in `CLAUDE.md` — they
are what makes the corpus expansion measurable rather than assumed.

### Step 2 — set `RETRIEVAL_K` from the sweep

Where hit rate stops climbing is where extra passages add noise rather than
recall. Currently 4, a guess. `SPEC.md` §11 explicitly defers this to evidence.

### Step 3 — expand the corpus to three books

Already researched and **licence-verified from OpenStax's own collection
metadata** — all three are **CC BY-NC-SA 4.0**, same as the current corpus, so
no new licensing work and the README's existing split still holds:

| Book | Repo |
|---|---|
| World History Volume 1, to 1500 | `openstax/osbooks-world-history` |
| World History Volume 2, from 1400 | `openstax/osbooks-world-history` |
| U.S. History (current) | `openstax/osbooks-us-history` |

The code is **already multi-book by design**: `ingest.py` globs `data/raw/*.pdf`,
`SOURCES` maps filename → (title, type), every chunk stores `source_title`, and
citations render it. What is missing is a **corpus registry** —
`scripts/download_sources.py` hardcodes one `DEFAULT_URL`, so three books means
three manual invocations plus hand-editing `SOURCES`. That should be one list.

**PDF URLs are not yet known.** `assets.openstax.org` is blocked from the
container. The author gets them from the book pages and **must `--inspect`
before downloading** (Gotcha 2):
- https://openstax.org/details/books/world-history-volume-1
- https://openstax.org/details/books/world-history-volume-2

**Re-run the eval after the rebuild.** That comparison is the deliverable.

### Step 4 — the author has still not committed `data/chroma/`

It is deliberately **not** git-ignored. P3's deployment reads a prebuilt index.
Expect a large commit; if git objects, report the size before doing anything
clever.

---

## 5. Decisions made, and why — do not silently reverse these

1. **Cosine distance, forced at collection creation.** Chroma defaults to L2.
   `ingest.COLLECTION_METADATA = {"hnsw:space": "cosine"}`. **The metric is
   fixed when the collection is created** — an index built without it is ranked
   by the wrong measure and needs a full rebuild.
2. **`langchain-community` is gone.** Upstream sunset it; `load_pages()` reads
   PDFs with `pypdf` directly. 140 → 119 packages. See §8 Rule 9. Note
   `PyPDFLoader` numbered pages from **0**; `load_pages()` numbers from **1**.
3. **Two page numbers per chunk.** `locator_value` = PDF page (always right for
   navigation); `printed_page` = typeset folio, recorded only when
   `_folio_offset()` gets a clear majority, else `-1` meaning *not known*. See
   §8 Rule 10.
4. **`is_refusal()` is not a substring match**, and this was a severe bug.
   A model answered a broad question in four cited paragraphs, then appended
   the reserved refusal sentence for the part it could not cover. A substring
   match classified the whole thing a refusal and **discarded every source
   card** — presenting fully traceable work as though nothing was found. Now
   the refusal must be essentially the whole answer, and prompt rule 6 says the
   sentence is reserved for total refusals.
5. **Only cited passages become source cards.** Listing all four retrieved
   under an answer that used two is a quiet lie about provenance. Markers
   pointing outside the given range are dropped — the prompt forbids inventing
   one, but forbidding is not preventing.
6. **Snippets are marked, never trimmed.** Chunk boundaries cut mid-sentence;
   `display.as_excerpt` adds a leading/trailing `…` and changes not one word.
   Fidelity is the point — a test asserts the excerpt contains exactly the words
   it was given.
7. **`ingest.py` refuses an existing index without `--rebuild`.** Chroma's
   `add_documents` appends, so a second run stores every chunk twice and k=4
   silently becomes k=1. Author's choice from three options.
8. **Config is a hybrid** (author's choice): index settings default and validate
   at import; LLM settings are required and read **on demand** via
   `llm_settings()`, so `pytest` and `ingest` need no API key.
9. **Streaming, plus a 400-token cap.** Same total time, first words in ~1s.
   The cap bounds worst-case latency.
10. **LangChain stays thin. No `RetrievalQA` or any prebuilt chain.** The
    retrieve → prompt → generate → cite loop is hand-written so the author can
    explain every step. **Do not "simplify" this into a chain.**
11. **"Not covered in the source material" is a success case.**
12. **Source PDFs git-ignored; the Chroma index committed.**
13. **One OpenAI-compatible client.** Never write `if backend == "ollama"`.
14. **Package is `cliopedia/`, never `lib/`** — the seeded `.gitignore` ignores
    `lib/`, so such a folder would be silently untracked.

---

## 6. Gotchas the next session absolutely needs

1. **`SPEC.md` still says CC BY 4.0 in six places, deliberately.** It is
   read-only by rule; `CLAUDE.md` §8 Rule 3 is the correction of record. The
   real licence is **CC BY-NC-SA 4.0**. **Do not "fix" SPEC.**
2. **An HTTP 200 is not verification.** `USHistory-OP.pdf` returns 200 and
   downloads happily while being a truncated 2016 object — no `%%EOF`, size an
   exact multiple of 4096. Cost two 324 MB downloads. Use
   `--inspect` on any candidate URL first. The good one is
   `US_History_-_WEB.pdf`. See §8 Rule 7.
3. **The container's network blocks nearly everything.** 403 on CONNECT for
   openstax.org, archive.org, huggingface.co, github.com, api.github.com.
   **Reachable:** `pypi.org`, `files.pythonhosted.org`,
   `raw.githubusercontent.com`. This is the *environment*, not the sites — the
   author's machine is unrestricted. `curl -sS "$HTTPS_PROXY/__agentproxy/status"`
   shows the live policy.
4. **OpenStax book metadata IS reachable** via `raw.githubusercontent.com`, and
   that is how the licences were verified:
   `.../openstax/<repo>/main/collections/<slug>.collection.xml` → `<md:license>`.
   `META-INF/books.xml` lists a repo's slugs. Use this before trusting any
   licence claim.
5. **PDF text extraction wraps mid-sentence.** `extract_text()` preserves the
   printed column's line breaks, not sentences. It broke the licence checker
   twice and it reaches chunking and the UI. Normalise before matching
   anything; **never match prose against prose** — reduce to a canonical form.
   See §8 Rule 8.
6. **The author is on Windows.** Never hand over a bare `source
   venv/bin/activate`. CMD needs **backslashes** — `venv\Scripts\activate`;
   `venv/Scripts/activate` fails. `cp` → `copy`. Forward slashes inside Python
   arguments are fine. See §8 Rule 4.
7. **Windows runs Ollama as a service.** `ollama serve` reporting the port busy
   is success, not failure.
8. **First-question latency was misdiagnosed twice.** It is **not** Ollama
   (`ollama ps` showed the model resident, 100% GPU) and **not** model size
   (8B→3B changed nothing). It is `load_embeddings()` — PyTorch plus ~90MB of
   weights. `app.py` now warms it on the main thread after the form renders.
   **If a timing question comes up again, instrument before theorising.**
9. **Streamlit's file watcher is disabled** in `.streamlit/config.toml`. It
   walked `transformers` and printed pages of torchvision tracebacks that look
   like failures and are not. Cost: no auto-rerun on save.
10. **Streamlit telemetry is off** in the same file, because `SPEC.md` §10
    claims no analytics and that claim was false until it was turned off.
11. **Never put backticks in a double-quoted `git commit -m`.** Bash eats the
    word. Use `git commit -F <file>` and read it back with
    `git log -1 --format=%B`. See §8 Rule 5.
12. **Before any history rewrite, make a backup ref.** A chained
    `reset --hard`/`cherry-pick`/`--amend` already went wrong once —
    `cherry-pick` has no `-q`, `set -e` did not halt, and the amend landed on
    the wrong commit. Prove content-neutrality with tree hashes. See §8 Rule 6.
13. **Unverified:** whether Streamlit Cloud exposes secrets as environment
    variables. `config.py` reads `os.environ`. If secrets turn out to be
    `st.secrets`-only, a small adapter is needed at deploy. **Do not assert
    either way.**
14. **Unverified:** Streamlit Cloud's memory/storage limits, and whether a
    PyTorch install fits. `SPEC.md` §2.2 documents Chroma's ONNX embedder as
    the fallback; switching costs a full index rebuild. **Adding two more books
    roughly triples the committed index — this risk grows with step 3.**
15. **Unverified:** Groq's current free-tier model lineup. **Do not guess a
    model name.**
16. **Quality signal worth following up:** `llama3.2:3b` cites noticeably less
    rigorously than `llama3.1:8b` did — several sentences per answer carried no
    marker, and one answer ended in unsourced synthesis. `attach()` cannot
    catch that; it only maps markers that exist. An answer where most sentences
    are unmarked passes every check while being largely untraceable. Worth a
    metric of its own.
17. **Security, every commit:** `git add -A`, inspect `git diff --cached`, then
    commit. `LLM_API_KEY` is the only real secret. The repo is public.

---

## 7. Open questions for the author

1. Has `eval/questions.toml` been filled in, and what were the baseline numbers?
2. `RETRIEVAL_K` after the sweep — still 4?
3. Which model to settle on: `llama3.2:3b` (fast, looser citation discipline) or
   `llama3.1:8b` (slower, more rigorous)? Gotcha 16 argues this deserves a
   measurement, not a preference.
4. `data/chroma/` still uncommitted.
5. Does OneDrive need excluding for `data/`? The repo lives inside a OneDrive
   folder; the corpus is 136MB of git-ignored, re-fetchable data. Raised twice,
   never answered.
