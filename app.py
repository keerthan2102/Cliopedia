"""Cliopedia's Streamlit UI — P1.

One page, one job. `SPEC.md` §5 fixes the layout: a question box, an answer
carrying [1]/[2] markers, and source cards whose verbatim snippets can be
expanded to check the answer against the textbook.

The design rule behind all of it: a claim the student cannot trace back to a
page is not a citation, so nothing here may present an answer without its
sources attached.

    streamlit run app.py
"""

from __future__ import annotations

import threading

import streamlit as st

from cliopedia.citations import attach
from cliopedia.config import ConfigError, settings
from cliopedia.display import as_excerpt, highlight_markers
from cliopedia.generate import (
    GenerationError,
    answer_stream,
    is_refusal,
    make_client,
)
from cliopedia.retrieve import RetrievalError, retrieve

SOURCE_URL = "https://openstax.org/details/books/us-history"
LICENCE_URL = "https://creativecommons.org/licenses/by-nc-sa/4.0/"

st.set_page_config(page_title="Cliopedia", page_icon="📚", layout="centered")


@st.cache_resource(show_spinner=False)
def load_embeddings():
    """Load the embedding model once per server process, not once per rerun.

    Streamlit re-executes this whole script on every interaction. Without the
    cache, each question would reload a PyTorch model — several seconds of dead
    time per keystroke-triggered rerun.
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=settings.embedding_model)


@st.cache_resource(show_spinner=False)
def load_client():
    """The LLM client, cached for the same reason. Returns (client, model)."""
    return make_client()


@st.cache_resource(show_spinner=False)
def warm_the_model():
    """Ask the language model for one token, in the background, at startup.

    Secondary to warming the embeddings, but still worth doing: Ollama unloads
    a model after five idle minutes by default, so a session returned to later
    pays to load it again. Set OLLAMA_KEEP_ALIVE to change that — `ollama ps`
    shows the deadline in its UNTIL column.

    On a daemon thread so nothing blocks the render, and failures are swallowed
    on purpose: a cold model means a slow first question, not a broken app, and
    the real error surfaces properly when the question is actually asked.
    """

    def _warm() -> None:
        try:
            client, model = make_client()
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
        except Exception:
            pass

    thread = threading.Thread(target=_warm, daemon=True, name="cliopedia-warmup")
    thread.start()
    return thread


st.title("📚 Cliopedia")
st.caption("Ask a history question — every answer cites its source.")

warm_the_model()

with st.form("ask"):
    question = st.text_input(
        "Your question",
        placeholder="What caused the Louisiana Purchase?",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Ask", type="primary")

# Deliberately after the form, and deliberately on the main thread.
#
# This is the real cost of a first question. Loading all-MiniLM-L6-v2 means
# importing PyTorch and reading ~90MB of weights — several seconds — and
# @st.cache_resource then makes every later question skip it. That is precisely
# the observed pattern: slow once, fast afterwards, and unchanged by swapping
# the language model, because the language model was never the cause.
#
# Streamlit sends elements to the browser as the script produces them, so the
# form is already on screen and typeable while this blocks. Doing it on a
# background thread instead would leave the cache unpopulated for the main
# thread, which is the only place it gets read.
load_embeddings()

if submitted and not question.strip():
    st.warning("Type a question first.")

elif submitted:
    try:
        with st.spinner("Searching the textbook…"):
            passages = retrieve(question, embeddings=load_embeddings())
            client, model = load_client()
    except ConfigError as exc:
        st.error("The app is not configured.")
        st.code(str(exc), language=None)
        st.stop()
    except RetrievalError as exc:
        st.error("No searchable index.")
        st.code(str(exc), language=None)
        st.stop()
    except GenerationError as exc:
        st.error("Could not reach the language model.")
        st.code(str(exc), language=None)
        st.stop()

    st.subheader("Answer")

    # Streamed into a placeholder so the reader sees words within a second or
    # two rather than a blank panel for the whole generation. The elapsed time
    # is unchanged — a model emits tokens one at a time and each depends on the
    # last — but waiting with something to read is a different experience.
    answer_box = st.empty()
    try:
        text = answer_box.write_stream(
            answer_stream(question, passages, client=client, model=model)
        )
    except GenerationError as exc:
        answer_box.empty()
        st.error("Could not reach the language model.")
        st.code(str(exc), language=None)
        st.stop()

    if is_refusal(text):
        # Deliberately no sources. Nothing supported an answer, so listing the
        # retrieved passages would invite the reader to treat them as evidence.
        answer_box.info(text)
        st.caption(
            "That is a correct answer, not a failure — this library covers one "
            "textbook, and saying so beats inventing a plausible date."
        )
    else:
        citations = attach(text, passages)
        # Replace the streamed text with the same text, markers emboldened.
        # Styling mid-stream would mean parsing half-written markers.
        answer_box.markdown(highlight_markers(text))

        if not citations:
            # An answer nobody can check is the failure this project exists to
            # prevent, so it is shown as a problem rather than styled as a
            # normal result.
            st.error(
                "This answer cited no passages, so none of it can be traced to "
                "the textbook. Treat it as unverified."
            )
        else:
            st.subheader("Sources")
            for citation in citations:
                with st.expander(
                    f"{citation.label}  ·  PDF page {citation.pdf_page}"
                ):
                    st.markdown(f"> {as_excerpt(citation.snippet)}")
                    st.caption("Retrieved passage, verbatim.")

st.divider()
st.caption(
    f"Source material: [OpenStax *U.S. History*]({SOURCE_URL}), licensed "
    f"[CC BY-NC-SA 4.0]({LICENCE_URL}). The OpenStax name, logo, and cover art "
    "are not covered by that licence. Answers are generated from retrieved "
    "passages by a language model and may contain errors — the citations are "
    "there so you can check them."
)
