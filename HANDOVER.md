# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention (README §Project documents; commits `1f06fc7`, `772dd1e`
and `35bf3b6` removed earlier ones after pickup).

Written 2026-08-11. `main` is at **`100278b`**. Working tree clean.
170 tests pass. 31 eval questions. Index 76 MB, 8330 chunks.

Read `CLAUDE.md` first — it is the working agreement and overrides anything
here. This file carries only what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

27 commits, PRs #3–#28, all merged to `main`. Two arcs.

### The corpus expansion

1 book → 3, 3775 → 8330 chunks, all licences read off the PDFs themselves.
Folio offsets 16/10/10, five World History gold pages human-verified against
rendered pages. Index committed for the first time.

Two measurement bugs found by *preparing* the expansion, not running it:
book-blind scoring (→ Rule 15) and `_folio()` detecting 6 folios in 987 pages.

### The grounding investigation

Asked "What happened during the 2008 financial crisis?", the app produced a
fully cited answer describing "a massive stock sell-off in late October" and a
40 percent fall — **Black Tuesday 1929**. Retrieval scored a hit at rank 1.

Measured with `python -m cliopedia.grounding`, ten samples per configuration:

| configuration | runs citing 1929 | uncited sentences |
|---|---|---|
| baseline | 9/10 | 47 |
| + reranking | 2/10 | 33 |
| + back-matter excluded | **0/10** | 31 |
| + page dedup | 1/10 | 17–22 |
| + per-sentence citation rule | 1/10 | 21 |

**The headline lesson, and the most transferable thing here:** three prompt
attempts moved nothing measurable; three structural changes moved everything.
Recorded in `CLAUDE.md` §1. Do not ship a prompt edit here claiming it will
move a number.

---

## 2. Current state

### Works

- 170 tests, both `pytest` and `python -m pytest`.
- Index committed: 8330 chunks, 76 MB (`chroma.sqlite3` 61.6 MB — over GitHub's
  50 MB advisory, well under the 100 MB hard limit).
- Retrieval at k=6: **hit 93.5%, MRR 0.729, 6.0 distinct pages/query**.
- `RERANK=on` gives MRR 0.883 on the pre-dedup index; **off by default** for
  deployment reasons only (`SPEC.md` §2.2).
- The author runs the app on Windows against the committed index.

### The one open defect

**~20 uncited factual sentences per 10 runs.** Sentences stating real facts from
the corpus that carry no `[n]` marker, so `app.py` renders no source card and a
reader cannot check them. On screen they are indistinguishable from invention,
which is precisely the failure this project defines itself against.

