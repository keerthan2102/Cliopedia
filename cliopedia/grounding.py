"""Sample answers repeatedly and lay out what each one cites, for human review.

`evaluate.py` measures the *search* half of this system: did the right page come
back? This helps with the *answer* half: given those passages, did the model say
things they actually say. Those are different failures and only one is visible
in a hit rate — this app has produced a fully cited answer describing "a massive
stock sell-off in late October" and a 40 percent fall, which is Black Tuesday
1929, for a question about 2008. Retrieval scored a hit at rank 1. The answer
was wrong by 79 years.

**This is a review aid, not a metric, and the distinction is the whole point.**

An automatic support score was tried first and rejected on measurement. Scoring
each cited sentence by how much of its vocabulary appears in the passage it
cites catches only **one of the three real failures** collected so far:

    "the integral role of automobiles [3]"      0% support   caught
    "widespread resentment ... bailout [1]"     71% support   MISSED
    "limited savings ... luxury cars [4]"       67% support   MISSED

Two reasons, both fatal. Averaging dilutes a fabrication: in the second case
"resentment" is the entire false claim, but "federal", "bailout" and "banks" are
all genuinely on the page, so one invented word drowns in several real ones. And
in the third the passage really does contain "savings", "luxury" and "cars" —
the error is that they are 1929 material framed as 2008, and vocabulary overlap
cannot see framing.

Publishing a score that misses two failures in three would be worse than
publishing nothing: it would read as reassurance. `CLAUDE.md` §8 Rule 13 is
about exactly this — a measurement believed more than it deserves does more
damage than no measurement at all.

So this module counts nothing and judges nothing. It removes the tedium instead:
run the same question N times, and for each answer print what it cited, which
chapter each cited passage came from, which distinctive words of a sentence are
absent from the passage it points at, and which factual sentences carry no
citation. A person still decides. The support percentages are printed as hints
and labelled as hints.

**Sample, never take one run as an answer.** Generation is stochastic. Two runs
of the identical question on identical code have produced one answer with a
false claim and one clean. That is why this exists at all.

**Needs a language model**, so it does not run where there is none.

    python -m cliopedia.grounding "What happened during the 2008 financial crisis?"
    python -m cliopedia.grounding "..." --runs 10
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Sequence

from cliopedia.citations import _MARKER
from cliopedia.retrieve import Retrieved

# Words too common to indicate that a claim came from a passage. Deliberately
# short: this is not linguistics, it is a filter to stop "the" and "during"
# counting as evidence of support.
_STOPWORDS = frozenset("""
about after again against also because been before being between both cannot
could during each other from further having however into itself more most only
other over same should some such than that their them then there these they
this those through under until very were what when where which while with
would your also many much been has had was were are is be by of in on to a an
and or as at it its
""".split())

_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Sentences scoring below this are printed FIRST for review. It is a sort order,
# NOT a pass mark: measured against the three known failures it surfaces one and
# misses two, so treating it as a verdict would hide real errors behind a
# comfortable number. See the module docstring.
REVIEW_FIRST_BELOW = 0.8


def content_words(text: str) -> set[str]:
    """The words in `text` distinctive enough to trace back to a source.

    Numbers are kept whatever their length: "1929", "45" and "700" are exactly
    the tokens that betray a claim borrowed from the wrong passage, and they are
    shorter than the length cutoff that filters ordinary prose.
    """
    words = re.findall(r"[a-zA-Z]+|\d+", text.lower())
    return {
        word
        for word in words
        if word.isdigit() or (len(word) >= 5 and word not in _STOPWORDS)
    }


@dataclass(frozen=True)
class Claim:
    """One sentence of an answer, and the passage it points at."""

    sentence: str
    citation: int          # the [n] the sentence carries
    support: float         # 0.0–1.0, how much of its vocabulary the passage has
    missing: tuple[str, ...]  # the distinctive words the passage does NOT have

    @property
    def worth_reading(self) -> bool:
        """Whether to put this sentence in front of the reader first.

        Not a judgement that the sentence is wrong. Low overlap is a weak signal
        and high overlap is no defence at all — a passage can contain every word
        of a claim and still be about the wrong century.
        """
        return self.support < REVIEW_FIRST_BELOW


def check(answer: str, passages: Sequence[Retrieved]) -> list[Claim]:
    """Every cited sentence in `answer`, scored against the passage it cites.

    A sentence carrying several markers is scored against each one and keeps its
    BEST score. That is deliberate: the prompt tells the model a claim drawn
    from two passages may carry both, so demanding that every marker account for
    the whole sentence would manufacture failures out of correct behaviour.
    """
    claims: list[Claim] = []
    for sentence in _SENTENCE.split(answer.strip()):
        numbers = [int(m.group(1)) for m in _MARKER.finditer(sentence)]
        if not numbers:
            continue  # uncited prose is a different problem; see the CLI report
        words = content_words(_MARKER.sub("", sentence))
        if not words:
            continue
        best: Claim | None = None
        for number in numbers:
            if not 1 <= number <= len(passages):
                # A marker outside the range given to the model. citations.py
                # drops these before rendering, so the reader never sees them,
                # but for measurement it is a total support failure.
                claims.append(Claim(sentence.strip(), number, 0.0, tuple(sorted(words))))
                best = None
                break
            passage_words = content_words(passages[number - 1].text)
            found = words & passage_words
            score = len(found) / len(words)
            candidate = Claim(
                sentence=sentence.strip(),
                citation=number,
                support=score,
                missing=tuple(sorted(words - passage_words)),
            )
            if best is None or candidate.support > best.support:
                best = candidate
        if best is not None:
            claims.append(best)
    return claims


def all_citations(answer: str) -> list[int]:
    """Every passage number the answer cites, in order of first use.

    Separate from `check()` on purpose. `check()` scores a sentence against its
    BEST-matching citation and reports only that one, which is right for
    ranking what to read — but it means a sentence citing [3][4] disappears from
    any tally built from `Claim.citation`.

    That mattered: a run summary built that way showed "cites [1, 2, 4]" for an
    answer that also cited [3], a Great Depression passage. The one number the
    whole grounding investigation turned on was undercounting, and undercounting
    in the reassuring direction. Which passages an answer touched is a question
    about the raw markers, so it is answered from the raw markers.
    """
    seen: dict[int, None] = {}
    for match in _MARKER.finditer(answer):
        seen.setdefault(int(match.group(1)), None)
    return list(seen)


def uncited_sentences(answer: str) -> list[str]:
    """Sentences making a claim with no citation at all.

    Not automatically a fault — a linking sentence carries no claim — but worth
    counting, because an uncited factual claim is exactly what the reader cannot
    check, and the app shows no source card for it.
    """
    out = []
    for sentence in _SENTENCE.split(answer.strip()):
        stripped = sentence.strip()
        if stripped and not _MARKER.search(stripped) and len(content_words(stripped)) >= 3:
            out.append(stripped)
    return out


def _chapter_number(heading: str) -> str:
    """The chapter a heading belongs to, ignoring its section.

    "32.2 The Domestic Mission" is part of chapter 32. Comparing the full
    "32.2" against "32" reported every run as citing outside its anchor
    chapter — 10/10, which is noise rather than signal. Only the integer part
    separates 2008 material from 1929 material here.
    """
    if not heading.strip():
        return "?"
    return heading.split()[0].split(".")[0]


def _report(runs: list[tuple[str, list[Claim], list[str]]],
            passages: Sequence[Retrieved]) -> None:
    """Lay the runs out for a person. Deliberately reaches no verdict."""
    print("\n" + "=" * 78)
    print("  PASSAGES THE MODEL WAS GIVEN")
    for number, passage in enumerate(passages, start=1):
        where = passage.heading or "(no chapter heading)"
        print(f"    [{number}] p.{passage.cite_page:<5} {passage.source_title[:28]:<30} {where[:40]}")
    print("\n  If an answer cites passages from two chapters, read it closely —")
    print("  that is the shape the 2008/1929 confusion takes.")

    print("\n" + "=" * 78)
    print("  SENTENCES WORTH CHECKING, lowest vocabulary overlap first")
    print("  (a HINT, not a verdict — a passage can contain every word of a")
    print("   claim and still be about the wrong century)\n")

    flagged = sorted(
        ((claim, index) for index, (_, claims, _) in enumerate(runs, 1)
         for claim in claims if claim.worth_reading),
        key=lambda pair: pair[0].support,
    )
    if not flagged:
        print("    nothing below the review threshold — still read a couple in full")
    for claim, run in flagged:
        print(f"    run {run}, cites [{claim.citation}], overlap {claim.support:.0%}")
        print(f"      {claim.sentence[:150]}")
        if claim.missing:
            print(f"      not in that passage: {', '.join(claim.missing[:8])}")
        print()

    print("=" * 78)
    print("  CHAPTER SPREAD PER RUN — every marker, not only best-scoring ones")
    print("  A run citing two chapters is not automatically wrong: a framed")
    print("  comparison is legitimate. It is where to look, not a verdict.\n")
    # The CHAPTER, not the section: "32.2 The Domestic Mission" is part of
    # chapter 32, so comparing the full "32.2" against "32" reported every run
    # as citing outside its anchor chapter — 10/10, which is noise, not signal.
    chapters = {n: _chapter_number(p.heading or "") for n, p in enumerate(passages, 1)}
    anchor = chapters.get(1)
    for index, (text, _, _) in enumerate(runs, 1):
        cited = sorted(all_citations(text))
        other = [n for n in cited if chapters.get(n) != anchor and n in chapters]
        note = f"  <-- also cites chapter(s) {sorted({chapters[n] for n in other})}" if other else ""
        print(f"    run {index}: {cited}{note}")
    mixed = sum(1 for text, _, _ in runs
                if any(chapters.get(n) != anchor for n in all_citations(text) if n in chapters))
    print(f"\n    {mixed}/{len(runs)} runs cited a passage outside chapter {anchor}\n")

    uncited = [(text, index) for index, (_, _, texts) in enumerate(runs, 1) for text in texts]
    if uncited:
        print("=" * 78)
        print(f"  {len(uncited)} FACTUAL SENTENCE(S) WITH NO CITATION")
        print("  Nothing supports these, and the app shows no source card for them.\n")
        for text, run in uncited[:8]:
            print(f"    run {run}: {text[:140]}")
    print("=" * 78)
    print(f"  {len(runs)} runs sampled. Read at least two answers in full — this")
    print("  tool narrows where to look, it does not decide whether they are right.")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="the question to sample")
    parser.add_argument("--runs", type=int, default=5,
                        help="how many times to ask it (default 5)")
    parser.add_argument("-k", type=int, default=None, help="passages to retrieve")
    parser.add_argument("--show", action="store_true",
                        help="print every answer in full as it arrives")
    args = parser.parse_args()

    from cliopedia.generate import GenerationError, answer as generate_answer, is_refusal
    from cliopedia.retrieve import RetrievalError, retrieve

    try:
        passages = retrieve(args.question, k=args.k)
    except RetrievalError as exc:
        print(f"\n{exc}")
        return 1

    print(f'Question: {args.question}')
    print(f"{len(passages)} passages retrieved, sampling {args.runs} answers\n")

    runs = []
    for index in range(1, args.runs + 1):
        try:
            text = generate_answer(args.question, passages)
        except GenerationError as exc:
            print(f"\n{exc}")
            return 1
        if is_refusal(text):
            print(f"  run {index}: refusal")
            runs.append((text, [], []))
            continue
        claims = check(text, passages)
        cited = sorted(all_citations(text))
        low = sum(1 for claim in claims if claim.worth_reading)
        print(f"  run {index}: cites {cited}, {low} sentence(s) worth checking")
        if args.show:
            print(f"    {text}\n")
        runs.append((text, claims, uncited_sentences(text)))

    _report(runs, passages)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
