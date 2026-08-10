"""Question → the passages most likely to answer it.

This is the "R" in RAG, and it is the part that degrades silently. A generation
bug is visible on screen; a retrieval bug just quietly hands the model the wrong
four paragraphs, and the answer reads perfectly well while citing pages that do
not support it. That is why this is the layer with tests.

How it works: the question is turned into a vector by the *same* embedding model
that turned every chunk into a vector at ingest, and Chroma returns the chunks
whose vectors point in the most similar direction.

    python -m cliopedia.retrieve "What caused the Louisiana Purchase?"
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from cliopedia.config import REPO_ROOT, settings


def _display(path):
    """Path relative to the repo when it lives there, absolute when it does not.

    CHROMA_DIR may legitimately point outside the repository — config.py
    supports an absolute value — and Path.relative_to raises rather than
    degrading when the path is elsewhere. An error message is the worst place
    for a second, unrelated exception.
    """
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


class RetrievalError(RuntimeError):
    """Raised when there is no usable index to search."""


@dataclass(frozen=True)
class Retrieved:
    """One passage, with everything a citation needs and nothing else.

    A deliberate boundary: LangChain's `Document` stops here and the rest of the
    pipeline works with this. It keeps `prompts.py`, `generate.py` and
    `citations.py` independent of a fast-moving third-party class, and it makes
    the contract between retrieval and the rest of the app readable in one
    place.
    """

    text: str
    similarity: float
    source_title: str
    source_type: str
    locator_kind: str
    locator_value: int
    printed_page: int
    # The chapter or section named in the page's running footer, or "" when the
    # page has no usable footer. Carries the temporal context the passage text
    # often lacks — see `ingest._heading`.
    heading: str = ""

    @property
    def cite_page(self) -> int:
        """The page a reader should be told about.

        Prefers the number printed on the page, because that is what "page 214"
        means to someone holding the book. Falls back to the PDF's own page,
        which is always correct for navigation. `printed_page` is -1 when the
        folio offset could not be established — see CLAUDE.md §8 Rule 10.
        """
        return self.printed_page if self.printed_page > 0 else self.locator_value


def open_index(embeddings=None):
    """Open the persisted index, refusing to conjure an empty one.

    Chroma creates a new empty collection when pointed at a directory that has
    none, so without this guard a missing index produces zero results instead of
    an error — and zero results looks exactly like "the corpus does not cover
    that question", which is a legitimate answer. Two very different situations
    must not be allowed to look the same.
    """
    chroma_dir = settings.chroma_dir
    if not chroma_dir.exists() or not any(chroma_dir.iterdir()):
        raise RetrievalError(
            f"No index at {_display(chroma_dir)}.\n"
            "Run: python -m cliopedia.ingest"
        )

    if embeddings is None:
        # Imported lazily: this pulls PyTorch, and importing this module should
        # not cost that when the caller only wants the dataclass.
        from langchain_huggingface import HuggingFaceEmbeddings

        embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)

    from langchain_chroma import Chroma

    return Chroma(
        persist_directory=str(chroma_dir),
        embedding_function=embeddings,
    )


def retrieve(question: str, k: int | None = None, embeddings=None) -> list[Retrieved]:
    """Return the `k` passages closest in meaning to `question`.

    The embedding model is read from config, so it is by construction the same
    one used at ingest. That is not a stylistic preference: vectors from two
    different models are coordinates in unrelated spaces, so a mismatch does not
    error — it returns confident nonsense.
    """
    if not question.strip():
        raise RetrievalError("Question is empty.")

    k = k or settings.retrieval_k
    store = open_index(embeddings)
    hits = store.similarity_search_with_score(question, k=k)

    results = []
    for document, distance in hits:
        meta = document.metadata
        results.append(
            Retrieved(
                text=document.page_content,
                # Chroma returns cosine *distance*: 0.0 is identical, 1.0 is
                # unrelated. Flipping it to a similarity means a bigger number
                # is a better match, which is what a reader expects.
                similarity=1.0 - distance,
                source_title=meta.get("source_title", "Unknown source"),
                source_type=meta.get("source_type", "secondary"),
                locator_kind=meta.get("locator_kind", "page"),
                locator_value=int(meta.get("locator_value", -1)),
                printed_page=int(meta.get("printed_page", -1)),
                heading=meta.get("heading", "") or "",
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="the question to search for")
    parser.add_argument("-k", type=int, default=None, help="how many passages")
    args = parser.parse_args()

    try:
        hits = retrieve(args.question, k=args.k)
    except RetrievalError as exc:
        print(f"\n{exc}")
        return 1

    if not hits:
        print("No passages retrieved.")
        return 0

    print(f'Question: {args.question}\n')
    for rank, hit in enumerate(hits, start=1):
        snippet = " ".join(hit.text.split())[:300]
        print(f"[{rank}] {hit.source_title} — p. {hit.cite_page}"
              f"  (similarity {hit.similarity:.3f}, PDF page {hit.locator_value})")
        print(f"    {snippet}…\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
