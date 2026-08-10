# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention (README §Project documents; commit `1f06fc7` removed an
earlier one after pickup).

Written 2026-08-10. `main` is at **`ac1f9f3`**. Working tree clean.
141 tests pass.

Read `CLAUDE.md` first — it is the working agreement and overrides anything
here. This file carries only what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

Two things: the corpus expansion end to end, and a hunt for a grounding bug that
is **still open**. Twelve commits, PRs #3–#14, all merged to `main`.

| commit | what |
|---|---|
| `f8a5ccb` | fix: score retrieval on book and page, not page alone |
| `16b292b` | fix: read the folio off a running footer, not only a bare line |
| `091e2ab` | feat: rebuild the index over all three books |
| `b4080e5` | docs: record the three-book retrieval baseline |
| `4372209` | docs: settle RETRIEVAL_K at 6 |
| `4d9fba6` | test: cover World History in the question set |
| `ecb87ee` | docs: add a day-to-day run section to the README |
| `ebd5d48` | fix: forbid the model merging passages about different events |
| `395f468` | feat: show each passage its chapter, so the model can tell eras apart |

**Corpus:** 1 book → 3, 3775 → 9275 chunks. All licences read off the PDFs
themselves (CC BY-NC-SA 4.0). Folio offsets 16 / 10 / 10, verified on 600/600
sampled pages. Index committed for the first time.

**Two measurement bugs**, both found by *preparing* the expansion rather than
running it: book-blind scoring (→ Rule 15) and `_folio()` detecting 6 folios in
987 pages (fixed, now 472).

---

## 2. Current state

### Works

- 141 tests, under both `pytest` and `python -m pytest`.
- Index committed and live: 9275 chunks, 85 MB, `chroma.sqlite3` 69.5 MB.
  Exceeds GitHub's 50 MB advisory (a harmless push warning), well under the
  100 MB hard limit.
- `eval/questions.txt`: 31 questions — 16 us-history, 8 world-history-1,
  7 world-history-2.
- `requirements.txt` resolves and imports cleanly in a fresh venv. Do not
  "fix" it.
- The author runs the app on Windows against the committed index.

### The numbers

Retrieval at k=6, 3775 → 9275 chunks:

| k | hit (1 book) | hit (3 books) | MRR (1 book) | MRR (3 books) |
|---|---|---|---|---|
| 4 | 86.7% | **60.0%** | 0.656 | 0.517 |
| 6 | **100.0%** | 86.7% | 0.680 | 0.568 |
| 15 | — | 100.0% | — | 0.579 |

Per book at k=6 over 30 questions: us-history 86.7% / MRR 0.568,
world-history-1 100% / 0.875, world-history-2 100% / 0.738. **Do not read that
gap as a quality comparison** — see `CLAUDE.md` §1; the two groups were written
by different people using different methods.

---

## 3. THE OPEN PROBLEM — start here

**A grounded-looking answer is still partly wrong, after three attempts.**
Everything below is measured, not inferred.

### The case

```bash
python -m cliopedia.ask "What happened during the 2008 financial crisis?" --snippets
```

Retrieval returns six passages spanning two crises 79 years apart:

```
[1] p.896  chapter 32 The Challenges of the Twenty-First Century     <- 2008
[2] p.699  chapter 25 Key Terms                                      <- 1929
[3] p.679  chapter 25.1 The Stock Market Crash of 1929               <- 1929
[4] p.680  chapter 25 Brother, Can You Spare a Dime? ... 1929-1932   <- 1929
[5] p.896  chapter 32 The Challenges of the Twenty-First Century     <- 2008
[6] p.679  chapter 25.1 The Stock Market Crash of 1929               <- 1929
```

### What has been tried

