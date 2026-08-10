# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention (README §Project documents; commit `1f06fc7` removed an
earlier one after pickup, and this file replaces one deleted the same way).

Written 2026-08-10. `main` is at **`4098df7`**. Working tree clean.

Read `CLAUDE.md` first — it is the working agreement and overrides anything
here. This file carries only what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

The corpus expansion, end to end: one book → three, with the measurement to
show what it cost, plus a grounding fix the expansion exposed. Nine commits,
all merged to `main` via PRs #3–#12.

| commit | what |
|---|---|
| `f8a5ccb` | fix: score retrieval on book and page, not page alone |
| `16b292b` | fix: read the folio off a running footer, not only a bare line |
| `091e2ab` | feat: rebuild the index over all three books |
| `b4080e5` | docs: record the three-book retrieval baseline |
| `4372209` | docs: settle RETRIEVAL_K at 6, record where the real waste is |
| `4d9fba6` | test: cover World History in the question set |
| `ecb87ee` | docs: add a day-to-day run section to the README |
| `ebd5d48` | fix: forbid the model merging passages about different events |

Two bugs found by *preparing* the expansion rather than by running it:

**Book-blind scoring.** `evaluate()` threw away `source_title` and matched bare
page numbers. Every volume has a page 210, so a World History page 210 returned
for a U.S. History question would have scored a **hit at rank 1**. Confirmed
against the old scorer, not assumed. → Rule 15.

**`_folio()` could not see OpenStax's folios.** It required a whole line to be
digits; OpenStax prints `9.3 • The Kingdom of Kush     391`. Detection was
6/987 pages on U.S. History and 0/791 on World History Vol 1. The offset of 16
was correct but rested on six pages. Fixed to accept a folio trailing a running
footer: detection 472/987, same answer 16. Both World History volumes resolve to
**10**. Verified 600/600 sampled pages.

---

## 2. Current state

### Works, verified this session

