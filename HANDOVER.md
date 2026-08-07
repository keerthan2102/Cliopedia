# HANDOVER.md

Relay baton for the next session. **Read this, act on it, then delete it** —
that is the convention this file follows (see README §Project documents, and
commit `1f06fc7`, which removed the last one after pickup).

Written 2026-08-07. `main` is at **`b9f8d0e`**. Working tree clean.

Read `CLAUDE.md` first — it is the working agreement and it overrides anything
here. This file only carries what `CLAUDE.md` cannot know yet.

---

## 1. What this session accomplished

Two bugs fixed, both in the measurement layer, both found by preparing the
corpus expansion rather than by running it. Both merged to `main`.

### PR #3 — `f8a5ccb` — retrieval scoring was book-blind

`evaluate()` retrieved `Retrieved` objects that each know their `source_title`,
then discarded it and scored bare page numbers. Correct only while the corpus
held one book. Every volume has a page 210, so once the World History volumes
are ingested, a World History page 210 returned for a U.S. History question
would have scored a **hit at rank 1**.

Confirmed against the old scorer rather than assumed:

| retrieved | old rank | new rank |
|---|---|---|
| World History 210, 211 only | 1 (hit) | miss |
| World History 210 ahead of U.S. History 210 | 1 | 2 |

Fixed: `score()` takes `(source_title, printed_page)` pairs, both must match.
`eval/questions.txt` gained a **required `book:` field** holding a corpus key,
validated against `cliopedia/corpus.py` at load time. `Result` carries the book
into `_report`, so a miss now prints which book retrieval went to instead.
Recorded as **CLAUDE.md §8 Rule 15**.

### PR #4 — `16b292b` — `_folio()` could not see OpenStax's folios

`_folio()` required a line to be *entirely* digits. OpenStax prints the folio at
the end of a running footer: `9.3 • The Kingdom of Kush     391`. So detection
was near-total failure that looked like success.

| book | before | after | offset |
|---|---|---|---|
| us-history | 6/987 detected | 472/987 | **16** (unchanged) |
| world-history-1 | 0/791 → None | 390/791 | **10** |
| world-history-2 | 1/723 → voted 404, rejected | 356/723 | **10** |

Validated on the corpus, not fixtures: **600 of 600 sampled pages** (200 per
book) have PDF index minus offset equal to the folio typeset on that page. The
new matcher independently reproduces U.S. History's known-correct 16.

New `tests/test_folio.py` (16 tests), built from footer strings copied verbatim
out of the PDFs. Suite is at **128 passing**.

---

## 2. Current state

### Works, verified this session

- **Full test suite: 128 passing**, under both `pytest` and `python -m pytest`.
- **`requirements.txt` is fine.** Installs and imports cleanly in a fresh venv:
  `transformers 5.14.1 / tokenizers 0.22.2`. (An earlier apparent conflict was
  caused by this session polluting system Python with `--ignore-installed`; it
  was **not** a repo bug. Do not "fix" `requirements.txt`.)
- **All three PDFs fetch and verify.** Structural check (`%PDF-` + `%%EOF` +
  exact byte count) and licence read off each PDF's own front matter:

  | book | bytes | pages | licence |
  |---|---|---|---|
  | us-history | 136,400,038 | 987 | CC BY-NC-SA 4.0 ✅ |
  | world-history-1 | 201,039,307 | 791 | CC BY-NC-SA 4.0 ✅ |
  | world-history-2 | 132,663,448 | 723 | CC BY-NC-SA 4.0 ✅ |

- **Folio offsets established for all three books**: 16, 10, 10.

### Half-done / not started

- **The index has never been built with three books.** `data/chroma/` does not
  exist. This is the next step (§3).
- **`eval/questions.txt` still holds only the 15 U.S. History questions.** No
  World History questions exist yet. All 15 now carry `book: us-history`.
- **The recorded baseline in `CLAUDE.md` §1 is still the single-book number**
  (100% @ k=6, MRR 0.680). It is *still valid* — both fixes are no-ops for the
  one-book case — but it will need re-measuring and updating after ingest.

### Broken / open

