"""Tests for prompt construction and the generation wrapper.

No network and no model. What is checkable here is the contract: that the
passages reach the prompt correctly numbered, that the grounding rules are
present, that an empty retrieval refuses without a round trip, and that a
refusal is still recognised when the model punctuates it its own way.

Whether the model *obeys* the prompt is not testable this way — that is what
P3's evaluation harness measures against a real question set.
"""

from __future__ import annotations

import pytest

from cliopedia import generate, prompts
from cliopedia.retrieve import Retrieved


def passage(
    text: str, printed: int = 12, pdf: int = 20, heading: str = ""
) -> Retrieved:
    return Retrieved(
        text=text,
        similarity=0.9,
        source_title="OpenStax U.S. History",
        source_type="secondary",
        locator_kind="page",
        locator_value=pdf,
        printed_page=printed,
        heading=heading,
    )


PASSAGES = [
    passage("The Louisiana Purchase of 1803 doubled the land area.", 12, 20),
    passage("Napoleon offered the territory after losing Saint-Domingue.", 13, 21),
]


def test_passages_are_numbered_from_one():
    text = prompts.format_passages(PASSAGES)
    assert text.startswith("[1] ")
    assert "[2] " in text
    assert "[0]" not in text and "[3]" not in text


def test_passage_text_is_whitespace_collapsed():
    """PDF text carries printed-column line breaks, not sentence structure."""
    wrapped = passage("The Louisiana\nPurchase   of\n1803 doubled")
    assert prompts.format_passages([wrapped]) == "[1] The Louisiana Purchase of 1803 doubled"


def test_a_chapter_heading_is_shown_with_its_passage():
    """The signal that lets the model tell 1929 from 2008."""
    labelled = passage("a massive stock sell-off in late October", heading="25 Key Terms")
    text = prompts.format_passages([labelled])
    assert "chapter 25 Key Terms" in text
    assert "OpenStax U.S. History" in text


def test_the_heading_label_carries_no_page_number():
    """Rule 5 forbids citing pages; do not hand the model one to cite."""
    labelled = passage("text", printed=699, pdf=715, heading="25 Key Terms")
    text = prompts.format_passages([labelled])
    assert "699" not in text
    assert "715" not in text


def test_a_passage_without_a_heading_is_still_numbered_plainly():
    """About one page in ten has no usable footer. It must not break."""
    assert prompts.format_passages([passage("text")]).startswith("[1] text")


def test_two_chapters_are_distinguishable_in_the_prompt():
    """The exact 2008-vs-1929 confusion, in the form the model now sees."""
    text = prompts.format_passages([
        passage("adjustable-rate loans, millions defaulted",
                heading="32 The Challenges of the Twenty-First Century"),
        passage("a massive stock sell-off in late October",
                heading="25 Brother, Can You Spare a Dime? The Great Depression, 1929-1932"),
    ])
    assert "chapter 32 The Challenges of the Twenty-First Century" in text
    assert "The Great Depression, 1929-1932" in text


def test_messages_are_system_then_user():
    messages = prompts.build_messages("What happened?", PASSAGES)
    assert [m["role"] for m in messages] == ["system", "user"]


def test_question_and_passages_reach_the_user_turn():
    messages = prompts.build_messages("  What caused it?  ", PASSAGES)
    user = messages[1]["content"]
    assert "What caused it?" in user
    assert "Louisiana Purchase" in user
    assert "Saint-Domingue" in user


def test_system_prompt_carries_the_grounding_rules():
    """The guarantee the whole project rests on lives in this string."""
    system = prompts.SYSTEM_PROMPT
    assert prompts.REFUSAL in system
    assert "ONLY" in system
    assert "square brackets" in system
    assert "Never invent page numbers" in system


def test_system_prompt_forbids_merging_separate_events():
    """Rule 3, added after a real failure — see the module docstring.

    Asked about the 2008 financial crisis, the model was handed a genuine 2008
    passage alongside two about the 1929 crash and merged all three. Every word
    was from the textbook and every claim was cited; the answer was still false.
    Rule 1 does not cover this, because nothing was invented — true fragments
    were assembled into an untrue whole.
    """
    system = prompts.SYSTEM_PROMPT
    assert "Never combine details from separate events" in system
    # The chapter label is the signal that makes rule 3 actionable: the quoted
    # chunk in the 2008 failure contained no date, so "check the dates" alone
    # gave the model nothing to check.
    assert "different chapters" in system
    assert "judge by the dates and names in the text" in system


