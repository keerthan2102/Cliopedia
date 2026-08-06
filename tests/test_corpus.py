"""The corpus registry is small, and every guarantee it makes is load-bearing.

These run without a corpus, a model or a network. What they protect is the
thing that broke when the registry did not exist: a book that can be downloaded
but not cited, because its filename never reached `SOURCES`.
"""

from __future__ import annotations

import pytest

from cliopedia import corpus, ingest


def test_every_book_has_a_unique_key():
    """Keys select a book on the command line, so a duplicate makes one unreachable."""
    keys = [book.key for book in corpus.CORPUS]
    assert len(keys) == len(set(keys)), f"duplicate key in CORPUS: {keys}"


def test_every_book_has_a_unique_filename():
    """Two books sharing a filename would overwrite each other in data/raw/."""
    names = [book.filename for book in corpus.CORPUS]
    assert len(names) == len(set(names)), f"duplicate filename in CORPUS: {names}"


def test_ingest_can_cite_every_registered_book():
    """The whole reason this module exists.

    `_describe()` falls back to the filename stem for an unregistered file, so a
    book missing from SOURCES produces a citation reading
    "openstax-world-history-volume-1" instead of a title — and does it silently,
    on every answer, with no error anywhere. This test is what makes that
    impossible.
    """
    for book in corpus.CORPUS:
        assert book.filename in ingest.SOURCES, f"{book.filename} is not citable"
        title, source_type = ingest.SOURCES[book.filename]
        assert title == book.title
        assert source_type == book.source_type


def test_source_type_is_a_known_kind():
    """SPEC.md §6.4 labels documents secondary or primary so the UI can tell
    a student which one they are reading. A typo here would be invisible."""
    for book in corpus.CORPUS:
        assert book.source_type in {"secondary", "primary"}, book


def test_every_book_names_where_its_url_comes_from():
    """A details page is how a broken or missing URL gets fixed. Without it the
    recovery path is a search engine, which is how the wrong PDF was picked up
    the first time (CLAUDE.md §8 Rule 7)."""
    for book in corpus.CORPUS:
        assert book.details_page.startswith("https://"), book


def test_pending_and_downloadable_partition_the_corpus():
    """Every book is in exactly one of the two, so neither list can hide one."""
    assert set(corpus.pending()) | set(corpus.downloadable()) == set(corpus.CORPUS)
    assert not set(corpus.pending()) & set(corpus.downloadable())


def test_a_pending_book_has_no_url_rather_than_a_guessed_one():
    """`url = None` means not established. The alternative — a plausible-looking
    guess — is what downloaded a truncated 2016 object twice."""
    for book in corpus.pending():
        assert book.url is None


def test_find_returns_the_requested_book():
    assert corpus.find("us-history").filename == "openstax-us-history.pdf"


def test_find_lists_valid_keys_when_given_a_bad_one():
    """An unknown key is a typo at the command line; the error should answer
    the question it provokes rather than merely reporting failure."""
    with pytest.raises(KeyError) as exc:
        corpus.find("world-history")  # missing the volume number
    message = str(exc.value)
    for book in corpus.CORPUS:
        assert book.key in message


def test_us_history_is_the_web_edition():
    """The print edition at the same prefix is a truncated 2016 object that
    still returns HTTP 200. Pinning WEB here keeps that from being re-chosen."""
    book = corpus.find("us-history")
    assert book.url is not None
    assert book.url.endswith("_-_WEB.pdf"), book.url
