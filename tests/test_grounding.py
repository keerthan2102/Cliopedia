"""Tests for the grounding review aid.

The interesting tests here are the ones that pin what this tool CANNOT do. An
overlap heuristic looks like a grounding checker, and treating it as one would
reproduce the Rule 13 failure in a new place: a comfortable number, believed,
hiding real errors. Two of the three real failures collected so far score high
and would pass any threshold. That is recorded below as expected behaviour, not
as a bug to fix later, so nobody promotes this into a metric by accident.
"""

from __future__ import annotations

from cliopedia.grounding import (
    REVIEW_FIRST_BELOW,
    check,
    content_words,
    uncited_sentences,
)
from cliopedia.retrieve import Retrieved


def passage(text: str, number: int = 1) -> Retrieved:
    return Retrieved(
        text=text,
        similarity=0.9,
        source_title="OpenStax U.S. History",
        source_type="secondary",
        locator_kind="page",
        locator_value=number,
        printed_page=number,
    )


# ── content_words ───────────────────────────────────────────────────────────


def test_short_and_common_words_are_not_evidence():
    """'the crisis was in' should not count as tracing a claim to a source."""
    assert content_words("The crisis was in the bank") == {"crisis"}


def test_numbers_survive_the_length_filter():
    """1929, 45 and 700 are exactly the tokens that betray a borrowed claim."""
    words = content_words("stock prices fell by 45 percent in 1929")
    assert "45" in words and "1929" in words


# ── check ───────────────────────────────────────────────────────────────────


def test_a_claim_drawn_from_its_passage_scores_high():
    answer = "Millions defaulted on adjustable-rate loans and faced foreclosure [1]."
    passages = [passage("increased monthly payments from adjustable-rate loans, "
                        "millions of people defaulted and were put into foreclosure")]
    claim = check(answer, passages)[0]
    assert claim.support > 0.8
    assert not claim.worth_reading


def test_a_fabricated_claim_scores_zero_and_names_what_is_missing():
    """The 'automobiles' case: the cited passage never mentions them."""
    answer = "The situation worsened due to the integral role of automobiles [1]."
    passages = [passage("investors withdrew their money from banks by the thousands, "
                        "fearing the banks would go under")]
    claim = check(answer, passages)[0]
    assert claim.support == 0.0
    assert claim.worth_reading
    assert "automobiles" in claim.missing


def test_a_sentence_citing_two_passages_keeps_its_best_score():
    """The prompt allows [1][3] for a claim spanning two passages."""
    answer = "Congress created the Troubled Asset Relief Program [1][2]."
    passages = [
        passage("wholly unrelated text about Neolithic settlements", 1),
        passage("Congress subsequently passed the Emergency Economic Stabilization "
                "Act, creating the Troubled Asset Relief Program", 2),
    ]
    claim = check(answer, passages)[0]
    assert claim.citation == 2
    assert claim.support > 0.8


def test_a_marker_outside_the_given_range_scores_zero():
    """citations.py drops these before rendering; for review they are total misses."""
    claim = check("A claim about something [7].", [passage("text")])[0]
    assert claim.citation == 7
    assert claim.support == 0.0


def test_uncited_prose_is_not_scored_as_a_claim():
    assert check("This sentence cites nothing at all.", [passage("text")]) == []


# ── The limits, pinned deliberately ─────────────────────────────────────────


def test_one_fabricated_word_among_true_ones_is_NOT_caught():
    """The 'resentment' case, which scored 71% against the real p.896.

    'resentment' was the entire false claim; every other distinctive word was
    genuinely on the page, so the fabrication drowns in them. Pinned because it
    is the reason this module reports rather than judges.
    """
    answer = ("It led to widespread resentment towards the expensive federal "
              "bailout of banks and investment firms [1].")
    passages = [passage(
        "widespread towards expensive federal bailout of banks and investment "
        "firms, agreed to use federal funds to bail out troubled institutions"
    )]
    claim = check(answer, passages)[0]
    assert "resentment" in claim.missing, "the one false word IS identified"
    assert claim.support > REVIEW_FIRST_BELOW, (
        "yet the sentence scores above any usable threshold, so a pass/fail "
        "checker would wave the fabrication through"
    )


def test_right_words_wrong_century_is_NOT_caught():
    """The 'luxury cars' case, which scored 67% against the real p.680.

    Every distinctive word of the claim really is in the passage. The error is
    that the passage is 1929 material while the ANSWER AROUND IT frames the
    whole thing as 2008 — and note where that framing lives: in the preceding
    sentences, not in this one. The real failing sentence named no year at all.
    A per-sentence check cannot see context it never reads, so no threshold
    fixes this; only a reader can, which is why the CLI prints each passage's
    chapter alongside the answer.
    """
    answer = ("The situation was exacerbated by Americans having limited savings "
              "and being unable to afford luxury goods such as cars [1].")
    passages = [passage(
        "In 1929 the situation was exacerbated as americans were unable to "
        "afford luxury goods, having limited savings; few could afford luxury "
        "cars like Stutz and Deusenberg, so those companies went out of business"
    )]
    claim = check(answer, passages)[0]
    assert claim.support == 1.0, "every distinctive word is in the passage"
    assert not claim.worth_reading, "so it is never surfaced — yet it is wrong"


# ── uncited_sentences ───────────────────────────────────────────────────────


def test_an_uncited_factual_sentence_is_surfaced():
    text = "Bank runs spread across the country during the panic."
    assert uncited_sentences(text) == [text]


def test_a_short_linking_sentence_is_not_surfaced():
    """'This led to a decline.' carries no checkable claim."""
    assert uncited_sentences("This was so.") == []


def test_a_cited_sentence_is_not_reported_as_uncited():
    assert uncited_sentences("Millions defaulted on their loans [1].") == []
