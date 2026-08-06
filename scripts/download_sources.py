"""Fetch the source corpus into data/raw/.

Why this script exists at all, when data/raw/ is git-ignored: the raw PDFs are
never committed, so without this the repo would be unbuildable by anyone who
cloned it — including you, on a new machine. The index in data/chroma/ is
committed for convenience, not because it is unreproducible. This script is what
makes that claim true.

Why it also inspects the licence: attribution under Creative Commons is a
licence obligation, and this project already asserted the wrong licence once by
trusting a search summary (CLAUDE.md §8 Rule 3). So the download is not
finished until the licence has been read off the document itself.

Run:
    python scripts/download_sources.py
    python scripts/download_sources.py --url https://.../SomeBook.pdf
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"

# `python scripts/download_sources.py` puts scripts/ on sys.path, not the repo
# root, so importing cliopedia would fail in exactly the form the README and
# CLAUDE.md §3 document. Adding the root explicitly keeps the documented command
# working rather than requiring `python -m scripts.download_sources` instead —
# CLAUDE.md §8 Rule 11: verify the literal command line that appears in the docs.
sys.path.insert(0, str(REPO_ROOT))

from cliopedia import corpus  # noqa: E402  (import needs the path above)

# Which books make up the corpus — their URLs, filenames and citation titles —
# now lives in cliopedia/corpus.py, read by this script and by ingest.py alike.
# It used to be a DEFAULT_URL here plus a separate SOURCES dict in ingest.py,
# which meant adding a book required editing two files and forgetting the
# second produced citations titled after the filename, silently.
#
# Only the fallback name for an ad-hoc --url fetch stays here: it belongs to
# this script's escape hatch rather than to the corpus.
DEFAULT_FILENAME = "openstax-download.pdf"

# The licence this corpus must carry, per CLAUDE.md §8 Rule 3.
EXPECTED_LICENCE = "CC BY-NC-SA 4.0"

# Matching is done against these, after stripping every non-alphanumeric
# character from both sides. Publishers punctuate the same licence differently —
# OpenStax's copyright page reads "Attribution Non-Commercial ShareAlike" while
# Creative Commons' own name for it is "Attribution-NonCommercial-ShareAlike".
# Those are the same licence, and no amount of guessing at hyphens will match
# both. Squashing to bare alphanumerics makes the punctuation irrelevant.
# Either form is accepted: the long name, or the short code the page also prints.
EXPECTED_LICENCE_FORMS = (
    "attributionnoncommercialsharealike",  # the long name, however punctuated
    "ccbyncsa40",                          # the short code
    "licensesbyncsa40",                    # the canonical URL path
)

# How many leading pages to scan for the copyright notice. OpenStax front matter
# puts it within the first few pages; 12 is slack, not a measurement.
FRONT_MATTER_PAGES = 12

# How much of the file's tail --inspect scans for the %%EOF marker. Large enough
# that trailing data after the marker cannot hide it, small enough to fetch in
# one range request rather than re-downloading hundreds of megabytes.
TAIL_SCAN_BYTES = 131072


def download(url: str, dest: Path) -> None:
    """Stream `url` to `dest`, atomically.

    The download goes to a `.part` file and is renamed only on success. Without
    that, an interrupted download leaves a truncated PDF at the real path —
    and a truncated PDF does not announce itself. `ingest.py` would parse
    whatever pages survived, embed them, and build an index that is quietly
    missing half the book. Wrong answers with confident citations is the one
    failure mode this project cannot tolerate.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")

    print(f"Fetching {url}")
    try:
        with urllib.request.urlopen(url) as response, partial.open("wb") as out:
            declared = response.headers.get("Content-Length")
            total = int(declared) if declared and declared.isdigit() else None
            written = 0
            while chunk := response.read(1 << 16):
                out.write(chunk)
                written += len(chunk)
                if total:
                    print(f"\r  {written / 1e6:6.1f} MB / {total / 1e6:.1f} MB", end="")
                else:
                    print(f"\r  {written / 1e6:6.1f} MB", end="")
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"\nHTTP {exc.code} fetching {url}\n\n"
            "If OpenStax has moved the file, find the current PDF link on the\n"
            "book's details page, check it with --url <link> --inspect, then\n"
            "update that book's url= in cliopedia/corpus.py."
        ) from exc
    except urllib.error.URLError as exc:
        partial.unlink(missing_ok=True)
        raise SystemExit(f"\nCould not reach {url}: {exc.reason}") from exc

    print()

    # The byte count is compared, not just displayed. urllib's read loop ends on
    # an empty read, and a connection that drops mid-transfer produces exactly
    # that — so a truncated download exits the loop looking like a clean finish.
    # The progress line is rounded to 0.1 MB, which hides a shortfall of tens of
    # thousands of bytes. Only an exact comparison catches it.
    if total is not None and written != total:
        partial.unlink(missing_ok=True)
        raise SystemExit(
            f"Truncated download: got {written:,} bytes, server declared {total:,} "
            f"({total - written:,} short).\n"
            "Deleted the partial file. Re-run to try again — a download this size\n"
            "over a flaky connection often needs more than one attempt."
        )

    partial.replace(dest)