- **`data/chroma/` has NEVER been committed**, though `SPEC.md` §4.1, the
  README licence table, `CLAUDE.md` §5 and `.gitignore`'s own comment all state
  it is a committed build artifact that the P3 deployment plan depends on.
  `git log --all -- 'data/chroma*'` is empty. **This needs a decision before
  deploy** — see §5.
- **P1 (Streamlit UI) has still never been used by a human.** That is P1's own
  exit criterion and it remains unmet. Needs Ollama, so it needs the author's
  machine.
- **A stale remote branch may exist**: `claude/project-overview-qlfp0c`. This
  environment gets **HTTP 403 from the proxy on branch deletion** — it is a
  policy denial, not a transient failure, so do not burn retries on it. Ask the
  author to delete it on GitHub.

---

## 3. Exact next steps

### Step 1 — build the three-book index

```bash
python -m cliopedia.ingest --rebuild
```

`--rebuild` is required: an existing index built from one book must not be
appended to. Watch the output for the **folio offset per book** — it must print
16, 10, 10. Anything else means something regressed in `cliopedia/ingest.py`.

Then record two numbers the author needs:

```bash
du -sh data/chroma/
find data/chroma -size +50M -exec ls -lh {} \;   # any file near GitHub's 100MB cap
```

### Step 2 — measure interference against the existing 15 questions

```bash
python -m cliopedia.evaluate --sweep
python -m cliopedia.evaluate -k 6
```

This measures **interference**: does adding ~1,500 pages of world history push
the right U.S. History page out of the top 6? It needs **no new questions**, and
it is the genuine before/after that `CLAUDE.md` §1 is set up for. The `before`
is 100% hit rate / 0.680 MRR at k=6.

**A drop is the expected, interesting result — not a failure.** `CLAUDE.md` §1
says so explicitly: "expanding to three books should push it down, and that
movement is the measurement worth having."

Re-run the k sweep and, if the plateau moved, follow **Rule 14**: find the
bracket with the coarse grid, then measure the integers inside it with `-k`.
`RETRIEVAL_K` is currently **6** (`cliopedia/config.py:134`).

Then update the baseline table in `CLAUDE.md` §1 ("Retrieval baseline") with the
new numbers and note that the corpus is now three books.

### Step 3 — World History eval questions

`eval/questions.txt`, following the format documented in its own header. Each
entry needs `ask:` / `book:` / `pages:` / `why:`.

- `book:` must be `world-history-1` or `world-history-2` — validated against
  `cliopedia/corpus.py`, unknown keys are refused.
- `pages:` are **printed folios**, not PDF pages. Offset is **10** for both
  volumes, so PDF page 121 is printed page 111.
- Read the trap section in the file's header: do **not** write questions by
  running retrieval and recording what comes back. Open the PDF at a page, read
  it, write a question that page answers.
- The author should spot-check a sample — the question set's whole value is that
  a human verified it (Rule 13).

### Blocked on the author's machine (needs Ollama)

- `python -m cliopedia.ask "..."` — the LLM answer path
- `streamlit run app.py` — the P1 UI, and P1's unmet exit criterion

The **retrieval eval needs no LLM**, so steps 1–2 run fine in a container.

---

## 4. Decisions made, and why

| Decision | Why |
|---|---|
| `book:` as a **required per-entry field**, not a file-level default | A default hundreds of lines above an entry is exactly the ambiguous unit Rule 13 warns about. Chosen over an inline `pages: us-history 210` form, which is actively unsafe: `world-history-1` contains a digit that the page parser would swallow. |
| Fix `_folio()` rather than declare offsets in `corpus.py` | It reproduces the one known-correct answer (16) with a 76× stronger majority, works for future books, and needs no hand-maintained data. A per-book manual offset was the alternative and is still a reasonable fallback if a future book defeats the heuristic. |
| Fix the scorer **before** expanding the corpus | Otherwise the post-expansion number would be unauditable — wrong-book hits inflate it, so a reassuring result would be indistinguishable from a real one. |
| Establish folio offsets **before** writing World History questions | Both volumes came back "not established". Had questions been drafted first, all 15 would have been written in a numbering the app could not report, and the eval would have shown catastrophic retrieval failure that was really a units bug. |
| Left `CLAUDE.md` Rule 10's confidence claim alone | It says the offset of 16 was established "with a clear majority of pages agreeing". It was 6 of 987 — a majority of *detections*. The correction is in the `_folio_offset` docstring; amending a **learned rule** is the author's call. |
| Did not touch `requirements.txt` | The apparent conflict was self-inflicted (see §2). Verified clean in a fresh venv before concluding. |

