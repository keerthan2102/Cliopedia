"""Measure retrieval, rather than trusting it.

Everything else in this project can be judged by reading the screen. Retrieval
cannot: it hands the model four passages, and if they are the wrong four the
answer still reads well and still cites pages — it just cites pages that do not
support the claim. The only way to know is to ask questions whose correct page
is known independently, and count.

The metric is **hit rate at k**: for each question, did any page we know to
contain the answer appear among the k retrieved passages? Plus **MRR** (mean
reciprocal rank), which rewards putting the right page first rather than fourth
— worth tracking separately, because a right answer buried at rank 4 competes
for prompt space with three irrelevant ones.

    python -m cliopedia.evaluate
    python -m cliopedia.evaluate --sweep        # hit rate at k = 1,2,4,8,16

The question set lives in eval/questions.txt, hand-written and version
controlled. Scoring lives here, in the package, so it can be imported and
tested without a corpus.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from cliopedia.config import REPO_ROOT, settings

QUESTIONS_FILE = REPO_ROOT / "eval" / "questions.txt"

# A line starts a new field only if it opens with one of these. Anything else
# continues the field above it, which is what lets `why` hold pasted prose —
# quotation marks, apostrophes, wrapped lines — with no escaping rules at all.
# The first format here was TOML, and it broke twice on exactly that: a
# sentence copied out of the PDF. A file written by hand should not fail
# because someone typed a quotation mark.
_FIELD = re.compile(r"^(ask|pages|why)\s*:\s*(.*)$", re.IGNORECASE)

# The values of k to try in a sweep. Spans "only the best passage" to "far more
# than a prompt should carry", so the curve shows where extra passages stop
# adding recall and start adding noise.
#
# 6 is in the grid because the original doubling sequence stepped straight over
# it. That sweep reached 100% at k=8 and stayed there, which reads as "8 is
# where recall tops out" — but 6 already reached 100%, and 8 was simply the
# first measured point past it. A doubling grid can only ever locate the answer
# to within a factor of two; when a plateau is what you are looking for, the
# first k on the plateau is the one worth knowing, so it has to be measured.
SWEEP_K = (1, 2, 4, 6, 8, 16)


class EvalError(RuntimeError):
    """Raised when the question set is missing or malformed."""


@dataclass(frozen=True)
class Question:
    """One question with the pages known to answer it.

    `pages` are **printed** page numbers — the folio a reader sees — because
    that is what a person writing the question set reads off the page. It is
    also what `Retrieved.cite_page` reports, so the two are directly comparable.
    """

    ask: str
    pages: tuple[int, ...]
    why: str = ""


@dataclass(frozen=True)
class Result:
    """How retrieval did on one question."""

    question: Question
    retrieved_pages: tuple[int, ...]
    rank: int | None  # 1-based rank of the first correct page, None if missed

    @property
    def hit(self) -> bool:
        return self.rank is not None

    @property
    def reciprocal_rank(self) -> float:
        return 0.0 if self.rank is None else 1.0 / self.rank


def load_questions(path: Path = QUESTIONS_FILE) -> list[Question]:
    """Read the hand-written question set.

    A deliberately plain line format rather than TOML, JSON or YAML. This file
    is typed and edited by a person, and its `why` field holds sentences copied
    straight out of a PDF — full of quotation marks, apostrophes and line
    wraps. Every structured format has escaping rules that such text violates,
    and TOML did: the first two attempts at writing this set failed to parse on
    a pasted sentence.

    So there are no quoting rules. `ask:`, `pages:` and `why:` start a field,
    anything else continues the one above, a blank line ends an entry. Twenty
    lines of parser buys a file that cannot be broken by typing in it.
    """
    if not path.exists():
        raise EvalError(
            f"No question set at {path}.\n"
            "It is hand-written: each entry is a question plus the pages known\n"
            "to answer it. See the file's own comments for the format."
        )

    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    field: str | None = None

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            if current:
                entries.append(current)
            current, field = {}, None
            continue
        if line.lstrip().startswith("#"):
            continue

        match = _FIELD.match(line.strip())
        if match:
            field = match.group(1).lower()
            current[field] = match.group(2).strip()
        elif field:
            current[field] = f"{current[field]} {line.strip()}".strip()
        else:
            raise EvalError(
                f"{path} line {number}: expected 'ask:', 'pages:' or 'why:'\n"
                f"  {line.strip()[:70]}\n"
                "A continuation line must follow one of those; a blank line ends\n"
                "an entry."
            )

    if current:
        entries.append(current)

    if not entries:
        raise EvalError(f"{path} contains no questions.")

    questions = []
    for index, entry in enumerate(entries, start=1):
        ask = entry.get("ask", "").strip()
        if not ask:
            raise EvalError(f"Entry {index} has no 'ask:' line.")

        raw_pages = entry.get("pages", "")
        numbers = re.findall(r"\d+", raw_pages)
        if not numbers:
            raise EvalError(
                f"Entry {index} ({ask[:50]!r}) lists no pages.\n"
                "Every question needs at least one page known to answer it —\n"
                "without one it scores zero and looks like a retrieval failure."
            )

        questions.append(
            Question(
                ask=ask,
                pages=tuple(int(n) for n in numbers),
                why=entry.get("why", "").strip(),
            )
        )
    return questions


def score(question: Question, retrieved_pages: Sequence[int]) -> Result:
    """Rank of the first retrieved page known to answer the question.

    Deliberately generous about *which* correct page is found: an answer often
    spans a page boundary, so finding either counts. Deliberately strict about
    rank — position matters, and averaging that in is what MRR is for.
    """
    rank = None
    for position, page in enumerate(retrieved_pages, start=1):
        if page in question.pages:
            rank = position
            break
    return Result(question=question, retrieved_pages=tuple(retrieved_pages), rank=rank)


def hit_rate(results: Sequence[Result]) -> float:
    """Fraction of questions where a correct page was retrieved at all."""
    return sum(r.hit for r in results) / len(results) if results else 0.0


def mean_reciprocal_rank(results: Sequence[Result]) -> float:
    """Average of 1/rank — rewards ranking the right page first, not merely at all."""
    return sum(r.reciprocal_rank for r in results) / len(results) if results else 0.0


def evaluate(questions: Sequence[Question], k: int, embeddings=None) -> list[Result]:
    """Run every question through retrieval at a given k."""
    from cliopedia.retrieve import retrieve

    results = []
    for question in questions:
        hits = retrieve(question.ask, k=k, embeddings=embeddings)
        results.append(score(question, [hit.cite_page for hit in hits]))
    return results


def _report(results: Sequence[Result], k: int) -> None:
    print(f"\nRetrieval at k={k}, over {len(results)} questions")
    print("─" * 78)
    for result in results:
        mark = f"rank {result.rank}" if result.hit else "MISS"
        print(f"  {mark:<8} {result.question.ask[:52]:<54}")
        if not result.hit:
            print(f"           expected {list(result.question.pages)}, "
                  f"got {list(result.retrieved_pages)}")
    print("─" * 78)
    print(f"  hit rate @{k}          {hit_rate(results):.1%}")
    print(f"  mean reciprocal rank  {mean_reciprocal_rank(results):.3f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-k", type=int, default=None, help="passages to retrieve")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help=f"report hit rate at k = {', '.join(str(k) for k in SWEEP_K)}",
    )
    args = parser.parse_args()

    try:
        questions = load_questions()
    except EvalError as exc:
        print(f"\n{exc}")
        return 1

    from cliopedia.retrieve import RetrievalError

    try:
        if args.sweep:
            print(f"\nSweeping k over {len(questions)} questions "
                  f"(RETRIEVAL_K is currently {settings.retrieval_k})")
            print("\n    k   hit rate     MRR")
            print("  " + "─" * 26)
            for k in SWEEP_K:
                results = evaluate(questions, k=k)
                print(f"  {k:>3}   {hit_rate(results):>7.1%}   {mean_reciprocal_rank(results):>6.3f}")
            print("\nA hit rate that stops climbing means extra passages are adding")
            print("noise, not recall. That is the number to tune k against.")
        else:
            k = args.k or settings.retrieval_k
            _report(evaluate(questions, k=k), k=k)
    except RetrievalError as exc:
        print(f"\n{exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