def verify_is_pdf(path: Path) -> None:
    """Reject anything that is not actually a PDF.

    A server that answers a bad path with an HTML error page still returns
    HTTP 200, so 'the download succeeded' proves nothing. Every PDF starts with
    the bytes %PDF-; checking them costs nothing and catches the case where we
    cheerfully saved an error page as openstax-us-history.pdf.
    """
    size = path.stat().st_size
    with path.open("rb") as handle:
        magic = handle.read(5)
        handle.seek(-min(TAIL_SCAN_BYTES, size), 2)
        tail = handle.read()

    if magic != b"%PDF-":
        path.unlink()
        raise SystemExit(
            f"Downloaded file is not a PDF (starts with {magic!r}, {size} bytes).\n"
            "That usually means the URL served an error page. Deleted it."
        )

    # Checking the head alone is not enough, and this was learned the expensive
    # way: OpenStax's print-edition URL serves a truncated 2016 object that
    # starts with a perfectly good %PDF- header and simply stops partway. Every
    # valid PDF ends with %%EOF, so verifying the tail is what distinguishes a
    # whole document from its first two thirds.
    if b"%%EOF" not in tail:
        path.unlink()
        raise SystemExit(
            f"Downloaded {size:,} bytes with a valid PDF header but no %%EOF marker\n"
            f"in the last {len(tail):,} bytes — the file is incomplete. Deleted it.\n\n"
            "This is usually the server's fault, not the connection's. Check the\n"
            "URL with --inspect before spending another download on it."
        )


