# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention (README §Project documents; commit `1f06fc7` removed an
earlier one after pickup, and this file replaces one deleted the same way).

Written 2026-08-10. `main` is at **`dd8a889`**. Working tree clean.

Read `CLAUDE.md` first — it is the working agreement and overrides anything
here. This file carries only what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

The corpus expansion, end to end: one book → three, with the measurement to
show what it cost. Eight commits, all merged to `main` via PRs #3–#10.

| commit | what |
|---|---|
| `f8a5ccb` | fix: score retrieval on book and page, not page alone |
| `16b292b` | fix: read the folio off a running footer, not only a bare line |
| `091e2ab` | feat: rebuild the index over all three books |
| `b4080e5` | docs: record the three-book retrieval baseline |
| `4372209` | docs: settle RETRIEVAL_K at 6, record where the real waste is |
| `4d9fba6` | test: cover World History in the question set |
| `ecb87ee` | docs: add a day-to-day run section to the README |

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

- **128 tests pass**, under both `pytest` and `python -m pytest`.
- **Index committed and live**: 9275 chunks, 84 MB, `chroma.sqlite3` 69 MB
  (clears GitHub's 100 MB per-file limit). Folio offsets 16 / 10 / 10.
- **All three licences read off the PDFs themselves**: CC BY-NC-SA 4.0.
- **`eval/questions.txt` is 30 questions**: 15 us-history, 8 world-history-1,
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

- **A real hallucination is on record and unfixed.** Asked "Tell me about the
  Roman conquest of Britain", the app produced a cited answer containing:
  *"unlike in Gaul, the Romans did not have a permanent presence in Britain
  until the late first century CE."* World History Vol 1 p.297 dates it to
  **43 CE**; the phrase "late first century" appears nowhere, and the page's
  "Unlike the case in Gaul" attaches to centuriation and roads being direct
  control, not to the permanent presence. Everything else in that answer checked
  out against pp.297 and 423. **The author reports this was produced on
  `llama3.1:8b`, not the smaller model — so it is not a small-model artifact and
  points at `cliopedia/prompts.py`.** Reproduce before changing anything.
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

### Step 1 — reproduce the grounding failure (highest value)

```bash
python -m cliopedia.ask "Tell me about the Roman conquest of Britain?" --snippets
```

Check whether the "late first century CE" claim recurs. If it does, the fix
belongs in `cliopedia/prompts.py` — the grounding instruction is not holding the
model to the passage. Read the current prompt before editing; §4.4 of
`CLAUDE.md` is the governing rule (never let the model fall back on memory).

This is the most valuable open thread: it is a live instance of the exact
failure the project exists to prevent, on the locked model, with the evidence
already gathered.

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
