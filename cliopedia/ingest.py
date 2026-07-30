"""Build the Chroma index from the PDFs in data/raw/.

Run offline, never at query time:

    data/raw/*.pdf
      → PyPDFLoader                     one Document per page, carrying its page
      → RecursiveCharacterTextSplitter  ~1000-char chunks, 150 of overlap
      → HuggingFaceEmbeddings           each chunk → a 384-number vector
      → Chroma(persist_directory=...)   stored on disk, committed to the repo

Why chunk at all: a whole book does not fit in a model's context window, and
searching by meaning works better on focused passages. Ask about the Louisiana
Purchase and you want the paragraph, not the chapter.

Why 150 characters of overlap: chunk boundaries are arbitrary and will cut
mid-sentence. Overlap means a fact split across a boundary still survives whole
in one of the two neighbouring chunks.

Why "recursive": the splitter tries paragraph breaks first, then line breaks,
then sentences, then words — preferring natural boundaries to chopping at
exactly 1000 characters. See CLAUDE.md §8 Rule 8 for why "line breaks" are a
weaker signal here than they look.

    python -m cliopedia.ingest
    python -m cliopedia.ingest --rebuild
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

from cliopedia.config import REPO_ROOT, settings

RAW_DIR = REPO_ROOT / "data" / "raw"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Chroma rejects a batch beyond its internal maximum, and a single add of every
# chunk also holds every vector in memory at once. 500 keeps both comfortable
# and gives the run something to print.
BATCH_SIZE = 500

# Which document each file is, for citation purposes. One entry today; P2 adds
# primary sources, which must be labelled distinctly from the textbook so the UI
# can tell a student "this is a period document, read it critically".
SOURCES: dict[str, tuple[str, str]] = {
    "openstax-us-history.pdf": ("OpenStax U.S. History", "secondary"),
}


class IngestError(RuntimeError):
    """Raised when the corpus or the index is not in a state we can build from."""


def _describe(pdf: Path) -> tuple[str, str]:
    title, source_type = SOURCES.get(pdf.name, (pdf.stem, "secondary"))
    return title, source_type


def load_and_split(pdf_paths: Iterable[Path]) -> list:
    """Turn PDFs into chunks that carry everything a citation needs.

    Metadata is flattened deliberately. `SPEC.md` §6.4 defines the locator as a
    tagged record — {"kind": "page", "value": 214} — but Chroma only stores
    scalar metadata values, so the record is split into `locator_kind` and
    `locator_value` here and reassembled in `citations.py`. The tagged shape
    still survives where it matters: page-less sources added at P2 store
    `locator_kind="paragraph"` and need no schema change.
    """
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks: list = []
    for pdf in pdf_paths:
        title, source_type = _describe(pdf)
        pages = PyPDFLoader(str(pdf)).load()
        print(f"  {pdf.name}: {len(pages)} pages")

        for chunk in splitter.split_documents(pages):
            # PyPDFLoader's `page` is a 0-based index into the PDF, so +1 gives
            # the page you would type into a viewer's page box. That is NOT
            # necessarily the number printed on the page — front matter offsets
            # the two — and closing that gap is a known open item, not something
            # to paper over by pretending they are the same.
            page_index = chunk.metadata.get("page")
            chunk.metadata = {
                "source_title": title,
                "source_type": source_type,
                "locator_kind": "page",
                "locator_value": (page_index + 1) if page_index is not None else -1,
                "source_file": pdf.name,
            }
            chunks.append(chunk)

    return chunks


def build_index(rebuild: bool = False, embeddings=None) -> int:
    """Build the index, refusing to append to an existing one.

    Appending is the failure this guard exists for. Chroma's add_documents adds
    rather than replaces, so a second run over an existing index stores every
    chunk twice. Retrieval then returns the same passage four times and k=4 is
    effectively k=1 — no error, no warning, just quietly gutted retrieval in an
    artifact that gets committed. Destroying a committed build artifact should
    require saying so out loud, hence --rebuild.
    """
    if not RAW_DIR.exists() or not (pdfs := sorted(RAW_DIR.glob("*.pdf"))):
        raise IngestError(
            f"No PDFs in {RAW_DIR.relative_to(REPO_ROOT)}.\n"
            "Run: python scripts/download_sources.py"
        )

    chroma_dir = settings.chroma_dir
    if chroma_dir.exists() and any(chroma_dir.iterdir()):
        if not rebuild:
            raise IngestError(
                f"{chroma_dir.relative_to(REPO_ROOT)} already contains an index.\n"
                "Ingesting again would append, storing every chunk twice and\n"
                "silently degrading retrieval. Pass --rebuild to replace it."
            )
        print(f"Removing existing index at {chroma_dir.relative_to(REPO_ROOT)}")
        shutil.rmtree(chroma_dir)

        # Chroma caches one client per persist_directory for the lifetime of the
        # process. Deleting the directory does not evict that cache, so the next
        # Chroma(...) on the same path reuses a client whose SQLite file no
        # longer exists and fails with "attempt to write a readonly database".
        # A one-shot CLI run never sees this — the process is new — but calling
        # build_index twice in one process does, which is exactly what the
        # retrieval tests will do.
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()

    print(f"Loading {len(pdfs)} PDF(s) from {RAW_DIR.relative_to(REPO_ROOT)}")
    chunks = load_and_split(pdfs)
    if not chunks:
        raise IngestError("Splitting produced no chunks — is the PDF text-extractable?")
    print(f"  {len(chunks)} chunks at {CHUNK_SIZE}/{CHUNK_OVERLAP}")

    if embeddings is None:
        # Imported here, not at module scope, because this pulls PyTorch and
        # takes seconds. Nothing that merely imports this module should pay for
        # a model it is not going to use.
        from langchain_huggingface import HuggingFaceEmbeddings

        print(f"\nLoading embedding model {settings.embedding_model}")
        print("  (first run downloads ~90MB)")
        embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)

    from langchain_chroma import Chroma

    store = Chroma(
        persist_directory=str(chroma_dir),
        embedding_function=embeddings,
    )

    print(f"\nEmbedding {len(chunks)} chunks in batches of {BATCH_SIZE}")
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        store.add_documents(batch)
        done = min(start + BATCH_SIZE, len(chunks))
        print(f"\r  {done}/{len(chunks)}", end="", flush=True)
    print()

    return len(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete an existing index and build it again from scratch",
    )
    args = parser.parse_args()

    try:
        count = build_index(rebuild=args.rebuild)
    except IngestError as exc:
        print(f"\n{exc}")
        return 1

    print(f"\nIndexed {count} chunks into {settings.chroma_dir.relative_to(REPO_ROOT)}")
    print(f"Embedding model: {settings.embedding_model}")
    print("\nThe index is a committed build artifact — commit it.")
    print("Next: python -m cliopedia.retrieve  (not written yet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
