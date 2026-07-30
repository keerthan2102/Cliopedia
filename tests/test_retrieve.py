"""Tests for the retrieval layer.

Retrieval is tested because it is the part that fails quietly. A broken prompt
or a broken model call is obvious on screen; retrieval that returns the wrong
four passages produces a fluent answer citing pages that do not support it.

Two decisions make these tests fast enough to run on every change:

**A tiny corpus, not the textbook.** Six short passages with known content, so
"did it retrieve the right one" has an answer we can assert rather than eyeball.
The real 987-page index proves nothing here that six passages do not.

**A toy embedding model, not all-MiniLM-L6-v2.** `_BagOfWords` scores passages
by shared vocabulary. It is a genuinely worse embedding than the real one — it
knows nothing about meaning, only about words in common — but it is
deterministic, needs no PyTorch, and runs in milliseconds. What is under test is
the wiring and the ranking contract, not the quality of the embedding model,
which is what the P3 evaluation harness is for.
"""

from __future__ import annotations

import re
import shutil

import pytest

from cliopedia import ingest, retrieve
from cliopedia.config import Settings

PASSAGES = [
    ("The Louisiana Purchase of 1803 nearly doubled the land area of the young "
     "nation, bought from Napoleon for fifteen million dollars.", 20, 12),
    ("Napoleon offered the whole Louisiana territory after losing Saint-Domingue "
     "and facing renewed war with Britain.", 21, 13),
    ("The Missouri Compromise of 1820 admitted Missouri as a slave state and "
     "Maine as a free state, drawing a line across the territory.", 40, 32),
    ("Reconstruction after the Civil War attempted to rebuild the southern "
     "states and secure rights for freedpeople.", 300, 292),
    ("The transcontinental railroad was completed in 1869, linking the eastern "
     "network to the Pacific coast.", 410, 402),
    ("Jamestown was founded in 1607 as the first permanent English settlement "
     "in North America.", 5, -1),  # front matter: printed page unknown
]


class _BagOfWords:
    """A deterministic stand-in for a real embedding model.

    Builds a fixed vocabulary from the corpus and represents any text as counts
    over it. Cosine similarity over those counts ranks by shared words — crude,
    but real enough to test that the right passage comes back first.
    """

    # Without this, the model ranks by the commonest words in English. The first
    # version of these tests retrieved a passage about railroads for a question
    # about the Louisiana Purchase, on the strength of three occurrences of
    # "the". Real embedding models learn to discount such words; the toy one has
    # to be told.
    STOPWORDS = frozenset(
        "a an the of and or for from in on at as to was were is are be been by "
        "with after its it that this these those what when where who which how".split()
    )

    def __init__(self, corpus: list[str]) -> None:
        vocab = sorted({word for text in corpus for word in self._words(text)})
        self._index = {word: i for i, word in enumerate(vocab)}

    @classmethod
    def _words(cls, text: str) -> list[str]:
        # A regex, not str.strip of hand-listed punctuation. The hand-listed
        # version omitted "?", so "Purchase?" in a question never matched
        # "Purchase" in a passage and the query silently lost half its terms.
        return [w for w in re.findall(r"[a-z0-9']+", text.lower())
                if w not in cls.STOPWORDS]

    def _vector(self, text: str) -> list[float]:
        # Presence, not frequency: repeating a word should not make a passage
        # more relevant, only having the word at all.
        vec = [0.0] * len(self._index)
        for word in self._words(text):
            if (i := self._index.get(word)) is not None:
                vec[i] = 1.0
        # An all-zero vector has no direction, so cosine distance is undefined.
        # One constant dimension keeps every vector valid without disturbing the
        # ranking between real matches.
        if not any(vec):
            vec[0] = 1e-6
        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


