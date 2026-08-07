"""Tests for reading the printed page number off a page.

This is citation machinery, so it is tested against the strings the real corpus
actually prints rather than invented ones. Every footer below was copied out of
an OpenStax PDF during the corpus expansion.

The failure being guarded against is specific: `_folio` originally required a
line to be *entirely* digits, which matched almost nothing, and `_folio_offset`
then either declined (World History) or accepted an offset resting on six pages
out of 987 (U.S. History). A wrong printed page is the one error this project
defines itself against, so both the detection and its refusal to guess are
worth holding in place.
"""

from __future__ import annotations

from cliopedia.ingest import _folio, _folio_offset

# Verbatim last lines from the three books in the corpus.
US_FOOTERS = [
    "4.5 • Wars for Empire     105",
    "7.4 • The Constitutional Convention and Federal Constitution     185",
    "11.3 • Independence for Texas     285",
    "14 • Critical Thinking Questions     385",
]
WORLD_FOOTERS = [
    "3 • Assessments     111",
    "5.3 • Korea, Japan, and Southeast Asia     191",
    "7.4 • Religion in the Roman Empire     291",
    "9.3 • The Kingdom of Kush     391",
]


def page(*lines: str) -> str:
    return "\n".join(lines)


# ── Detection ───────────────────────────────────────────────────────────────


def test_a_line_that_is_only_the_number_is_a_folio():
    """The classic layout, and the only one the first version handled."""
    assert _folio(page("Some body text.", "214")) == 214


def test_a_folio_trailing_a_running_footer_is_found():
    """What OpenStax actually prints, and what used to be missed entirely."""
    assert _folio(page("Body text.", "9.3 • The Kingdom of Kush     391")) == 391


def test_every_real_us_history_footer_parses():
    expected = [105, 185, 285, 385]
    assert [_folio(page("Body.", f)) for f in US_FOOTERS] == expected


def test_every_real_world_history_footer_parses():
    expected = [111, 191, 291, 391]
    assert [_folio(page("Body.", f)) for f in WORLD_FOOTERS] == expected


def test_the_first_line_is_checked_when_the_last_has_no_number():
    assert _folio(page("214", "Body text with no trailing number.")) == 214


def test_the_last_line_wins_over_the_first():
    """Folios sit at the foot far more often than the head."""
    assert _folio(page("999", "Body.", "4.5 • Wars for Empire     105")) == 105


def test_a_page_with_no_number_anywhere_declines():
    assert _folio(page("Body text.", "More body text.")) is None


def test_an_empty_page_declines():
    assert _folio("") is None
    assert _folio("   \n  \n") is None


# ── Not folios ──────────────────────────────────────────────────────────────


def test_a_figure_reference_is_not_read_as_a_folio():
    """'9.17' ends in 17, but the digits follow a full stop, not a space."""
    assert _folio(page("Body.", "As shown in FIGURE 9.17")) is None


def test_a_number_glued_to_a_word_is_not_a_folio():
    assert _folio(page("Body.", "See Chapter12")) is None


def test_an_implausibly_large_number_is_not_a_folio():
    assert _folio(page("Body.", "Population reached 60000")) is None


# ── The offset vote ─────────────────────────────────────────────────────────


def test_a_consistent_book_establishes_its_offset():
    """Twenty pages, folio ten behind the PDF index."""
    texts = [page("Body.", f"1.1 • Section     {i - 10}") for i in range(1, 21)]
    assert _folio_offset(texts) == 10


def test_a_few_stray_numbers_do_not_move_the_offset():
    """A year ending a sentence votes once; the majority overrules it."""
    texts = [page("Body.", f"1.1 • Section     {i - 16}") for i in range(1, 31)]
    texts[4] = page("Body.", "The purchase was completed in 1803")
    texts[9] = page("Body.", "Ratification followed in 1788")
    assert _folio_offset(texts) == 16


def test_too_few_detections_is_refused_however_unanimous():
    """World History Volume 2 found one folio and voted offset 404.

    Unanimous, and wrong. The minimum-votes floor is the only thing that
    rejected it, so it is held here explicitly.
    """
    texts = [page("Body text with no number.") for _ in range(700)]
    texts[0] = page("Body.", "404")
    assert _folio_offset(texts) is None


def test_a_split_vote_is_refused_rather_than_broken_arbitrarily():
    """No clear majority means the layout defeats the heuristic. Say so."""
    texts = []
    for i in range(1, 11):
        texts.append(page("Body.", f"1.1 • A     {i - 5}"))
        texts.append(page("Body.", f"1.1 • B     {i - 900}"))
    assert _folio_offset(texts) is None


def test_a_book_with_no_folios_at_all_declines():
    texts = [page("Body text.", "More body text.") for _ in range(50)]
    assert _folio_offset(texts) is None
