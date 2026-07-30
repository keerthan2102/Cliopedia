"""The prompts. Kept out of the logic files on purpose.

Prompt wording is the part of this system most likely to change, and the part
where a small edit has the largest effect on behaviour. Keeping it in one file
means a change to how the model is instructed is a diff you can read, rather
than a string buried three functions deep in `generate.py`.

The grounding guarantee is enforced here and nowhere else. Retrieval decides
*which* passages the model sees; this decides what it is allowed to do with
them.
"""

from __future__ import annotations

from typing import Sequence

from cliopedia.retrieve import Retrieved

# The exact sentence the model must produce when the passages do not answer the
# question. Fixed wording, because the application needs to *recognise* a
# refusal — to render it differently, and to measure how often it happens at P3.
# A model improvising "I'm afraid the provided context doesn't seem to..." is
# the same behaviour but unrecognisable to code.
REFUSAL = "This isn't covered in the source material."

SYSTEM_PROMPT = f"""\
You are a careful research assistant for history students. You answer strictly \
from a set of numbered passages taken from a history textbook.

Rules, in order of importance:

1. Use ONLY the numbered passages provided. Your own knowledge of history is \
not admissible here, however confident you are, and however obviously true a \
fact seems. If it is not in the passages, it does not go in the answer.

2. If the passages do not contain the answer, reply with exactly this sentence \
and nothing else:
{REFUSAL}
This is a correct and useful answer, not a failure. A student is far better \
served by knowing the textbook is silent than by a plausible invention.

3. Cite every factual claim with the number of the passage it came from, in \
square brackets, immediately after the claim. Example:
The purchase doubled the size of the United States [2].
A sentence drawn from two passages carries both: ... [1][3].

4. Never cite a passage number you were not given. Never invent page numbers — \
cite passage numbers only, and the application will turn those into pages.

5. Answer in prose, a few sentences, in a neutral explanatory register. Do not \
add a preamble, do not restate the question, and do not mention "the passages" \
or "the context" — write as though explaining the history itself.

6. If the passages partly answer the question, answer the part they cover and \
say plainly what they do not address. Do not fill the gap.\
"""

# Kept separate from the system prompt so the passages and the question travel
# as the user turn. Chat models are trained to treat the system turn as standing
# instructions and the user turn as the thing to act on; blurring the two makes
# the model likelier to treat the rules themselves as material to summarise.
USER_TEMPLATE = """\
Passages:

{passages}

Question: {question}"""


def format_passages(passages: Sequence[Retrieved]) -> str:
    """Number the passages so the model can cite them by index.

    The numbering is the contract between the answer and the source list: `[2]`
    in the answer text means `passages[1]`, which the UI renders as a source
    card with its page and verbatim snippet. Whitespace is collapsed because
    text extracted from a PDF carries the line breaks of a printed column, not
    of sentences — see CLAUDE.md §8 Rule 8 — and those breaks otherwise read to
    the model as structure that is not there.
    """
    blocks = []
    for number, passage in enumerate(passages, start=1):
        text = " ".join(passage.text.split())
        blocks.append(f"[{number}] {text}")
    return "\n\n".join(blocks)


def build_messages(question: str, passages: Sequence[Retrieved]) -> list[dict]:
    """Assemble the full chat request: standing rules, then this question."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                passages=format_passages(passages),
                question=question.strip(),
            ),
        },
    ]
