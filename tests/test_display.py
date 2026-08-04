"""Tests for how retrieved text is presented.

Presentation is usually not worth testing. It is here, because the snippet is
what a student uses to check that the answer did not drift from the source — so
"the displayed text is exactly what was indexed" is a correctness property, not
a styling preference.
"""

from __future__ import annotations

import pytest

from cliopedia.display import as_excerpt, highlight_markers


def test_mid_sentence_start_is_marked_not_trimmed():
    """The real case from the corpus: a chunk beginning partway through a clause."""
    raw = "real estate deal in American history, the Louisiana Purchase greatly enhanced"
    shown = as_excerpt(raw)
    assert shown.startswith("…real estate deal")
    assert "real estate deal in American history, the Louisiana Purchase greatly enhanced" in shown


def test_a_complete_sentence_gains_no_ellipses():
    clean = "The Louisiana Purchase of 1803 nearly doubled the land area."
    assert as_excerpt(clean) == clean


def test_unfinished_ending_is_marked():
    assert as_excerpt("Jefferson wanted to bolster trade in the West").endswith("West…")


def test_pdf_line_breaks_are_collapsed():
    """Extracted PDF text wraps at printed column width, not at sentences."""
    assert as_excerpt("The Louisiana\nPurchase   of\n1803.") == "The Louisiana Purchase of 1803."


def test_no_words_are_added_or_removed():
    """The one property that must hold: an excerpt is the passage, unedited."""
    raw = "produce down the Mississippi River to New Orleans, where it would be sold"
    assert as_excerpt(raw).strip("…").split() == raw.split()


def test_empty_snippet_does_not_become_lone_ellipses():
    assert as_excerpt("   ") == ""


@pytest.mark.parametrize("ending", [".", "?", "!", '"', "”"])
def test_sentence_endings_are_recognised(ending):
    assert as_excerpt(f"A finished sentence{ending}").endswith(ending)


def test_markers_are_emboldened():
    assert highlight_markers("Doubled the nation [1].") == "Doubled the nation **[1]**."


def test_every_marker_in_a_sentence_is_marked():
    out = highlight_markers("Napoleon relented [2], doubling the nation [1][3].")
    assert out == "Napoleon relented **[2]**, doubling the nation **[1][3]**."


def test_adjacent_markers_are_wrapped_as_one_run():
    """Bolding [2][4] separately yields ****, which Markdown prints literally.

    Seen on screen: "became a reality [2]****[4]." — the bug this guards.
    """
    out = highlight_markers("a reality [2][4].")
    assert out == "a reality **[2][4]**."
    assert "****" not in out


def test_three_adjacent_markers_stay_clean():
    assert "****" not in highlight_markers("Drawn from all three [1][2][3].")


def test_non_marker_brackets_are_left_alone():
    """[sic] is not a citation and must not be styled as one."""
    assert highlight_markers("A clarification [sic] here.") == "A clarification [sic] here."
