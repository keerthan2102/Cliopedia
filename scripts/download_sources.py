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

# The OpenStax U.S. History PDF.
#
# Verified working on 2026-07-29: serves a 324 MB print-quality PDF. If it ever
# 404s, get the current link from the book's page and pass it with --url:
#     https://openstax.org/details/books/us-history
# then correct the constant below in the same commit that records the fix.
DEFAULT_URL = "https://assets.openstax.org/oscms-prodcms/media/documents/USHistory-OP.pdf"
DEFAULT_FILENAME = "openstax-us-history.pdf"

# What the licence line is expected to say, per CLAUDE.md §8 Rule 3.
EXPECTED_LICENCE = "Attribution-NonCommercial-ShareAlike"

# How many leading pages to scan for the copyright notice. OpenStax front matter
# puts it within the first few pages; 12 is slack, not a measurement.
FRONT_MATTER_PAGES = 12


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
            "If OpenStax has moved the file, find the current PDF link on\n"
            "https://openstax.org/details/books/us-history and re-run with\n"
            "--url <link>, then fix DEFAULT_URL in this file."
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
    with path.open("rb") as handle:
        magic = handle.read(5)
    if magic != b"%PDF-":
        size = path.stat().st_size
        path.unlink()
        raise SystemExit(
            f"Downloaded file is not a PDF (starts with {magic!r}, {size} bytes).\n"
            "That usually means the URL served an error page. Deleted it."
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
    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # pypdf raises several unrelated types on damage
        raise SystemExit(
            f"\n{path.relative_to(REPO_ROOT)} is {size:,} bytes but pypdf cannot\n"
            f"read it: {type(exc).__name__}: {exc}\n\n"
            "A PDF that starts correctly but has no end-of-file marker is a\n"
            "truncated download. Re-run with --force to refetch it."
        ) from exc

    print(f"\n{path.relative_to(REPO_ROOT)}")
    print(f"  {size / 1e6:.1f} MB ({size:,} bytes), {len(reader.pages)} pages")

    hits: list[str] = []
    for page in reader.pages[:FRONT_MATTER_PAGES]:
        for line in (page.extract_text() or "").splitlines():
            if "creative commons" in line.lower() or "creativecommons.org" in line.lower():
                hits.append(line.strip())

    print("\n  Licence lines found in the front matter:")
    if not hits:
        print("    (none — read the copyright page yourself before publishing)")
        return
    for line in dict.fromkeys(hits):
        print(f"    {line}")

    if any(EXPECTED_LICENCE.lower() in line.lower() for line in hits):
        print(f"\n  Matches the expected licence ({EXPECTED_LICENCE}).")
    else:
        print(
            f"\n  WARNING: expected {EXPECTED_LICENCE!r} and did not find it.\n"
            "  Attribution is a licence obligation. Do not publish until README\n"
            "  and CLAUDE.md agree with what the document actually says."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL, help="PDF to fetch")
    parser.add_argument("--filename", default=DEFAULT_FILENAME, help="name under data/raw/")
    parser.add_argument(
        "--force", action="store_true", help="re-download even if the file exists"
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    sys.exit(main())