def test_the_rule_numbering_stays_consistent_with_its_cross_reference():
    """Rule 7 points at 'rule 2' by number, so inserting a rule can break it."""
    system = prompts.SYSTEM_PROMPT
    # The refusal sentence must still be introduced by rule 2, since rule 7
    # refers to it that way.
    rule_two = system.split("2. ")[1].split("3. ")[0]
    assert prompts.REFUSAL in rule_two
    assert "Do NOT use the sentence from rule 2" in system


def test_empty_retrieval_refuses_without_calling_the_model():
    """No passages is answerable without a network round trip."""

    def exploding_client(*_args, **_kwargs):
        raise AssertionError("the model must not be called with zero passages")

    assert generate.answer("anything", [], client=exploding_client) == prompts.REFUSAL


class _FakeClient:
    """The shape of the OpenAI client, and nothing more."""

    def __init__(self, content: str | None = "An answer [1]."):
        self.content = content
        self.seen: dict = {}
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.seen = kwargs
                message = type("M", (), {"content": outer.content})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": _Completions()})()


def test_answer_passes_model_and_messages_through():
    client = _FakeClient()
    result = generate.answer("What happened?", PASSAGES, client=client, model="llama3.1:8b")
    assert result == "An answer [1]."
    assert client.seen["model"] == "llama3.1:8b"
    assert [m["role"] for m in client.seen["messages"]] == ["system", "user"]
    assert client.seen["temperature"] == generate.TEMPERATURE


def test_empty_model_output_is_an_error_not_an_empty_answer():
    """A blank answer rendered as a sourced answer would be the worst outcome."""
    with pytest.raises(generate.GenerationError):
        generate.answer("q", PASSAGES, client=_FakeClient(content="   "), model="m")


def test_transport_failure_becomes_an_actionable_message():
    class Broken:
        def __init__(self):
            class _C:
                def create(self, **_):
                    raise ConnectionRefusedError("connection refused")
            self.chat = type("Chat", (), {"completions": _C()})()

    with pytest.raises(generate.GenerationError, match="ollama serve"):
        generate.answer("q", PASSAGES, client=Broken(), model="m")


@pytest.mark.parametrize(
    "text",
    [
        "This isn't covered in the source material.",
        "This isnt covered in the source material",          # dropped apostrophe
        '"This isn\'t covered in the source material."',      # quoted
        "This isn't covered in the source material. ",        # trailing space
    ],
)
def test_refusals_are_recognised_despite_punctuation(text):
    """A refusal the UI fails to spot gets rendered as though it were sourced."""
    assert generate.is_refusal(text)


@pytest.mark.parametrize(
    "text",
    [
        "The Louisiana Purchase doubled the size of the United States [1].",
        "The source material covers this in detail [2].",
    ],
)
def test_real_answers_are_not_mistaken_for_refusals(text):
    assert not generate.is_refusal(text)


class _FakeStreamClient:
    """A client whose completions arrive in pieces, like a real stream."""

    def __init__(self, pieces):
        self.pieces = pieces
        self.seen: dict = {}
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.seen = kwargs
                def chunks():
                    for piece in outer.pieces:
                        delta = type("D", (), {"content": piece})()
                        choice = type("C", (), {"delta": delta})()
                        yield type("Ch", (), {"choices": [choice]})()
                return chunks()

        self.chat = type("Chat", (), {"completions": _Completions()})()


def test_stream_yields_pieces_that_join_into_the_answer():
    client = _FakeStreamClient(["The purchase ", "doubled the nation ", "[1]."])
    out = "".join(generate.answer_stream("q", PASSAGES, client=client, model="m"))
    assert out == "The purchase doubled the nation [1]."


def test_stream_requests_streaming_from_the_api():
    client = _FakeStreamClient(["x"])
    list(generate.answer_stream("q", PASSAGES, client=client, model="m"))
    assert client.seen["stream"] is True
    assert client.seen["temperature"] == generate.TEMPERATURE