def report(path: Path) -> None:
    """Print page count and the licence line, for the human to confirm.

    This deliberately does not fail the run on a licence mismatch. The script's
    job is to put the evidence in front of you; deciding what a licence means is
    not something to automate.
    """
    # Deliberately broad. Reporting is a convenience layered on top of a
    # download that has already succeeded, and pypdf's import chain reaches
    # native crypto libraries that fail in ways that are not ImportError. A
    # broken reader must not make a good download look like a failed one.
    try:
        from pypdf import PdfReader
    except BaseException as exc:  # noqa: BLE001
        print(
            f"\nCould not load pypdf ({type(exc).__name__}), so page count and\n"
            "licence were not checked. The download itself is fine.\n"
            "Run `pip install -r requirements.txt` inside the venv, then re-run."
        )
        return

    size = path.stat().st_size

    # Every pypdf call sits inside this one guard, not just the constructor.
    # pypdf parses lazily: PdfReader() on a damaged file can return happily and
    # only raise later, when the page tree is first walked. Guarding only the
    # construction produces a traceback at len(reader.pages) instead of the
    # intended message.
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        front_matter = " ".join(
            (page.extract_text() or "") for page in reader.pages[:FRONT_MATTER_PAGES]
        )
    except Exception as exc:  # pypdf raises several unrelated types on damage
        raise SystemExit(
            f"\n{path.relative_to(REPO_ROOT)} is {size:,} bytes but pypdf cannot\n"
            f"read it: {type(exc).__name__}: {exc}\n\n"
            "The file is damaged or incomplete. Check the source URL with\n"
            "--inspect, then re-run with --force to refetch."
        ) from exc

    print(f"\n{path.relative_to(REPO_ROOT)}")
    print(f"  {size / 1e6:.1f} MB ({size:,} bytes), {pages} pages")

    # Whitespace is collapsed across the whole front matter before matching, and
    # this is the point rather than tidiness. A licence name is long enough to
    # wrap, and OpenStax's does: the copyright page breaks it right after
    # "licensed under a Creative Commons". Matching line by line therefore cut
    # the sentence in half and reported a false mismatch against the very words
    # that had scrolled onto the next line. Searching one normalised string
    # cannot be defeated by a line break.
    normalised = " ".join(front_matter.split())
    haystack = normalised.lower()

    hits: list[str] = []
    cursor = 0
    while (found := haystack.find("creative commons", cursor)) != -1:
        hits.append(normalised[max(0, found - 60):found + 220].strip())
        cursor = found + 1

    print("\n  Licence text found in the front matter:")
    if not hits:
        print("    (none — read the copyright page yourself before publishing)")
        return
    for passage in dict.fromkeys(hits):
        print(f"    ...{passage}...")

    squashed = "".join(ch for ch in haystack if ch.isalnum())
    if any(form in squashed for form in EXPECTED_LICENCE_FORMS):
        print(f"\n  Matches the expected licence ({EXPECTED_LICENCE}).")
    else:
        print(
            f"\n  WARNING: expected {EXPECTED_LICENCE} and did not find it.\n"
            "  Attribution is a licence obligation. Do not publish until README\n"
            "  and CLAUDE.md agree with what the document actually says."
        )


def inspect(url: str, path: Path) -> None:
    """Report what the server says and what landed on disk, without downloading.

    Exists because a 324 MB fetch is far too expensive to use as a debugging
    loop. When a download arrives at exactly the declared Content-Length and is
    still not a readable PDF, the interesting questions are all answerable from
    the response headers and the last few hundred bytes of the file.
    """
    print(f"URL: {url}\n")
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request) as response:
            print(f"  HTTP {response.status}")
            interesting = (
                "Content-Length", "Content-Type", "Content-Encoding", "Accept-Ranges",
                "ETag", "Last-Modified", "Server", "Via", "X-Cache", "Age",
            )
            for header in interesting:
                value = response.headers.get(header)
                if value:
                    print(f"  {header}: {value}")
    except urllib.error.URLError as exc:
        print(f"  HEAD failed: {exc}")

    # Scan a generous tail, not just the final bytes. A PDF is allowed to carry
    # trailing data after its %%EOF marker, so finding no marker in the last
    # kilobyte proves nothing on its own — the marker could simply be further
    # back. Only its absence across a large tail distinguishes "the served
    # object is truncated" from "the file is fine but ends untidily".
    print(f"\nRange request for the final {TAIL_SCAN_BYTES:,} bytes:")
    ranged = urllib.request.Request(url, headers={"Range": f"bytes=-{TAIL_SCAN_BYTES}"})
    try:
        with urllib.request.urlopen(ranged) as response:
            tail = response.read()
            print(f"  HTTP {response.status} (206 means ranges are supported)")
            print(f"  Content-Range: {response.headers.get('Content-Range')}")
            print(f"  got {len(tail):,} bytes")
            marker = tail.rfind(b"%%EOF")
            if marker == -1:
                print(f"  NO %%EOF anywhere in the last {len(tail):,} bytes")
                print("  -> the object being served is itself incomplete; do not download it")
            else:
                print(f"  %%EOF found {len(tail) - marker:,} bytes from the end")
                print("  -> the served object ends properly; safe to download")
            print(f"  last 60 bytes: {tail[-60:]!r}")
    except urllib.error.URLError as exc:
        print(f"  range request failed: {exc}")

    if not path.exists():
        print(f"\nNo local file at {path}")
        return

    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(16)
        handle.seek(-min(TAIL_SCAN_BYTES, size), 2)
        tail = handle.read()
    print(f"\nLocal file {path.relative_to(REPO_ROOT)}")
    print(f"  {size:,} bytes (multiple of 4096: {size % 4096 == 0})")
    print(f"  first 16 bytes: {head!r}")
    marker = tail.rfind(b"%%EOF")
    print(f"  %%EOF in last {len(tail):,} bytes: " + (f"yes, {len(tail) - marker:,} from end" if marker != -1 else "NO"))
    print(f"  last 60 bytes: {tail[-60:]!r}")


