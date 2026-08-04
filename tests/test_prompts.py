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


def passage(text: str, printed: int = 12, pdf: int = 20) -> Retrieved:
    return Retrieved(
        text=text,
        similarity=0.9,
        source_title="OpenStax U.S. History",
        source_type="secondary",
        locator_kind="page",
        locator_value=pdf,
        printed_page=printed,
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