---

## 5. Gotchas the next agent absolutely needs

**The container is ephemeral.** `data/raw/` (470 MB) and `venv/` (5.8 GB) are
both git-ignored and **will be gone** in a fresh session. Rebuild with
`python -m venv venv && ./venv/bin/pip install -r requirements.txt` and
`python scripts/download_sources.py`. Budget for it — the venv install pulls
PyTorch.

**Downloads truncate. Retry.** U.S. History needed three attempts, Volume 2 two,
all failing around 120–130 MB. `download_sources.py` correctly detects the short
read, deletes the partial, and says to re-run — a truncated file is never kept.
Just loop until the byte count matches. It is not a size cap: Volume 1 is the
largest at 201 MB and came down whole.

**Do not run `pip install` in parallel with anything else.** This session did,
and it churned `site-packages` mid-run, breaking `_cffi_backend` so `pypdf`
failed to import and `download_sources.py` **silently skipped its licence
check**. The download itself is unaffected (the byte/`%%EOF` checks are pure
Python), but the licence evidence was lost and had to be re-gathered. Work in
the venv, sequentially.

**`download_sources.py` skips files that already exist.** Re-running it will
*not* re-verify a licence. To check a PDF already on disk, call
`report()` / `verify_is_pdf()` directly, and pass an **absolute** path —
`report()` does `path.relative_to(REPO_ROOT)` and raises `ValueError` on a
relative one.

**Its progress meter assumes a TTY.** Piped to a file it emits one line per
0.1 MB; a 470 MB fetch produced a 42 KB log. Filter with `grep -av "MB /"`.

**Two page numberings, always name which.** `locator_value` is the PDF page;
`printed_page` is the folio; `cite_page` prefers the folio and **falls back to
the PDF page** when `printed_page` is `-1`. Offsets are now 16 / 10 / 10, so the
fallback should not trigger — but if a future book's offset fails to establish,
that book's pages come back in PDF units while `questions.txt` is in printed
units and every question for it MISSes. Loud, therefore safe, but check ingest's
output.

**The five-vote floor in `_folio_offset()` is load-bearing.** World History Vol 2
detected exactly one folio and voted *unanimously* for an offset of 404. Only
that floor rejected it. If detections are ever a small fraction of a book's
pages, treat the offset as suspect even when the majority looks unanimous.

**`load_pages()` drops image-only pages.** 987 PDF pages → 985 Documents for
U.S. History. Expected; `page_index` is still the true PDF page because the
enumerate runs before the filter.

**Committing the index has a licence consequence.** `data/chroma/` embeds
verbatim textbook passages, so it ships under **CC BY-NC-SA 4.0**, not the
repo's MIT `LICENSE`. Never relicense it, and never make the deployed demo
commercial. Also check the sqlite file against GitHub's 100 MB per-file hard
limit before committing — if it exceeds that, the P3 deploy plan needs
rethinking, not just a bigger commit.

**Branching.** `CLAUDE.md` §5 says `main` is the trunk and all work lands there.
The author confirmed this session: commit to `main`, no feature branches. When a
harness forces a branch, open a PR into `main` and **merge it before the session
ends** — never leave work stranded. Both PRs this session (#3, #4) were merged
that way. Note that a merged PR cannot be reused: start a fresh branch from
`origin/main` for follow-up work.

**Commit messages: no backticks** inside a double-quoted `-m` string — bash runs
command substitution and silently eats the word (Rule 5). Use `git commit -F`.
Read the message back with `git log -1 --format=%B`.

**`SPEC.md` is read-only.** It still says CC BY 4.0 and `k = 4`; both are
superseded. Corrections live in `CLAUDE.md` §8, not in `SPEC.md`.
