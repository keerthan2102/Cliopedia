"""What the corpus is made of — one list, read by everything that needs it.

Before this file, a book existed in two unrelated places: `DEFAULT_URL` and
`DEFAULT_FILENAME` in `scripts/download_sources.py` said where to fetch it, and
the `SOURCES` dict in `ingest.py` said what to call it in a citation. Adding a
second book meant editing both, and forgetting the second edit does not fail
loudly — `_describe()` falls back to the filename stem, so citations would
quietly read "openstax-world-history-v1" instead of "World History Volume 1".
A silent wrong citation is the one failure this project cannot tolerate.

So the corpus is declared once, here, and both sides read it.

A book may be registered before its PDF URL is known. `url = None` means
exactly that: **not yet established**, never "probably this". Guessing a URL is
how the print edition got downloaded twice — a stale 2016 object that returned
HTTP 200 and was truncated (see CLAUDE.md §8 Rule 7). An unset URL makes the
download script say what is missing and where to get it, which is the honest
behaviour when the answer is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

# Every book here must carry this licence. It is not decoration: NonCommercial
# constrains the deployed demo, and ShareAlike travels with the verbatim
# passages embedded in data/chroma/, so the index cannot ship under the repo's
# MIT LICENSE. See CLAUDE.md §8 Rule 3 — a wrong attribution is a licence
# violation, not a typo.
CORPUS_LICENCE = "CC BY-NC-SA 4.0"


@dataclass(frozen=True)
class Book:
    """One source document, from where to fetch it through to how it is cited.

    Frozen because the registry is read from several places and a corpus that
    can be mutated at runtime makes "which book produced this citation" a
    question with no stable answer.
    """

    key: str           # short name for the command line
    filename: str      # what it is called under data/raw/
    title: str         # what a citation shows the student
    source_type: str   # "secondary" (textbook) or "primary" (period document)
    details_page: str  # the book's OpenStax page, where a fresh URL comes from
    url: str | None = None  # None means NOT YET ESTABLISHED — never a guess

    @property
    def pending(self) -> bool:
        """True when this book cannot be downloaded yet, because no URL is known."""
        return self.url is None


# The order here is the order books are fetched and ingested. It has no effect
# on retrieval — every chunk carries its own source_title — but a stable order
# keeps ingest output readable when three books scroll past.
CORPUS: tuple[Book, ...] = (
    Book(
        key="us-history",
        filename="openstax-us-history.pdf",
        title="OpenStax U.S. History",
        source_type="secondary",
        details_page="https://openstax.org/details/books/us-history",
        # The WEB edition, not the print one. Confirmed 2026-07-29 with
        # --inspect: 136,400,038 bytes, Last-Modified 2026-04-21, tail ends
        # "startxref\n216\n%%EOF\n". A structurally complete PDF.
        #
        # There is also a USHistory-OP.pdf at the same prefix. Do not use it.
        # It returns HTTP 200 and downloads happily, but the object is a stale
        # 2016 upload truncated to 324,153,344 bytes — an exact multiple of
        # 4096 — with no %%EOF anywhere in its tail. It cost two full downloads
        # to discover. Resolving is not the same as being the right file.
        #
        # WEB is also right on the merits: less than half the size, because
        # this pipeline only extracts text and never needs print-resolution art.
        url="https://assets.openstax.org/oscms-prodcms/media/documents/US_History_-_WEB.pdf",
    ),
    # ── The corpus expansion ────────────────────────────────────────────────
    # Both volumes are confirmed CC BY-NC-SA 4.0, read on 2026-08-05 from
    # OpenStax's own collection metadata rather than from a search summary:
    #   raw.githubusercontent.com/openstax/osbooks-world-history/main/
    #     collections/world-history-volume-{1,2}.collection.xml
    # each carrying
    #   <md:license url="http://creativecommons.org/licenses/by-nc-sa/4.0/">
    # The titles below are the <md:title> values from those same files.
    #
    # Same licence as U.S. History, so the expansion needs no new licensing
    # work and the README's existing MIT/CC split still holds unchanged.
    #
    # Both URLs were checked with --inspect on 2026-08-06 before being written
    # here, which is the rule these two entries exist to honour: a link is
    # registered only after the served object has been shown to be structurally
    # complete. Evidence recorded so a future break can be told from a fetch
    # that was never right in the first place.
    Book(
        key="world-history-1",
        filename="openstax-world-history-volume-1.pdf",
        title="OpenStax World History Volume 1, to 1500",
        source_type="secondary",
        details_page="https://openstax.org/details/books/world-history-volume-1",
        # 201,039,307 bytes, Last-Modified 2026-04-21, tail ends
        # "startxref\n216\n%%EOF\n" with %%EOF 6 bytes from the end. Not a
        # multiple of 4096, and the same publication date as U.S. History —
        # both of the tells that caught the stale print edition come back clean.
        url="https://assets.openstax.org/oscms-prodcms/media/documents/World_History_Volume_1-WEB.pdf",
    ),
    Book(
        key="world-history-2",
        filename="openstax-world-history-volume-2.pdf",
        title="OpenStax World History Volume 2, from 1400",
        source_type="secondary",
        details_page="https://openstax.org/details/books/world-history-volume-2",
        # 132,663,448 bytes, Last-Modified 2026-04-21, same clean tail.
        url="https://assets.openstax.org/oscms-prodcms/media/documents/World_History_Volume_2-WEB.pdf",
    ),
)


def by_filename() -> dict[str, tuple[str, str]]:
    """Filename → (title, source_type), the shape `ingest.py` cites from.

    Derived rather than hand-maintained, so a book can never be downloadable
    but uncitable — the failure this module exists to prevent.
    """
    return {book.filename: (book.title, book.source_type) for book in CORPUS}


def find(key: str) -> Book:
    """Look a book up by its command-line key, listing the valid ones on a miss."""
    for book in CORPUS:
        if book.key == key:
            return book
    known = ", ".join(b.key for b in CORPUS)
    raise KeyError(f"No book with key {key!r}. Known keys: {known}")


def downloadable() -> tuple[Book, ...]:
    """The books whose URL is known, and which can therefore be fetched now."""
    return tuple(book for book in CORPUS if not book.pending)


def pending() -> tuple[Book, ...]:
    """The books registered but not yet fetchable, because no URL is set."""
    return tuple(book for book in CORPUS if book.pending)
