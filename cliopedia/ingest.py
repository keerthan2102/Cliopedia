"""Build the Chroma index from the PDFs in data/raw/.

Run offline, never at query time:

    data/raw/*.pdf
      → load_pages()                    one Document per page, via pypdf directly
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
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Iterable

from cliopedia import corpus
from cliopedia.config import REPO_ROOT, settings

RAW_DIR = REPO_ROOT / "data" / "raw"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Chroma rejects a batch beyond its internal maximum, and a single add of every
# chunk also holds every vector in memory at once. 500 keeps both comfortable
# and gives the run something to print.
BATCH_SIZE = 500

# Chroma defaults to L2 (straight-line) distance. SPEC.md §6.2 specifies cosine,
# which compares the *direction* of two vectors and ignores their length — the
# right choice for text, where a longer passage produces a longer vector without
# being any more relevant.
#
# This is fixed when the collection is created and cannot be changed afterwards.
# An index built without it is silently ranked by the wrong metric and has to be
# rebuilt from scratch.
COLLECTION_METADATA = {"hnsw:space": "cosine"}

# Which document each file is, for citation purposes. Derived from the corpus
# registry rather than written out here, so a book cannot be fetchable but
# uncitable: an unregistered filename falls back to its stem in _describe(),
# which produces a citation reading "openstax-world-history-volume-1" instead
# of a title, and does so silently. One declaration, in cliopedia/corpus.py.
#
# P2 adds primary sources, which must be labelled distinctly from the textbook
# so the UI can tell a student "this is a period document, read it critically".
# That is the source_type field on Book; nothing here changes.
SOURCES: dict[str, tuple[str, str]] = corpus.by_filename()


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


class IngestError(RuntimeError):
    """Raised when the corpus or the index is not in a state we can build from."""


def _remove_index(chroma_dir: Path) -> None:
    """Delete the index directory, explaining a lock rather than dumping a trace.

    On Windows a file cannot be deleted while another process holds it open, so
    `shutil.rmtree` raises PermissionError (WinError 5) partway through. Two
    things make that likely here and neither is exotic: a `streamlit run app.py`
    left running keeps Chroma's SQLite file open, and this repo lives inside a
    OneDrive folder, whose sync client opens files on its own schedule.

    It matters more than an ugly traceback would suggest. rmtree deletes as it
    walks, so a failure halfway leaves a **partially deleted index** — some
    segments gone, the SQLite catalogue still referencing them. That is not an
    empty directory and not a valid index, and `open_index()` cannot tell the
    difference: it checks only that the directory is non-empty. So the run must
    stop here with instructions, rather than continuing on wreckage.
    """
    try:
        shutil.rmtree(chroma_dir)
    except PermissionError as exc:
        locked = getattr(exc, "filename", None) or chroma_dir
        raise IngestError(
            f"Could not delete the existing index — access denied on:\n"
            f"  {locked}\n\n"
            "Something else is holding a file open. Usually one of:\n"
            "  - a `streamlit run app.py` still running (close it)\n"
            "  - another python or pytest process using the index\n"
            "  - OneDrive syncing this folder (pause sync, then retry)\n"
            "  - the folder open in File Explorer or an editor\n\n"
            "IMPORTANT: the index is now PARTLY deleted, so it is neither empty\n"
            "nor valid, and querying it would give wrong or missing citations.\n"
            "Delete the whole folder before rebuilding:\n"
            f"  Windows:      rmdir /s /q {chroma_dir}\n"
            f"  PowerShell:   Remove-Item -Recurse -Force '{chroma_dir}'\n"
            f"  macOS/Linux:  rm -rf '{chroma_dir}'\n\n"
            "Then re-run: python -m cliopedia.ingest --rebuild"
        ) from exc


def _describe(pdf: Path) -> tuple[str, str]:
    title, source_type = SOURCES.get(pdf.name, (pdf.stem, "secondary"))
    return title, source_type


# A folio sitting at the end of a running footer, e.g.
#   "9.3 • The Kingdom of Kush     391"
# The digits must be preceded by whitespace (or start the line) and must end it,
# so "FIGURE 9.17" does not read as folio 17 — the character before those digits
# is a full stop, not a space.
_TRAILING_FOLIO = re.compile(r"(?:^|\s)(\d{1,4})$")


def _folio(page_text: str) -> int | None:
    """The page number *printed on* this page, if it shows one.

    Looked for in the last line first and the first line second, because that is
    where a folio is typeset.

    Two shapes count. A line that is nothing but the number is the classic case.
    The number ending a running footer is the case that matters here, because it
    is what OpenStax actually prints:

        4.5 • Wars for Empire     105
        9.3 • The Kingdom of Kush     391

    Requiring the whole line to be digits missed every one of those. It found
    folios on 6 of U.S. History's 987 pages — the handful whose footer carried
    no section title — and on 0 of World History Volume 1's 791. That was enough
    to squeak past the vote threshold for one book and fail outright for the
    other, so the corpus expansion arrived with two volumes whose printed pages
    were unknown and one whose offset rested on six pages.

    Still deliberately narrow. A trailing number that is *not* a folio (a year
    ending a sentence, a figure number) produces one stray vote, and
    `_folio_offset` discards it by majority. Guessing remains worse than
    declining: a confidently wrong page reference is the failure this project
    exists to prevent.
    """
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    if not lines:
        return None
    for candidate in (lines[-1], lines[0]):
        if candidate.isdigit() and 0 < int(candidate) < 10_000:
            return int(candidate)
        match = _TRAILING_FOLIO.search(candidate)
        if match and 0 < int(match.group(1)) < 10_000:
            return int(match.group(1))
    return None


def _folio_offset(page_texts: list[str]) -> int | None:
    """How far the printed numbering runs behind the PDF's own page count.

    Front matter means PDF page 1 is rarely printed page 1, so the two numbering
    schemes sit at a constant offset through the body of the book. Rather than
    trust any single page's folio — a stray number in a table would do — every
    detected folio votes on the offset, and the winner is accepted only if a
    clear majority of detections agree.

    Note what that majority is over: **detections, not pages.** Those are very
    different denominators, and conflating them is how the offset of 16 came to
    be described as well-established when it rested on 6 of 987 pages. The
    minimum of five votes is the only thing standing between a near-total
    detection failure and a confident wrong answer — World History Volume 2
    detected exactly one folio and voted for an offset of 404, and only that
    floor rejected it. If detections are ever a small fraction of a book's
    pages, treat the offset as suspect even when the majority looks unanimous.

    Returning None is a valid, safe answer: it means "this book's layout defeats
    the heuristic", and the caller then records no printed page at all rather
    than a plausible-looking wrong one.
    """
    votes = Counter()
    for index, text in enumerate(page_texts, start=1):
        folio = _folio(text)
        if folio is not None:
            votes[index - folio] += 1

    if not votes:
        return None
    offset, agreeing = votes.most_common(1)[0]
    total = sum(votes.values())
    if agreeing < 5 or agreeing * 2 <= total:
        return None
    return offset


def load_pages(pdf: Path) -> tuple[list, int | None]:
    """Read a PDF into one Document per page, using pypdf directly.

    LangChain's PyPDFLoader used to do this. It was dropped because
    `langchain-community` has been sunset upstream with no successor package,
    and because the wrapper is a dozen lines that hid the one thing this project
    cares most about — where a page number comes from. Writing it out keeps a
    sunset dependency out of the deploy and matches CLAUDE.md §4.1: LangChain
    for the boring stable parts, our own code for the explainable parts.
    """
    from langchain_core.documents import Document
    from pypdf import PdfReader

    reader = PdfReader(str(pdf))
    texts = [(page.extract_text() or "") for page in reader.pages]
    offset = _folio_offset(texts)

    pages = [
        Document(page_content=text, metadata={"page_index": index})
        for index, text in enumerate(texts, start=1)
        if text.strip()  # image-only pages carry no retrievable text
    ]
    return pages, offset


def load_and_split(pdf_paths: Iterable[Path]) -> list:
    """Turn PDFs into chunks that carry everything a citation needs.

    Metadata is flattened deliberately. `SPEC.md` §6.4 defines the locator as a
    tagged record — {"kind": "page", "value": 214} — but Chroma only stores
    scalar metadata values, so the record is split into `locator_kind` and
    `locator_value` here and reassembled in `citations.py`. The tagged shape
    still survives where it matters: page-less sources added at P2 store
    `locator_kind="paragraph"` and need no schema change.

    Two page numbers are stored, because they answer different questions.
    `locator_value` is the PDF's own page — what you type into a viewer's page
    box — and is always correct. `printed_page` is the number typeset on the
    page, which is what a reader means by "page 214", and is recorded only when
    the offset could be established with confidence. -1 means "not known", never
    "probably this".
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks: list = []
    for pdf in pdf_paths:
        title, source_type = _describe(pdf)
        pages, offset = load_pages(pdf)
        if offset is None:
            print(f"  {pdf.name}: {len(pages)} text pages, printed numbering not established")
        else:
            print(f"  {pdf.name}: {len(pages)} text pages, printed page = PDF page - {offset}")

        for chunk in splitter.split_documents(pages):
            pdf_page = chunk.metadata["page_index"]
            printed = pdf_page - offset if offset is not None else None
            chunk.metadata = {
                "source_title": title,
                "source_type": source_type,
                "locator_kind": "page",
                "locator_value": pdf_page,
                "printed_page": printed if printed and printed > 0 else -1,
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
            f"No PDFs in {_display(RAW_DIR)}.\n"
            "Run: python scripts/download_sources.py"
        )

    chroma_dir = settings.chroma_dir
    if chroma_dir.exists() and any(chroma_dir.iterdir()):
        if not rebuild:
            raise IngestError(
                f"{_display(chroma_dir)} already contains an index.\n"
                "Ingesting again would append, storing every chunk twice and\n"
                "silently degrading retrieval. Pass --rebuild to replace it."
            )
        print(f"Removing existing index at {_display(chroma_dir)}")
        _remove_index(chroma_dir)

        # Chroma caches one client per persist_directory for the lifetime of the
        # process. Deleting the directory does not evict that cache, so the next
        # Chroma(...) on the same path reuses a client whose SQLite file no
        # longer exists and fails with "attempt to write a readonly database".
        # A one-shot CLI run never sees this — the process is new — but calling
        # build_index twice in one process does, which is exactly what the
        # retrieval tests will do.
        from chromadb.api.client import SharedSystemClient

        SharedSystemClient.clear_system_cache()

    print(f"Loading {len(pdfs)} PDF(s) from {_display(RAW_DIR)}")
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
        collection_metadata=COLLECTION_METADATA,
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

    print(f"\nIndexed {count} chunks into {_display(settings.chroma_dir)}")
    print(f"Embedding model: {settings.embedding_model}")
    print("\nThe index is a committed build artifact — commit it.")
    print('Next: python -m cliopedia.ask "What caused the Louisiana Purchase?"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