@pytest.fixture
def index(tmp_path, monkeypatch):
    """Build a six-passage index in a temp directory and point the code at it.

    `settings` is frozen and bound at import time in each module, so the
    replacement is patched into both modules rather than mutated — which is the
    point of freezing it.
    """
    from langchain_chroma import Chroma
    from langchain_core.documents import Document

    chroma_dir = tmp_path / "chroma"
    patched = Settings(chroma_dir=chroma_dir, embedding_model="toy", retrieval_k=4)
    monkeypatch.setattr(retrieve, "settings", patched)
    monkeypatch.setattr(ingest, "settings", patched)

    embeddings = _BagOfWords([text for text, _, _ in PASSAGES])
    documents = [
        Document(
            page_content=text,
            metadata={
                "source_title": "OpenStax U.S. History",
                "source_type": "secondary",
                "locator_kind": "page",
                "locator_value": pdf_page,
                "printed_page": printed,
                "source_file": "openstax-us-history.pdf",
            },
        )
        for text, pdf_page, printed in PASSAGES
    ]

    store = Chroma(
        persist_directory=str(chroma_dir),
        embedding_function=embeddings,
        collection_metadata=ingest.COLLECTION_METADATA,
    )
    store.add_documents(documents)

    yield embeddings

    # Chroma caches a client per directory for the life of the process, so a
    # later test pointed at a new tmp_path would otherwise reuse this one.
    from chromadb.api.client import SharedSystemClient

    SharedSystemClient.clear_system_cache()
    shutil.rmtree(chroma_dir, ignore_errors=True)


def test_retrieves_the_relevant_passage_first(index):
    hits = retrieve.retrieve("What was the Louisiana Purchase?", embeddings=index)
    assert "Louisiana Purchase" in hits[0].text


def test_a_different_question_retrieves_a_different_passage(index):
    """Guards against the failure where retrieval always returns passage one."""
    hits = retrieve.retrieve("When was Jamestown founded?", embeddings=index)
    assert "Jamestown" in hits[0].text


def test_respects_k(index):
    assert len(retrieve.retrieve("Louisiana", k=2, embeddings=index)) == 2
    assert len(retrieve.retrieve("Louisiana", k=5, embeddings=index)) == 5


def test_defaults_to_configured_k(index):
    """RETRIEVAL_K is the contract; retrieve() must not hardcode its own number."""
    assert len(retrieve.retrieve("Louisiana", embeddings=index)) == 4


def test_results_are_ordered_by_descending_similarity(index):
    hits = retrieve.retrieve("Louisiana Purchase Napoleon", embeddings=index)
    scores = [h.similarity for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_citation_metadata_survives_the_round_trip(index):
    """The whole point of the project: a passage must carry its provenance."""
    hit = retrieve.retrieve("Louisiana Purchase", k=1, embeddings=index)[0]
    assert hit.source_title == "OpenStax U.S. History"
    assert hit.source_type == "secondary"
    assert hit.locator_kind == "page"
    assert hit.locator_value == 20
    assert hit.printed_page == 12


def test_cite_page_prefers_the_printed_folio(index):
    hit = retrieve.retrieve("Louisiana Purchase", k=1, embeddings=index)[0]
    assert hit.locator_value == 20 and hit.printed_page == 12
    assert hit.cite_page == 12


def test_cite_page_falls_back_when_folio_unknown(index):
    """-1 means 'not known'. The reader still gets a page they can navigate to."""
    hit = retrieve.retrieve("Jamestown 1607 English settlement", k=1, embeddings=index)[0]
    assert hit.printed_page == -1
    assert hit.cite_page == hit.locator_value == 5


def test_similarity_is_a_similarity_not_a_distance(index):
    """A closer match must score higher, not lower."""
    close = retrieve.retrieve("Missouri Compromise 1820", k=1, embeddings=index)[0]
    assert 0.0 < close.similarity <= 1.0
    far = retrieve.retrieve("Missouri Compromise 1820", k=6, embeddings=index)[-1]
    assert close.similarity > far.similarity


def test_empty_question_is_rejected(index):
    with pytest.raises(retrieve.RetrievalError):
        retrieve.retrieve("   ", embeddings=index)


def test_missing_index_raises_rather_than_returning_nothing(tmp_path, monkeypatch):
    """No index and no results must not look the same.

    Chroma happily creates an empty collection for an unknown directory, so
    without the guard a missing index returns zero hits — indistinguishable from
    "the corpus does not cover this", which is a legitimate answer.
    """
    monkeypatch.setattr(
        retrieve,
        "settings",
        Settings(chroma_dir=tmp_path / "absent", embedding_model="toy", retrieval_k=4),
    )
    with pytest.raises(retrieve.RetrievalError, match="No index"):
        retrieve.retrieve("anything", embeddings=_BagOfWords(["x"]))
