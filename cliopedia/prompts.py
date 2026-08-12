"""The prompts. Kept out of the logic files on purpose.

Prompt wording is the part of this system most likely to change, and the part
where a small edit has the largest effect on behaviour. Keeping it in one file
means a change to how the model is instructed is a diff you can read, rather
than a string buried three functions deep in `generate.py`.

The grounding guarantee is enforced here and nowhere else. Retrieval decides
*which* passages the model sees; this decides what it is allowed to do with
them.

Rule 3 exists because of a specific observed failure, and is worth
understanding before anyone trims it. Asked "What happened during the 2008
financial crisis?", the app retrieved U.S. History p.896 — genuinely about
Lehman Brothers and Bear Stearns in 2008 — alongside pp.679 and 699, which are
the causes of the 1929 crash and the Great Depression key-terms glossary. The
model merged all three into one account of 2008, complete with "a massive stock
sell-off in late October" and a 40 percent fall, which is Black Tuesday 1929.
Every word came from the textbook. Every claim carried a citation. The answer
was still false, and the citations made it *more* believable.

That is the failure mode this file has to prevent: not invention from memory,
which rule 1 covers, but assembly of true fragments into an untrue whole.
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

3. The passages are selected by similarity of wording, NOT by whether they \
describe the event you were asked about. Some will be about a different event, \
period or place that merely uses similar language — a passage about one \
financial panic can arrive beside a passage about another one a century \
earlier.

Most passages are labelled with the book and chapter they came from. **Use that \
label.** Passages from different chapters of the same book are usually about \
different periods, and a chapter title often names its era outright. If the \
question is about one period and a passage comes from a chapter about another, \
that passage does not belong in your answer, however closely its wording \
matches. Where a label is missing, judge by the dates and names in the text.

Never combine details from separate events into a single account. A date, a \
figure or a cause taken from the wrong episode is a fabrication even though \
every word of it came from the textbook — and the citation makes that error \
more convincing, not less.

4. Cite every factual claim with the number of the passage it came from, in \
square brackets, immediately after the claim. Example:
The purchase doubled the size of the United States [2].
A sentence drawn from two passages carries both: ... [1][3].

**Every sentence that states a fact carries its own marker**, including one \
continuing the point before it. A citation covers the sentence it sits in and \
nothing further — not the paragraph, not the idea. So consecutive sentences \
drawn from the same passage each end in the same number:

Millions defaulted on adjustable-rate loans [1]. Without access to credit, \
consumer spending declined [1]. International trade slowed, hurting many \
American businesses [1].

That repetition is correct, not clumsy. Do NOT write the first sentence with a \
citation and let the rest of the paragraph run on without one — that is the \
most common way this goes wrong, and it is invisible to you and fatal to the \
reader: the application renders one source card per marker, so a sentence \
without a marker gets no card and there is nothing for a student to check it \
against. An uncited sentence is indistinguishable, on screen, from something \
you invented.

If a sentence states no fact — a linking phrase, a summary of what you just \
said — it needs no citation. If you cannot point to the passage a sentence \
came from, do not write the sentence.

5. Never cite a passage number you were not given. Never invent page numbers — \
cite passage numbers only, and the application will turn those into pages.

6. Answer in prose, a few sentences, in a neutral explanatory register. Do not \
add a preamble, do not restate the question, and do not mention "the passages" \
or "the context" — write as though explaining the history itself.

7. If the passages partly answer the question, answer the part they cover and \
say plainly what they do not address, in your own words. Do not fill the gap. \
Do NOT use the sentence from rule 2 in this case — that sentence is reserved \
for when the passages answer nothing at all, and the application treats it as a \
signal that no sources exist.\
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
        # The chapter heading, when the page had one, is what lets the model
        # tell two similar-sounding passages apart. It is shown WITHOUT the page
        # number on purpose: a page number is a thing the model could cite, and
        # rule 5 forbids that — the application turns passage indices into pages.
        # A chapter title carries the same disambiguating force with nothing
        # citable in it.
        label = f"[{number}]"
        if passage.heading:
            label = f"[{number}] (from {passage.source_title}, chapter {passage.heading})"
        blocks.append(f"{label} {text}")
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
