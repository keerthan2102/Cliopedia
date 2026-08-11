# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention (README §Project documents; commits `1f06fc7` and
`772dd1e` removed earlier ones after pickup).

Written 2026-08-10. `main` is at **`b59354c`**. Working tree clean.
145 tests pass. 31 eval questions. Index 85 MB, 9275 chunks.

Read `CLAUDE.md` first — it is the working agreement and overrides anything
here. This file carries only what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

Seventeen commits, PRs #3–#18, all merged to `main`.

**The corpus expansion, end to end.** 1 book → 3, 3775 → 9275 chunks. All three
licences read off the PDFs themselves (CC BY-NC-SA 4.0). Folio offsets 16/10/10.
Index committed for the first time despite four documents already describing it
as committed.

**Two measurement bugs**, both found by *preparing* the expansion, not running
it:
- Book-blind scoring — `evaluate()` matched bare page numbers, so a World
  History p.210 would have scored a hit at rank 1 for a U.S. History question
  (→ Rule 15).
- `_folio()` detected 6 folios in 987 pages and reported success; OpenStax
  prints them in a running footer. Fixed → 472. Both World History volumes went
  from *no offset* to 10.

**Retrieval measured and tuned by evidence:**
- Expansion cost real accuracy: at k=6, hit rate 100% → 86.7%; MRR fell at every
  k. Recorded, not hidden.
- `RETRIEVAL_K` settled at **6** — 13 of 15 questions have identical ranks at
  k=6/10/15, so raising it is tuning to the test.
- Chapter filtering **measured and rejected** (fixes one question, breaks four).
- Cross-encoder reranking **measured and adopted behind a flag**: MRR
  0.699 → **0.883**, hit rate 93.5% → 100%. Largest gain in the project.

**Answer key verified.** 31 questions covering all three books; the author
spot-checked five World History entries against the rendered PDFs, confirming
the offset of 10 on real pages.

---

## 2. Current state

### Works

