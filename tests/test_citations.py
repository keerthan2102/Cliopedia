"""Tests for citation assembly.

This is the layer the project's central claim rests on: an answer that cannot be
traced to a source has failed. So the cases that matter most here are the ones
where a citation would be *wrong* rather than merely absent.
"""

from __future__ import annotations

import pytest

from cliopedia.citations import Citation, Locator, attach, cited_numbers
from cliopedia.retrieve import Retrieved


def passage(text: str, printed: int, pdf: int, kind: str = "page") -> Retrieved:
    return Retrieved(
        text=text,
        similarity=0.9,
        source_title="OpenStax U.S. History",
        source_type="secondary",
        locator_kind=kind,
        locator_value=pdf,
        printed_page=printed,
    )


PASSAGES = [
    passage("The Louisiana Purchase of 1803 doubled the land area.", 12, 20),
    passage("Napoleon offered the territory after Saint-Domingue.", 13, 21),
    passage("The Missouri Compromise drew a line across the territory.", 32, 40),
]


def test_finds_markers_in_order_of_first_use():
    assert cited_numbers("A [2]. B [1]. C [2] again.") == [2, 1]


def test_ignores_bracketed_text_that_is_not_a_marker():
    assert cited_numbers("A clarification [sic] and a note [see below].") == []


def test_only_cited_passages_become_sources():
    """Listing uncited passages implies evidence that was never used."""
    citations = attach("Jefferson bought it [1].", PASSAGES)
    assert [c.number for c in citations] == [1]


def test_citation_carries_everything_needed_to_verify():
    citation = attach("Claim [2].", PASSAGES)[0]
    assert citation.source_title == "OpenStax U.S. History"
    assert citation.source_type == "secondary"
    assert citation.locator == Locator(kind="page", value=13)
    assert citation.pdf_page == 21
    assert "Saint-Domingue" in citation.snippet


def test_locator_uses_the_printed_page_not_the_pdf_page():
    """A reader means the printed folio by 'page 13'."""
    citation = attach("Claim [1].", PASSAGES)[0]
    assert citation.locator.value == 12 and citation.pdf_page == 20


def test_locator_falls_back_when_the_folio_is_unknown():
    unknown = [passage("Front matter text.", -1, 5)]
    citation = attach("Claim [1].", unknown)[0]
    assert citation.locator.value == 5


def test_out_of_range_marker_is_dropped_not_rendered():
    """The prompt forbids inventing a number. Forbidding is not preventing."""
    citations = attach("Real [1]. Invented [7]. Also invented [0].", PASSAGES)
    assert [c.number for c in citations] == [1]


def test_answer_citing_nothing_produces_no_citations():
    assert attach("An unsourced assertion.", PASSAGES) == []


def test_snippet_is_whitespace_collapsed_for_display():
    wrapped = [passage("The Louisiana\nPurchase   of\n1803.", 12, 20)]
    assert attach("X [1].", wrapped)[0].snippet == "The Louisiana Purchase of 1803."


@pytest.mark.parametrize(
    "locator,expected",
    [
        (Locator("page", 214), "p. 214"),
        (Locator("paragraph", 37), "paragraph 37"),
        (Locator("page", -1), "location unknown"),
    ],
)
def test_locator_renders_by_kind(locator, expected):
    """A page-less P2 source must render without a UI change."""
    assert str(locator) == expected


def test_label_is_the_source_card_heading():
    citation = attach("Claim [3].", PASSAGES)[0]
    assert citation.label == "[3] OpenStax U.S. History — p. 32"


def test_paragraph_locator_survives_the_whole_path():
    """P2's plain-text sources fit the existing shape, as SPEC 6.4 intended."""
    para = [passage("A period document with no pages.", -1, 37, kind="paragraph")]
    citation = attach("Claim [1].", para)[0]
    assert citation.locator == Locator(kind="paragraph", value=37)
    assert citation.label.endswith("paragraph 37")


def test_citations_are_frozen():
    citation = attach("Claim [1].", PASSAGES)[0]
    with pytest.raises(Exception):
        citation.number = 99  # type: ignore[misc]
    assert isinstance(citation, Citation)
