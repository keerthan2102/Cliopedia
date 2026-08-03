"""Turning pipeline output into something readable, without changing it.

Separate from `app.py` because a Streamlit script executes top to bottom on
import — there is no way to test a function defined inside one. These are pure
string functions, and given that the fidelity of a displayed snippet is the
thing this project asks students to trust, they are worth testing.
"""

from __future__ import annotations

import re

_MARKER = re.compile(r"\[(\d+)\]")

# Characters that can legitimately end a sentence, including the closing
# quotation marks a textbook uses.
_SENTENCE_ENDINGS = '.?!"”\'’'


def as_excerpt(snippet: str) -> str:
    """Mark a retrieved passage as the fragment it is.

    Chunk boundaries cut mid-sentence, so a passage often begins partway
    through a clause: "real estate deal in American history, the Louisiana
    Purchase...". Trimming to the nearest sentence would read better while
    quietly making it a *different* quotation — and the snippet exists so a
    student can check the answer against the source, which only works if it is
    exactly what was indexed.

    So the text is never altered. An ellipsis marks each end that is not a real
    boundary, which tells the reader they are seeing a fragment. Whitespace is
    collapsed, because extracted PDF text carries the line breaks of a printed
    column rather than of sentences (CLAUDE.md §8 Rule 8).
    """
    text = " ".join(snippet.split())
    if not text:
        return ""
    if not text[0].isupper():
        text = f"…{text}"
    if text[-1] not in _SENTENCE_ENDINGS:
        text = f"{text}…"
    return text


def highlight_markers(text: str) -> str:
    """Embolden [1] / [2] so the eye can pair a claim with its source card.

    Not hyperlinks: Streamlit has no dependable in-page anchor, and a link that
    silently fails to scroll is worse than one that was never offered. Matching
    numbers carry the traceability requirement — the reader sees [2] in a
    sentence and finds the card headed [2] below.
    """
    return _MARKER.sub(r"**[\1]**", text)