**Attempt 1 — `ebd5d48`, prompt rule 3** ("never combine details from separate
events; check dates"). **Failed.** Diagnosed: the chunk the model quoted
contains no dates at all, so there was nothing to check.

**Attempt 2 — `395f468`, chapter labels in `format_passages()`.** **Partial.**
The worst fabrication went — "a massive stock sell-off in late October",
"40 percent", and passage [2] are no longer used. [1] and [5] are now used
correctly (TARP, adjustable-rate loans, job figures), and the model volunteered
a limitation about subprime mortgages, which is rule 7 working.

**Two claims still come from 1929 passages:**
- "People withdrew their money from banks, fearing that they would go under [3]"
- "The contagion effect of panic played a significant role in the crisis [4]"

### The diagnosis that matters

The answer contained: *"The 2008 financial crisis had some similarities to the
Great Depression of the 1930s."* **The model saw the chapter labels and
understood two eras were present** — then bridged them with a comparison instead
of excluding the wrong ones.

The labels worked as *information* and failed as a *constraint*. **Adding more
context to the prompt is not the next move** — the signal already lands.

### The proposed next step, NOT yet implemented

Filter in code, in `cliopedia/retrieve.py`, after ranking: drop passages whose
chapter is inconsistent with the top-ranked passage's chapter, before they reach
the model. On this case that removes [2], [3], [4] and leaves the two genuine
2008 passages.

**The question the author was asked and has NOT yet answered** — strict, or
majority-guarded?

- **Strict**: always filter to the top passage's chapter.
- **Majority-guarded** (recommended in-session): filter only when a clear
  majority of passages share one chapter, so genuinely comparative questions
  keep their evidence.

**The risk, plainly:** "How did the Great Depression compare to the 2008
crisis?" is a reasonable student question, and a strict filter would gut it.
Get the author's answer before implementing.

### A second, separate bug — not addressed

In an earlier run the model cited `[3]` for *"the integral role of automobiles"*
when that snippet never mentions automobiles. That is **claim-support failure**,
not event-merging, and chapter filtering will not fix it. No fix attempted.

---

## 4. Other next steps

### Verify the World History gold pages

Spot-check 4–5 entries in the `── World History ──` block of
`eval/questions.txt` against the PDFs. They were written from `pypdf`-extracted
text, not the rendered page, so a caption could sit between quoted sentences.
Each `why:` quotes the page verbatim, so this is a read, not a rerun. Rule 13:
an unverified answer key is worth nothing.

### Attack ranking, not k

`RETRIEVAL_K` is settled at **6**; `CLAUDE.md` §1 explains why raising it is
tuning to the test. Measured levers:

- **Page-level dedup — 23% of slots are duplicate pages.** k=6 delivers **4.6
  distinct pages, not 6**. Dedup would give ~6 from a depth of about 8. Not
  implemented: two chunks from one page can carry different content and the UI
  shows a snippet per chunk, so it changes what a source card means. **Needs the
  author.**
- **Chunking.** For the Glorious Revolution question the gold page (93–94) sits
  *behind* `us-history` 107 and 92 — retrieval lands adjacent and ranks
  neighbours above it.
- **Reranking / hybrid search.** MRR 0.568 barely moves with k. That is the
  number to move.

### P1 sign-off

The Streamlit UI still has no completed human pass against its exit criterion
(a stranger can use it unaided and verify any claim). The author uses it daily.

---

## 5. Gotchas the next agent absolutely needs

**Reading the index modifies it.** After any query or eval, `git status` shows
`data/chroma/chroma.sqlite3` modified. SQLite rewrites its header on open;
content is identical. Run `git checkout -- data/chroma/`. **Never commit that
churn** — 69 MB of meaningless history each time. Only commit after a genuine
`ingest --rebuild`. Rule 16; it fired repeatedly, including via a stop hook.

**A rebuild changes the collection UUID directory name.** `data/chroma/<guid>/`
is regenerated, so git shows deletes and adds, and anyone pulling must move
their local `data/chroma` aside first or the pull aborts on untracked files.
Tell the author: `Move-Item data\chroma data\chroma.old` before pulling.

**Never commit mid-rebuild.** `--rebuild` deletes the index *before*
re-embedding. A commit in that window pushes a repo with no index at all.

**The container is ephemeral.** `data/raw/` (470 MB) and `venv/` (5.8 GB) are
git-ignored and vanish. You do **not** need them to query — the index is
committed. Only to re-ingest.

**Downloads truncate; just retry.** U.S. History took three attempts, Volume 2
two, failing around 120–130 MB. Not a size cap — Volume 1 is largest at 201 MB
and came whole. `download_sources.py` deletes partials and says to re-run.

**Never run `pip install` alongside other work.** It churned `site-packages`
mid-run, broke `_cffi_backend`, and made `download_sources.py` silently skip its
licence check.

**No Ollama in the remote container.** Retrieval, ingest, eval and tests run
there; **generation does not**. Any prompt change is unverifiable remotely —
this session shipped two prompt fixes on reasoning alone and the first failed
outright. Ask the author to run `cliopedia.ask` before claiming a prompt fix
works.

**The eval CLI reloads the embedding model per invocation.** For multi-k work
build `HuggingFaceEmbeddings(model_name=settings.embedding_model)` once and pass
it via `evaluate(qs, k=k, embeddings=emb)`. Minutes instead of an hour.

**Do not compare hit rate across books**, and note the aggregate rose
86.7% → 93.3% purely because easier items joined the set. Track per-book rows.

**`_heading()` covers 89–91% of pages** and returns `None` for the rest rather
than guessing — same principle as `_folio_offset`: unlabelled beats mislabelled.
Its line ordering is load-bearing: the openstax boilerplate occupies the last
line on many pages, and stripping a leading number before matching eats the
chapter number when the folio is printed last. That mistake held coverage at
37%.

**The five-vote floor in `_folio_offset()` is load-bearing.** World History
Vol 2 detected one folio and voted *unanimously* for offset 404.

**Two page numberings — always name which.** `locator_value` is the PDF page,
`printed_page` the folio, `cite_page` prefers the folio.

**Passage labels must never carry page numbers.** Rule 5 forbids the model
citing pages and `citations.py` depends on passage indices. Pinned by
`test_the_heading_label_carries_no_page_number`.

**The author develops on Windows.** Never hand over a bare `source` line.
PowerShell blocks `Activate.ps1` by default; the friction-free path is
`.\venv\Scripts\python.exe -m ...` or `.\venv\Scripts\streamlit.exe run app.py`.
Documented in the README's "Running it day to day".

**`.env` drifts silently.** The author's had `RETRIEVAL_K=4` and `llama3.2:3b`,
both stale, and k=4 is the *worst* point on the curve. `.env.example` is
correct. Run `python -m cliopedia.config` first when behaviour surprises you.

**Branching.** `main` is the trunk; no feature branches. When a harness forces
one, PR into `main` and **merge before the session ends**. Watch for stranded
commits — resetting a branch to `origin/main` left the index commit behind this
session, and `main` briefly carried the measurements without the index that
produced them. Verify with `git ls-files`, not the log.

**Commit messages: no backticks** in a double-quoted `-m` string (Rule 5). Use
`git commit -F`, read back with `git log -1 --format=%B`.

**`SPEC.md` is read-only.** It still says CC BY 4.0 and `k = 4`; both
superseded. Corrections live in `CLAUDE.md` §8.

---

## 6. A note on this session's method

Three attempts at the grounding bug; two shipped on reasoning that proved wrong
or incomplete. The measurements were sound throughout — heading coverage,
retrieval order, the no-dates-in-the-chunk diagnosis — but **whether the model
behaves differently was assumed twice and checked once.**

The lesson worth carrying: a prompt change is not verified until a model has run
it. In this environment that means asking the author. Everything else here can
be checked locally; that cannot.