def test_stream_skips_empty_deltas():
    """Real streams emit chunks with no content — a role header, a final stop."""
    client = _FakeStreamClient(["A", None, "", "B"])
    assert "".join(generate.answer_stream("q", PASSAGES, client=client, model="m")) == "AB"


def test_stream_refuses_without_calling_the_model_when_nothing_retrieved():
    def exploding(*_a, **_k):
        raise AssertionError("must not call the model with zero passages")

    assert list(generate.answer_stream("q", [], client=exploding)) == [prompts.REFUSAL]


def test_stream_transport_failure_is_actionable():
    class Broken:
        def __init__(self):
            class _C:
                def create(self, **_):
                    raise ConnectionRefusedError("refused")
            self.chat = type("Chat", (), {"completions": _C()})()

    with pytest.raises(generate.GenerationError, match="ollama serve"):
        list(generate.answer_stream("q", PASSAGES, client=Broken(), model="m"))


def test_answer_length_is_capped():
    """Generation cost is linear in tokens, so the ceiling bounds latency."""
    client = _FakeClient()
    generate.answer("q", PASSAGES, client=client, model="m")
    assert client.seen["max_tokens"] == generate.MAX_ANSWER_TOKENS


def test_streamed_answer_length_is_capped_too():
    client = _FakeStreamClient(["x"])
    list(generate.answer_stream("q", PASSAGES, client=client, model="m"))
    assert client.seen["max_tokens"] == generate.MAX_ANSWER_TOKENS


REAL_PARTIAL_ANSWER = (
    "The election of Abraham Lincoln to the presidency in 1860 was a watershed "
    "event that proved to be a culmination of increasing tensions between the "
    "proslavery South and the antislavery North [2]. This led to the Confederate "
    "attack on Fort Sumter, marking the beginning of the Civil War [2]. The year "
    "1863 proved decisive for two major reasons [3].\n\n"
    "This isn't covered in the source material."
)


def test_a_cited_answer_ending_with_the_refusal_is_not_a_refusal():
    """Verbatim from a real run, and the bug it caused was severe.

    The model answered in four cited paragraphs, then appended the refusal
    sentence about the part it could not cover. A substring match classified the
    whole answer as a refusal and dropped every source card — presenting fully
    traceable work as though nothing had been found.
    """
    assert not generate.is_refusal(REAL_PARTIAL_ANSWER)


def test_the_partial_answer_still_yields_its_citations():
    from cliopedia.citations import attach

    citations = attach(REAL_PARTIAL_ANSWER, PASSAGES + PASSAGES)
    assert [c.number for c in citations] == [2, 3]


def test_a_bare_refusal_is_still_recognised():
    assert generate.is_refusal("This isn't covered in the source material.")


def test_a_refusal_with_a_small_wrapper_is_still_recognised():
    assert generate.is_refusal("Answer: This isn't covered in the source material.")


def test_prompt_reserves_the_refusal_sentence_for_total_refusals():
    """Rule 6 must not invite the model to use rule 2's sentence while answering."""
    assert "reserved" in prompts.SYSTEM_PROMPT
    assert "Do NOT use the sentence from rule 2" in prompts.SYSTEM_PROMPT


def test_the_prompt_demands_a_citation_per_sentence_not_per_paragraph():
    """Rule 4 was already explicit and still produced 17 uncited sentences per
    10 runs. The failure was specific: the model cited the first sentence of a
    thought and let the rest run on, treating one marker as covering the
    paragraph. That is ordinary academic style and wrong here — the app renders
    one source card per marker, so an uncited sentence gets no card and is
    indistinguishable on screen from an invention.
    """
    system = prompts.SYSTEM_PROMPT
    assert "Every sentence that states a fact carries its own marker" in system
    assert "not the paragraph" in system
    # The worked example must actually demonstrate the repetition it asks for.
    assert system.count("[1].") >= 3


def test_the_prompt_still_exempts_sentences_carrying_no_claim():
    """Otherwise the model would decorate linking phrases with citations."""
    assert "If a sentence states no fact" in prompts.SYSTEM_PROMPT