Prompt rule 4 was strengthened for exactly this (PR #27) and **had no effect** —
21 against a 17–22 band already seen without it.

### Half-done: the decision waiting on the author

**Surface uncited sentences in the UI.** `cliopedia/grounding.py::uncited_sentences`
already detects them. `app.py` currently errors only when an answer cites
*nothing*; this would extend it to the commoner case — some sentences cited,
others bare — listing them under something like "Not traceable to a source —
treat as unverified."

Put to the author, not yet answered. Two reasons it is theirs:
- it changes what the app tells a **student**, a product judgement rather than a
  metric;
- the detector is crude (any sentence with 3+ content words and no marker), so
  it will flag some harmless summary lines, and showing false positives has its
  own cost.

### Smaller open items

- **Rule 6 violations**: answers sometimes contain "Note: passages [3] and [5]
  describe…". The reasoning is right, the voice is wrong — the prompt forbids
  mentioning "the passages". Seen in ~2 runs of 10.
- **`RERANK` deployed default** — quality case settled, deployment case belongs
  to P3.
- **P1 UI sign-off** — no completed human pass against "a stranger can use it
  unaided and verify any claim".
- **Rule 10's confidence claim** still says the offset of 16 was established
  "with a clear majority of pages agreeing". It was 6 of 987 — a majority of
  *detections*. Correction is in the `_folio_offset` docstring; amending a
  learned rule was left to the author.
- **Ten World History gold pages** verified only by the extraction they were
  written from (five were checked against rendered pages).

---

## 3. Exact next steps

### Step 1 — the UI change, once the author decides

`app.py`, after the Sources block. `uncited_sentences(text)` returns the
offending sentences. Keep the existing "cited no passages at all" error; this is
an addition, not a replacement.

Re-measure afterwards with the sampler, but note **the count will not change** —
this makes the problem visible rather than smaller. The success criterion is a
reader being told what they cannot check, not a lower number.

### Step 2 — if more grounding work is wanted, attack it structurally

Prompt edits are exhausted (see §1). What remains untried and structural:

- **Chunking** — `CHUNK_SIZE`/`CHUNK_OVERLAP` in `cliopedia/ingest.py` are
  untouched defaults from `SPEC.md` §6.1, explicitly flagged there as "starting
  defaults, not tuned values". For the Glorious Revolution question the gold
  page still sits *behind* its neighbours; that is a chunking symptom.
- **Hybrid keyword+vector search** — never attempted.

Both need an index rebuild and both are measurable in-container with
`python -m cliopedia.evaluate --sweep`.

### Step 3 — the two questions no measurement can answer

The `RERANK` deployed default and P1 sign-off. Both need the author.

---

## 4. Decisions made, and why

| Decision | Why |
|---|---|
| `book:` required per entry in `eval/questions.txt` | Every volume has a page 210. Matching on the number alone scored a wrong-book hit at rank 1 and **inflated** the score — the failure mode that does not complain. → Rule 15 |
| Fix `_folio()` rather than hardcode offsets | Reproduces the known-correct 16 with a 76× stronger majority and works for future books |
| `RETRIEVAL_K` stays 6 | 13 of 15 questions rank identically at k=6/10/15 |
| Chapter filtering **rejected** | Measured: fixes one question, breaks four. When rank 1 is in the wrong chapter, anchoring on it entrenches the error |
| Reranking **behind a flag, default off** | MRR 0.699 → 0.883, but it loads a second model and `SPEC.md` §2.2 flags Cloud memory as unverified |
| Back-matter excluded from the index | Assessments pages are lists of *questions* — they match a student's question closely and contain no answer. MRR 0.699 → 0.724, no gold page affected |
| Page dedup **kept despite a regression** | 4.4 → 6.0 distinct pages, uncited claims 31 → ~20, wrong-chunk citation fixed; era-merging 0/10 → 1/10. Author's call, made deliberately |
| Grounding tool **reports, never scores** | An overlap score caught 1 of 3 known failures. Publishing it would have been Rule 13 in a new place |
| Prompt rules kept despite no effect | They cost nothing and a stronger deployed model may honour them |

---

## 5. Gotchas the next agent absolutely needs

**No Ollama in the remote container.** Retrieval, ingest, eval and tests run
there; **generation does not**. Every prompt change must be verified by the
author. Three were shipped on reasoning this session and none worked.

**LLM output is stochastic — sample, never take one run.** Two runs on identical
code produced one clean answer and one with a false claim. Every number in §1
is over ten runs; earlier single-sample conclusions were wrong twice.

**The measurement tool needed more fixing than the system it measures.** It
under-reported citations (a sentence citing `[3][4]` tallied only `[4]`), then
over-reported chapter spread (`32.2` counted as outside chapter 32). Both errors
made the picture look tidier. **Check the instrument before believing it.**

**Reading the index modifies it.** After any query, `git status` shows
`data/chroma/chroma.sqlite3` modified — SQLite rewrites its header on open.
`git checkout -- data/chroma/`. **Never commit that churn** (61 MB per time).
Only commit after a genuine `ingest --rebuild`. Rule 16; it fired constantly.

**A rebuild renames the collection UUID directory**, so a plain `git pull`
aborts for anyone holding a local index. If the file is *tracked and modified*,
`git checkout -- data/chroma/` first; if *untracked*, move it aside.

**Never commit mid-rebuild** — `--rebuild` deletes the index before re-embedding.

**On Windows an env var must be set on the same line as the command**:
`$env:RERANK="on"; .\venv\Scripts\python.exe -m ...`. A separate `$env:` in
another window never reaches the process. This cost a full round trip.
`python -m cliopedia.config` shows whether it took.

**The author's repo is inside OneDrive**, which holds files open and blocks
deletes during a rebuild — see the `_remove_index` docstring.

**The container is ephemeral.** `data/raw/` (470 MB) and `venv/` (5.8 GB) are
git-ignored and vanish. You do **not** need them to query — the index is
committed. Only to re-ingest or read source pages.

**Downloads truncate around 120–130 MB; just retry.** Not a size cap — the
201 MB volume comes down whole.

**Never run `pip install` alongside other work.** It broke `_cffi_backend`
mid-run and made `download_sources.py` silently skip its licence check.

**The eval CLI reloads the embedding model per invocation.** For multi-k work
build `HuggingFaceEmbeddings(...)` once and pass it via
`evaluate(qs, k=k, embeddings=emb)`. Minutes instead of an hour.

**Do not compare hit rate across books.** The World History questions lean on
distinctive proper nouns; the U.S. History ones are paraphrased into a student's
voice. Track per-book rows over time.

**With `RERANK=on` the similarity column does not descend** — those are
embedding scores, the order comes from the cross-encoder. The CLI says so.

**`_heading()` covers 89–91% of pages** and returns `None` for the rest rather
than guessing. Its line ordering is load-bearing.

**The five-vote floor in `_folio_offset()` is load-bearing** — World History
Vol 2 detected one folio and voted *unanimously* for offset 404.

**Passage labels must never carry page numbers** — rule 5 forbids the model
citing pages and `citations.py` depends on passage indices. Pinned by a test.

**Branching.** `main` is the trunk; no feature branches. When a harness forces
one, PR into `main` and **merge before the session ends**. Branch deletion is
**HTTP 403** here — ask the author. Watch for stranded commits: a branch reset
to `origin/main` left the index commit behind this session. Verify with
`git ls-files`, not the log.

**Commit messages: no backticks** in a double-quoted `-m` string (Rule 5). Use
`git commit -F`; read back with `git log -1 --format=%B`.

**`SPEC.md` is read-only.** It still says CC BY 4.0 and `k = 4`; both
superseded. Corrections live in `CLAUDE.md` §8.
