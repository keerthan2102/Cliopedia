"""Ask a history question from the terminal — the P0 entrypoint.

    python -m cliopedia.ask "What caused the Louisiana Purchase?"

This is the whole pipeline, written out in one readable function rather than
assembled by a prebuilt chain:

    retrieve  →  build prompt  →  call model  →  attach citations

That explicitness is the point of the project (CLAUDE.md §4.1). Every stage is
visible here, so every stage can be explained.
"""

from __future__ import annotations

import argparse
import textwrap

from cliopedia.citations import attach
from cliopedia.config import ConfigError
from cliopedia.generate import GenerationError, answer, is_refusal
from cliopedia.retrieve import RetrievalError, retrieve

WIDTH = 78


def _wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(
        " ".join(text.split()),
        width=WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def ask(question: str, k: int | None = None, show_snippets: bool = False) -> int:
    passages = retrieve(question, k=k)
    text = answer(question, passages)

    print(f"\n{_wrap(question)}\n")
    print("─" * WIDTH)
    print(_wrap(text))
    print("─" * WIDTH)

    if is_refusal(text):
        # No sources, deliberately. A refusal means no passage supported an
        # answer, so listing the passages that were retrieved anyway would
        # invite the reader to treat them as evidence for something.
        print("\nNo sources — the corpus does not cover this question.")
        print("That is a correct answer, not a failure (CLAUDE.md §4.4).")
        return 0

    citations = attach(text, passages)
    if not citations:
        # The answer cited nothing. Worth saying out loud rather than printing
        # an empty heading: an uncited answer is exactly what this project
        # exists to prevent, so it should look wrong.
        print("\nWARNING: the answer cited no passages, so none of it is traceable.")
        return 1

    print("\nSOURCES")
    for citation in citations:
        print(f"  {citation.label}   (PDF page {citation.pdf_page})")
        if show_snippets:
            print(_wrap(f"“{citation.snippet[:400]}…”", indent="      "))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", help="the history question to answer")
    parser.add_argument("-k", type=int, default=None, help="passages to retrieve")
    parser.add_argument(
        "--snippets",
        action="store_true",
        help="print the verbatim passage behind each citation",
    )
    args = parser.parse_args()

    try:
        return ask(args.question, k=args.k, show_snippets=args.snippets)
    except (RetrievalError, GenerationError, ConfigError) as exc:
        print(f"\n{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