- **130 tests pass**, under both `pytest` and `python -m pytest`.
- **Index committed and live**: 9275 chunks, 84 MB, `chroma.sqlite3` 69 MB
  (clears GitHub's 100 MB per-file limit). Folio offsets 16 / 10 / 10.
- **All three licences read off the PDFs themselves**: CC BY-NC-SA 4.0.
- **`eval/questions.txt` is 31 questions**: 16 us-history, 8 world-history-1,
  7 world-history-2.
- **`requirements.txt` resolves and imports cleanly** in a fresh venv
  (`transformers 5.14.1 / tokenizers 0.22.2`). Do not "fix" it.
- The author has the app running on Windows against the committed index.

### The numbers that matter

Retrieval at the configured **k=6**, 3775 → 9275 chunks:

| k | hit rate (1 book) | hit rate (3 books) | MRR (1 book) | MRR (3 books) |
|---|---|---|---|---|
| 4 | 86.7% | **60.0%** | 0.656 | 0.517 |
| 6 | **100.0%** | 86.7% | 0.680 | 0.568 |
| 15 | — | 100.0% | — | 0.579 |

Per book at k=6, over the 30-question set:

| book | questions | hit rate | MRR |
|---|---|---|---|
| us-history | 15 | 86.7% | 0.568 |
| world-history-1 | 8 | 100.0% | 0.875 |
| world-history-2 | 7 | 100.0% | 0.738 |

**The expansion cost real accuracy on U.S. History, but the new books are
retrievable.** So the problem is interference and *ranking*, not reachability.

### Broken / open

- **Two grounding failures are on record. A mitigation shipped in `ebd5d48`
  (PR #12) and has NOT been verified against a real model.** Both were produced
  on `llama3.1:8b`, the locked model, so neither is a small-model artifact.

  **The bad one — merged events.** Asked "What happened during the 2008
  financial crisis?", the app produced a cited answer describing "a massive
  stock sell-off in late October", a 40 percent fall, bank runs and the role of
  automobiles. That is Black Tuesday **1929**. Retrieval returned U.S. History
  p.896 (genuinely 2008 — Lehman, Bear Stearns, Bernanke) alongside pp.679 and
  699 (causes of the 1929 crash; the Great Depression key-terms glossary), and
  the model merged all three into one account of 2008. Every word came from the
  textbook, every claim was cited, and the answer was wrong by 79 years. Rule 1
  does not cover this — nothing was invented, true fragments were assembled into
  an untrue whole.

  **The subtler one — relocated claim.** Asked about the Roman conquest of
  Britain, the answer said *"the Romans did not have a permanent presence in
  Britain until the late first century CE."* World History Vol 1 p.297 dates it
  to **43 CE**, never uses that phrase, and its own "Unlike the case in Gaul"
  attaches to centuriation and roads, not to the permanent presence. The rest of
  that answer checked out against pp.297 and 423.

  **What shipped:** `prompts.py` rule 3 — passages are selected by similarity of
  wording rather than subject; check dates and names against the question; never
  combine details from separate events. Rules renumbered 4–7, with a test
  pinning the `rule 2` cross-reference.

  **Why it is probably not enough**, measured rather than guessed: the chunk the
  model quoted for the late-October claim (p.699) **contains no year at all**, so
  there is nothing in it for rule 3's date check to catch. See the open decision
  on `format_passages()` in §4.
- **P1 (Streamlit UI) still has no completed human pass.** The author is using
  it, but the exit criterion — a stranger can use it unaided and verify any
  claim — has not been formally signed off.
- **The World History gold pages have not been human-verified.** They were
  written from `pypdf`-extracted text, not the rendered page, so a caption or
  sidebar could sit between quoted sentences. Rule 13: an unverified answer key
  is worth nothing.
- **Stale branches** `claude/corpus-expansion` and
  `claude/project-overview-qlfp0c` may still exist on `origin`. The author said
  they would delete them. **Branch deletion is HTTP 403 from this environment** —
  a policy denial, not a transient failure. Do not burn retries on it.

---

## 3. Exact next steps

### Step 1 — verify the grounding fix (highest value, needs Ollama)

`prompts.py` rule 3 shipped in `ebd5d48` and has **never been run against a
model**. That environment had no Ollama. Do this first:

```bash
python -m cliopedia.ask "What happened during the 2008 financial crisis?" --snippets
python -m cliopedia.ask "Tell me about the Roman conquest of Britain?" --snippets
```

Failure signatures to look for: "late October" or "40 percent" or bank runs in
the 2008 answer; "late first century" in the Roman one. Either means rule 3 did
not hold.

If the 2008 answer is still wrong, the likely cause is already diagnosed and
is **not** the prompt wording. At k=6 the model receives:

```
[1] p.896  years in chunk: ['2008','2009']
[2] p.699  years in chunk: []        <- the chunk it quoted
[3] p.679  years in chunk: ['1929']
[5] p.896  years in chunk: ['2008']
```

Rule 3 tells the model to check dates; passage [2] has none. It also never sees
page numbers or titles — `format_passages()` emits `[n] text` only — so it
cannot tell [1] and [2] sit 200 pages apart in a chronological textbook. That is
the open decision in §4; do not act on it without the author.

This remains the most valuable thread in the project: a live instance of the
exact failure it exists to prevent, on the locked model, fully diagnosed.

### Step 2 — attack ranking, not k

`RETRIEVAL_K` is settled at **6** and should stay there absent new evidence
(see §1 of `CLAUDE.md` for why raising it is tuning to the test). The measured
levers, in order of cheapness:

- **Page-level dedup — 23% of slots are wasted.** At k=6, 90 slots return only
  69 distinct pages, so k=6 delivers **4.6 pages of evidence, not 6**. Dedup
  would give ~6 distinct pages from a depth of about 8. Not implemented on
  purpose: two chunks from one page can carry different content and the UI shows
  a snippet per chunk, so it changes what a source card means. **Design decision,
  needs the author.**
- **Chunking.** For the Glorious Revolution question the gold page (93–94) sits
  *behind* `us-history` 107 and 92 — retrieval lands adjacent to the right
  passage and ranks neighbours above it.
- **Reranking / hybrid search.** MRR is 0.568 and barely moves with k. That is
  the number to move.

Re-run after any change and update the tables in `CLAUDE.md` §1:

```bash
python -m cliopedia.evaluate --sweep
python -m cliopedia.evaluate -k 6
```

### Step 3 — verify the World History gold pages

Spot-check 4–5 entries in `eval/questions.txt` (the block after the
`── World History ──` comment) against the actual PDFs. Each `why:` field quotes
the page verbatim, so this is a read, not a rerun.

---

## 4. Decisions made, and why

| Decision | Why |
|---|---|
| `book:` as a **required per-entry field** in `eval/questions.txt` | A file-level default is exactly the ambiguous unit Rule 13 warns about. An inline `pages: us-history 210` form was rejected as unsafe: `world-history-1` contains a digit the page parser would swallow. |
| Fix `_folio()` rather than declare offsets in `corpus.py` | It reproduces the one known-correct answer (16) with a 76× stronger majority and needs no hand-maintained data. Per-book manual offsets remain the fallback if a future book defeats the heuristic. |
| Fix the scorer **before** expanding the corpus | Wrong-book hits inflate the score, so a reassuring post-expansion number would have been indistinguishable from a real one. |
| Establish folio offsets **before** writing World History questions | Both volumes initially came back "not established". Questions drafted first would have been written in a numbering the app could not report. |
| **`RETRIEVAL_K` stays 6** | 13 of 15 questions have identical ranks at k=6, 10 and 15. Going to 15 costs nine passages per query to fix two questions found at ranks 10 and 15. |
| Commit the index | First time it has been, despite four documents describing it as committed. `SPEC.md` §4.1 requires it — Streamlit Cloud has no database. 69 MB clears GitHub's limit. |
| Did **not** touch `requirements.txt` | An apparent `tokenizers`/`transformers` conflict was self-inflicted by `--ignore-installed` in system Python. Verified clean in a fresh venv first. |
| Left Rule 10's confidence claim alone | It says the offset of 16 was established "with a clear majority of pages agreeing"; it was 6 of 987 — a majority of *detections*. The factual correction is in the `_folio_offset` docstring. Amending a **learned rule** is the author's call. **Still open.** |
| Did **not** add page numbers to `format_passages()` | **Open decision, needs the author.** It would likely fix the merged-events failure by letting the model see that two passages sit 200 pages apart. But the omission is deliberate: withholding page numbers is what stops the model writing "p. 699" into answers instead of `[2]`, which rule 5 forbids and `citations.py` depends on. Three options were put to the author — (1) add book + page and strengthen rule 5, (2) add only the section heading (`25.2 • The Great Depression`), which gives temporal context without a citable number but needs an `ingest.py` change and a full re-embed, (3) accept rule 3 as partial mitigation. Option 2 was recommended. **Test rule 3 alone first — if it holds, none of this is needed.** |

---

## 5. Gotchas the next agent absolutely needs

**Reading the index modifies it.** After any query or eval, `git status` shows
`data/chroma/chroma.sqlite3` modified. SQLite rewrites its header on open;
content is identical (verified by hashing 9275 embedding rows and 64,925
metadata rows). Run `git checkout -- data/chroma/`. **Never commit that churn** —
69 MB of meaningless history each time. Only commit the index after a genuine
`python -m cliopedia.ingest --rebuild`. This is Rule 16 and it fired repeatedly
this session, including via the stop hook.

**The container is ephemeral.** `data/raw/` (470 MB) and `venv/` (5.8 GB) are
git-ignored and vanish in a fresh session. You do **not** need them to query —
the index is committed. You need them only to re-ingest.

**Downloads truncate; just retry.** U.S. History took three attempts, Volume 2
two, failing around 120–130 MB. `download_sources.py` detects the short read,
deletes the partial, and says to re-run. Not a size cap — Volume 1 is largest at
201 MB and came down whole. Loop until the byte count matches.

**Never run `pip install` in parallel with other work.** Doing so churned
`site-packages` mid-run, broke `_cffi_backend`, and made `download_sources.py`
silently skip its licence check. The downloads were fine; the licence evidence
was lost and had to be re-gathered.

**`download_sources.py` skips existing files**, so re-running it does not
re-verify a licence. Call `report()` / `verify_is_pdf()` directly, and pass an
**absolute** path — `report()` does `relative_to(REPO_ROOT)` and raises on a
relative one. Its progress meter also assumes a TTY: filter with
`grep -av "MB /"` or a 470 MB fetch produces a 42 KB log.

**The eval CLI reloads the embedding model per invocation.** For multi-k work,
build `HuggingFaceEmbeddings(model_name=settings.embedding_model)` once and pass
it via `evaluate(qs, k=k, embeddings=emb)`. Turns 45 minutes into a few.

**The five-vote floor in `_folio_offset()` is load-bearing.** World History
Vol 2 detected exactly one folio and voted *unanimously* for offset 404. Only
that floor rejected it. If detections are a small fraction of a book's pages,
treat the offset as suspect however unanimous the majority looks.

**Two page numberings — always name which.** `locator_value` is the PDF page,
`printed_page` the folio, `cite_page` prefers the folio and falls back to the
PDF page when `printed_page` is `-1`. Offsets are 16 / 10 / 10 so the fallback
should not trigger.

**Do not compare hit rate across books.** The World History questions were
written by a different author using distinctive proper nouns (*Çatalhöyük*,
*cartaz*, *Songhai*); the U.S. History ones are paraphrased into a student's
voice, which is harder. MRR 0.875 vs 0.568 measures question style at least as
much as retrieval. The aggregate row also rose 86.7% → 93.3% purely because
easier items joined the set. **Track per-book rows over time.**

**The author develops on Windows.** Never hand over a bare `source` line.
PowerShell blocks `Activate.ps1` under the default execution policy; the
friction-free path is calling the venv executable directly
(`.\venv\Scripts\streamlit.exe run app.py`). This is documented in the README's
new "Running it day to day" section.

**`.env` drifts silently.** The author's local `.env` was running
`RETRIEVAL_K=4` and `llama3.2:3b` — both stale, and k=4 is now the *worst* point
on the curve (60.0%). `.env.example` is correct. `python -m cliopedia.config` is
the first thing to run when behaviour surprises you.

**Branching.** `CLAUDE.md` §5: `main` is the trunk, no feature branches. When a
harness forces one, open a PR into `main` and **merge it before the session
ends**. A merged PR cannot be reused — start a fresh branch from `origin/main`
for follow-up work. **Watch for stranded commits**: resetting a branch to
`origin/main` mid-session left the index commit behind on another branch this
session, and `main` briefly carried the measurements without the index that
produced them. Verify with `git ls-files`, not the log.

**Commit messages: no backticks** inside a double-quoted `-m` string — bash runs
command substitution and eats the word (Rule 5). Use `git commit -F` and read
back with `git log -1 --format=%B`.

**`SPEC.md` is read-only.** It still says CC BY 4.0 and `k = 4`; both are
superseded. Corrections live in `CLAUDE.md` §8.
