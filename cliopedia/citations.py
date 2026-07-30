"""Turning retrieved passages into citations the reader can check.

`SPEC.md` §6.4 fixes the shape: a citation carries its source, its type, a
**tagged locator**, and the verbatim snippet. The locator is a small record
rather than a bare page number so that page-less sources — the plain-text
primary documents planned for P2 — fit the same structure without changing the
UI or the index schema.

Chroma stores only scalar metadata, so `ingest.py` flattens that record into
`locator_kind` and `locator_value`. This is where it is put back together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from cliopedia.retrieve import Retrieved

# Matches the [1] / [2] markers the model is instructed to write. Deliberately
# narrow: only digits, so ordinary bracketed prose is not mistaken for a
# citation.
_MARKER = re.compile(r"\[(\d+)\]")


@dataclass(frozen=True)
class Locator:
    """Where in a source a passage came from.

    Tagged rather than bare so `{"kind": "page"}` and `{"kind": "paragraph"}`
    can coexist. A UI that renders a locator by asking its `kind` keeps working
    when a source with no pages arrives.
    """

    kind: str
    value: int

    def __str__(self) -> str:
        if self.value < 0:
            return "location unknown"
        return f"p. {self.value}" if self.kind == "page" else f"{self.kind} {self.value}"


@dataclass(frozen=True)
class Citation:
    """One source card: what the reader needs to verify a claim."""

    number: int
    source_title: str
    source_type: str
    locator: Locator
    snippet: str
    pdf_page: int

    @property
    def label(self) -> str:
        return f"[{self.number}] {self.source_title} — {self.locator}"


def cited_numbers(answer: str) -> list[int]:
    """The passage numbers the answer actually cites, in order of first use."""
    seen: dict[int, None] = {}
    for match in _MARKER.finditer(answer):
        seen.setdefault(int(match.group(1)), None)
    return list(seen)


def attach(answer: str, passages: Sequence[Retrieved]) -> list[Citation]:
    """Build the source list for an answer.

    Only passages the answer actually cites are returned. Listing all four
    retrieved passages under an answer that used two would be a quiet lie about
    provenance — the reader would reasonably assume every card supports
    something in the text.

    A marker pointing outside the range given to the model is dropped rather
    than rendered. The prompt forbids inventing one, but "the prompt forbids it"
    is not a guarantee, and a citation numbered [7] against four passages would
    otherwise crash the UI or, worse, silently point at nothing.
    """
    citations = []
    for number in cited_numbers(answer):
        if not 1 <= number <= len(passages):
            continue
        passage = passages[number - 1]
        citations.append(
            Citation(
                number=number,
                source_title=passage.source_title,
                source_type=passage.source_type,
                locator=Locator(kind=passage.locator_kind, value=passage.cite_page),
                # Collapsed for display. The line breaks in extracted PDF text
                # are printed-column artifacts, not sentence structure, and
                # showing them verbatim makes a correct quotation look mangled.
                snippet=" ".join(passage.text.split()),
                pdf_page=passage.locator_value,
            )
        )
    return citations