- 145 tests, both `pytest` and `python -m pytest`.
- Index committed and live: 9275 chunks, 85 MB, `chroma.sqlite3` 69.5 MB (over
  GitHub's 50 MB advisory, well under the 100 MB hard limit).
- `eval/questions.txt`: 31 questions — 16 us-history, 8 world-history-1,
  7 world-history-2. Five World History entries human-verified.
- Reranking works end to end, off by default (`RERANK=on` to enable).
- The author runs the app on Windows against the committed index.

### THE OPEN BUG — two distinct failures, one apparently fixed, one not

Test case, on the author's machine (needs Ollama):

```bash
python -m cliopedia.ask "What happened during the 2008 financial crisis?" --snippets
```

**(a) Era-merging — appears fixed, NOT measured.** Retrieval returns passages
about both the 2008 crisis (ch.32) and the 1929 crash (ch.25), and the model
used to weave them into one account of 2008 — "a massive stock sell-off in late
October", a 40 percent fall, bank runs. All cited, all false by 79 years.

Three attempts, in order:
1. `ebd5d48` — prompt rule 3 ("never combine details from separate events").
   **Failed.** The chunk it quoted contains no dates, so there was nothing to
   check against.
2. `395f468` — chapter labels in `format_passages()`, so each passage arrives as
   `(from OpenStax U.S. History, chapter 25 Brother, Can You Spare a Dime? The
   Great Depression, 1929-1932)`. **Partial** — worst fabrication gone, two
   claims still misattributed.
3. `54c1c24` — reranking. **Latest run was clean**: every citation a 2008 page,
   two 1929 passages present at ranks 4–5 and ignored.

**Do not record this as fixed.** The run before it, on identical code and
config, contained an error. LLM output is stochastic and this session repeatedly
drew conclusions from single samples — twice wrongly. One clean run is not a
measurement.

**(b) Claim-support — confirmed twice, NOT addressed.** The model cites a
passage for a claim that passage does not contain:
- `[3]` cited for "the integral role of automobiles" — that snippet never
  mentions automobiles.
- `[1]` (p.896) cited for "widespread resentment towards the expensive federal
  bailout" — the word "resentment" does not appear on p.896.

Both are *plausible and probably elsewhere in the book*, attached to the wrong
passage. Reranking cannot help. For a project whose thesis is that the citation
is the product, this is arguably the more serious failure: the reader expands
the source card to check, and the sentence is not there.

### Also open

- **Rule 6 violation observed once**: an answer began "Note: Passages 1-6 all
  describe financial crises…". The reasoning was right but the prompt forbids
  mentioning "the passages" — write as though explaining the history itself.
- **P1 (Streamlit UI)** has no completed human sign-off against its exit
  criterion (a stranger can use it unaided and verify any claim).
- **Page-level dedup** — 23% of retrieval slots are duplicate pages, so k=6
  delivers **4.6 distinct pages, not 6**. Not implemented: two chunks from one
  page can carry different content and the UI shows a snippet per chunk, so it
  changes what a source card means. **Needs the author.**
- **Rule 10's confidence claim** still says the offset of 16 was established
  "with a clear majority of pages agreeing". It was 6 of 987 — a majority of
  *detections*. The factual correction is in the `_folio_offset` docstring;
  amending a learned rule was left to the author.
- **`download_sources.py --book X`** prints "1 of 3 registered book(s) present"
  regardless of how many are actually there. Confirmed with 2 present. Cosmetic,
  untouched.
- **Ten World History gold pages** are still verified only by the `pypdf`
  extraction they were written from.

---

## 3. Exact next steps

### Step 1 — turn the grounding bug into a number (highest value)

Everything about (a) rests on single samples. Write a script that runs the same
question N times and counts failures, then run it with `RERANK` on and off:

- **Era-merging signature**: any citation resolving to a `us-history` page in
  chapter 25 (printed 679, 680, 699 are the known ones), or the strings "late
  October", "40 percent", "bank run" presented as 2008.
- **Claim-support signature**: for each `[n]` in the answer, check the sentence's
  distinctive nouns appear in `passages[n-1].text`.

`cliopedia.generate` exposes `answer()`; `cliopedia.retrieve.retrieve()` gives
the passages; `cliopedia.citations.cited_numbers()` parses the markers. Ten runs
per configuration is enough to tell 0/10 from 6/10.

**This must run on the author's machine — the remote container has no Ollama.**

### Step 2 — then fix claim-support

Only after step 1 gives a baseline. A prompt rule requiring the model to confirm
a claim appears in passage *n* before writing `[n]`. `cliopedia/prompts.py`,
after rule 3. Re-measure with the same script; do not ship on reasoning alone.

### Step 3 — decide the deployed `RERANK` default

Currently off, for deployment reasons only (`SPEC.md` §2.2 — Streamlit
Community Cloud memory limits unverified for even the first model). The quality
case is settled. This belongs to P3 when deployment is actually exercised.

---

## 4. Decisions made, and why

| Decision | Why |
|---|---|
| `book:` required per entry in `eval/questions.txt` | A file-level default is the ambiguous unit Rule 13 warns about. Inline `pages: us-history 210` was rejected as unsafe — `world-history-1` contains a digit the page parser would swallow. |
| Fix `_folio()` rather than hardcode offsets in `corpus.py` | Reproduces the known-correct 16 with a 76× stronger majority and works for future books. |
| Fix the scorer **before** expanding the corpus | Wrong-book hits inflate the score, so a reassuring number would have been indistinguishable from a real one. |
| `RETRIEVAL_K` stays 6 | 13 of 15 questions rank identically at k=6/10/15. Going to 15 costs nine passages per query to fix two questions found at ranks 10 and 15. |
| Chapter filtering **rejected** | Measured: fixes one question, breaks four. When rank 1 is in the wrong chapter, anchoring on it entrenches the error. The majority-anchored variant is worse — in the 2008 case the majority chapter is the *wrong* era. |
| Reranking adopted **behind a flag, default off** | Quality case is overwhelming (MRR 0.699 → 0.883). Default is a deployment decision: it loads a second model and `SPEC.md` §2.2 flags Cloud memory as unverified. No new pip dependency — `CrossEncoder` ships in `sentence-transformers`. |
| Chapter labels carry **no page number** | Rule 5 forbids the model citing pages; `citations.py` depends on passage indices. Pinned by `test_the_heading_label_carries_no_page_number`. |
| Index committed | `SPEC.md` §4.1 requires it — Streamlit Cloud has no database. 69.5 MB clears GitHub's hard limit. |
| `requirements.txt` untouched | An apparent `tokenizers`/`transformers` conflict was self-inflicted by `--ignore-installed` in system Python. Verified clean in a fresh venv. |

---

## 5. Gotchas the next agent absolutely needs

**No Ollama in the remote container.** Retrieval, ingest, eval and tests all run
there; **generation does not**. Two prompt fixes shipped this session on
reasoning alone and the first was simply wrong. **Never claim a prompt change
works without a model run** — ask the author.

**LLM output is stochastic.** Two runs on identical code and config gave
different answers, one with an error and one clean. Single generations are weak
evidence in *both* directions. Count over repeats.

**Reading the index modifies it.** After any query or eval, `git status` shows
`data/chroma/chroma.sqlite3` modified — SQLite rewrites its header on open;
content is identical. `git checkout -- data/chroma/`. **Never commit that
churn** (69 MB per time). Only commit after a genuine `ingest --rebuild`.
Rule 16; it fired repeatedly, including via a stop hook.

**A rebuild renames the collection UUID directory**, so `git pull` aborts on
untracked files for anyone with a local index. Tell the author:
`Move-Item data\chroma data\chroma.old` first.

**Never commit mid-rebuild** — `--rebuild` deletes the index before
re-embedding.

**The container is ephemeral.** `data/raw/` (470 MB) and `venv/` (5.8 GB) are
git-ignored and vanish. You do **not** need them to query — the index is
committed. Only to re-ingest or to read source pages.

**Downloads truncate around 120–130 MB; just retry.** Not a size cap — Volume 1
is largest at 201 MB and comes whole. The script deletes partials.

**Never run `pip install` alongside other work.** It churned `site-packages`
mid-run, broke `_cffi_backend`, and made `download_sources.py` silently skip its
licence check.

**The eval CLI reloads the embedding model per invocation.** For multi-k work
build `HuggingFaceEmbeddings(model_name=settings.embedding_model)` once and pass
it via `evaluate(qs, k=k, embeddings=emb)`. Minutes instead of an hour.

**Do not compare hit rate across books.** The World History questions lean on
distinctive proper nouns; the U.S. History ones are paraphrased into a student's
voice. MRR 0.875 vs 0.568 measures question style as much as retrieval. The
aggregate also rose 86.7% → 93.3% purely because easier items joined the set.

**With `RERANK=on` the similarity column does not descend.** Those are embedding
scores; the *order* comes from the cross-encoder, a different scale. The CLI
says so — don't "fix" it.

**`_heading()` covers 89–91% of pages** and returns `None` for the rest rather
than guessing. Its line ordering is load-bearing: the openstax boilerplate
occupies the last line on many pages, and stripping a leading number before
matching eats the chapter number when the folio is printed last (that held
coverage at 37%).

**The five-vote floor in `_folio_offset()` is load-bearing.** World History Vol 2
detected one folio and voted *unanimously* for offset 404.

**Two page numberings — always name which.** `locator_value` is the PDF page,
`printed_page` the folio, `cite_page` prefers the folio.

**The author develops on Windows.** Never hand over a bare `source` line.
PowerShell blocks `Activate.ps1` by default. Friction-free path:
`.\venv\Scripts\python.exe -m ...`. An env var must be set on the **same line**:
`$env:RERANK="on"; .\venv\Scripts\python.exe -m cliopedia.ask "..."` — a
separate `$env:` in another window will not reach the process. This cost a
whole round trip; `python -m cliopedia.config` shows whether it took.

**`.env` drifts silently.** The author's had `RETRIEVAL_K=4` and `llama3.2:3b`,
both stale, and k=4 is the *worst* point on the curve. `.env.example` is
correct.

**Branching.** `main` is the trunk; no feature branches. When a harness forces
one, PR into `main` and **merge before the session ends**. Watch for stranded
commits — a branch reset to `origin/main` left the index commit behind this
session, and `main` briefly carried the measurements without the index that
produced them. Verify with `git ls-files`, not the log. Branch deletion is
**HTTP 403** from this environment; ask the author.

**Commit messages: no backticks** in a double-quoted `-m` string (Rule 5). Use
`git commit -F`, read back with `git log -1 --format=%B`.

**`SPEC.md` is read-only.** It still says CC BY 4.0 and `k = 4`; both
superseded. Corrections live in `CLAUDE.md` §8.