def _report_pending(books) -> None:
    """Say which registered books cannot be fetched yet, and how to fix that.

    A book with no URL is not an error — it is a declared intention. Printing it
    every run is what stops "we are expanding to three books" from quietly
    staying a one-book corpus.
    """
    if not books:
        return
    print(f"\n{len(books)} book(s) registered but not yet fetchable — no URL set:")
    for book in books:
        print(f"  {book.key:<18} {book.title}")
        print(f"  {'':<18} get the PDF link from {book.details_page}")
    print(
        "\nCheck a candidate link BEFORE downloading it:\n"
        "  python scripts/download_sources.py --url <pdf-url> --inspect\n"
        "then set url= for that book in cliopedia/corpus.py. An HTTP 200 is not\n"
        "verification — see CLAUDE.md §8 Rule 7."
    )


def _fetch(book, force: bool) -> None:
    """Download and verify one registered book, skipping what is already there."""
    dest = RAW_DIR / book.filename
    print(f"\n── {book.title} ─────────────────────────────")
    if dest.exists() and not force:
        print(f"{dest.relative_to(REPO_ROOT)} already exists — skipping. Use --force to refetch.")
        report(dest)
        return

    download(book.url, dest)
    verify_is_pdf(dest)
    report(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--book",
        help="fetch one registered book by key: "
        + ", ".join(b.key for b in corpus.CORPUS),
    )
    parser.add_argument("--url", help="fetch an arbitrary PDF instead of a registered book")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="name under data/raw/")
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file exists"
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="diagnose without downloading: server headers plus the local file's tail",
    )
    args = parser.parse_args()

    # --url stays an escape hatch, and is what --inspect is normally pointed at:
    # checking a candidate link is the step that happens *before* it is worth
    # registering. Registered books take the same path once their URL is known.
    if args.url:
        if args.inspect:
            inspect(args.url, RAW_DIR / args.filename)
            return 0
        dest = RAW_DIR / args.filename
        if dest.exists() and not args.force:
            print(f"{dest.relative_to(REPO_ROOT)} already exists — skipping. Use --force to refetch.")
            report(dest)
            return 0
        download(args.url, dest)
        verify_is_pdf(dest)
        report(dest)
        print("\nNext: python -m cliopedia.ingest")
        return 0

    if args.book:
        try:
            book = corpus.find(args.book)
        except KeyError as exc:
            # exc.args[0], not str(exc): str() on a KeyError applies repr to the
            # message and wraps the whole sentence in quotes.
            print(f"\n{exc.args[0]}")
            return 1
        if book.pending:
            print(f"\n{book.title} has no URL set yet.")
            _report_pending([book])
            return 1
        if args.inspect:
            inspect(book.url, RAW_DIR / book.filename)
            return 0
        books = [book]
    else:
        books = list(corpus.downloadable())
        if args.inspect:
            for entry in books:
                inspect(entry.url, RAW_DIR / entry.filename)
            _report_pending(corpus.pending())
            return 0

    if not books:
        print("No registered book has a URL set, so there is nothing to fetch.")
        _report_pending(corpus.pending())
        return 1

    for book in books:
        _fetch(book, force=args.force)

    _report_pending(corpus.pending())

    print(
        f"\n{len(books)} of {len(corpus.CORPUS)} registered book(s) present in data/raw/."
        "\nNext: python -m cliopedia.ingest --rebuild"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
