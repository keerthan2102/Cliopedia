"""Passages + question → a grounded answer.

One client, two backends. Ollama locally and Groq in production both speak the
OpenAI-compatible chat-completions API, so the only difference between them is
three environment variables. There is deliberately no `if backend == "ollama"`
anywhere in this file — see CLAUDE.md §4.2.
"""

from __future__ import annotations

from typing import Sequence

from cliopedia.config import ConfigError, llm_settings
from cliopedia.prompts import REFUSAL, build_messages
from cliopedia.retrieve import Retrieved

# Low but not zero. Near-zero temperature makes the model repeat the passage
# wording almost verbatim, which reads like a bad copy-paste and blurs the line
# between quotation and summary. This is a factual task, so it stays well below
# a conversational default either way.
TEMPERATURE = 0.2


class GenerationError(RuntimeError):
    """Raised when the model cannot be reached or returns nothing usable."""


def make_client():
    """Build the OpenAI-compatible client from configuration.

    `llm_settings()` raises a `ConfigError` naming the missing variable, which
    is a far better failure than a 401 from a remote API — so it is allowed to
    surface rather than being wrapped into something vaguer.
    """
    from openai import OpenAI

    config = llm_settings()
    return OpenAI(base_url=config.base_url, api_key=config.api_key), config.model


def answer(
    question: str,
    passages: Sequence[Retrieved],
    client=None,
    model: str | None = None,
) -> str:
    """Answer `question` using only `passages`.

    Empty retrieval short-circuits to the refusal without calling the model.
    Sending zero passages and trusting the instructions to produce a refusal
    would be paying for a network round trip to be told something already
    known — and relying on the model to get right what we can guarantee.
    """
    if not passages:
        return REFUSAL

    if client is None:
        client, resolved = make_client()
        model = model or resolved
    if model is None:
        raise GenerationError("No model specified and none resolved from config.")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=build_messages(question, passages),
            temperature=TEMPERATURE,
        )
    except ConfigError:
        raise
    except Exception as exc:  # the client raises a family of transport errors
        raise GenerationError(
            f"The model call failed: {type(exc).__name__}: {exc}\n"
            "If running locally, check that `ollama serve` is up and that\n"
            "LLM_BASE_URL matches it — see python -m cliopedia.config."
        ) from exc

    if not response.choices:
        raise GenerationError("The model returned no choices.")

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise GenerationError("The model returned an empty answer.")
    return text


def answer_stream(
    question: str,
    passages: Sequence[Retrieved],
    client=None,
    model: str | None = None,
):
    """Yield the answer piece by piece as the model produces it.

    Same request as `answer()`, read incrementally. This changes nothing about
    how long an answer takes — a language model emits one token at a time and
    each depends on the last, so the total is fixed by the model's speed. What
    it changes is how long the reader stares at nothing: first words in about a
    second instead of a blank panel until the last token lands.

    Citations cannot be attached until the text is complete, so the caller is
    expected to accumulate what it yields and pass the whole answer to
    `citations.attach` at the end.
    """
    if not passages:
        yield REFUSAL
        return

    if client is None:
        client, resolved = make_client()
        model = model or resolved
    if model is None:
        raise GenerationError("No model specified and none resolved from config.")

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=build_messages(question, passages),
            temperature=TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                yield piece
    except ConfigError:
        raise
    except Exception as exc:  # the client raises a family of transport errors
        raise GenerationError(
            f"The model call failed: {type(exc).__name__}: {exc}\n"
            "If running locally, check that `ollama serve` is up and that\n"
            "LLM_BASE_URL matches it — see python -m cliopedia.config."
        ) from exc


def is_refusal(text: str) -> bool:
    """Whether an answer is the 'not in the source material' response.

    Compared loosely on purpose. The prompt asks for an exact sentence, but
    models add a trailing full stop, drop the apostrophe, or wrap it in quotes,
    and a refusal that the UI fails to recognise gets rendered as though it were
    a sourced answer — the one presentation that would be actively misleading.
    """
    squashed = "".join(c for c in text.lower() if c.isalnum())
    return "".join(c for c in REFUSAL.lower() if c.isalnum()) in squashed
