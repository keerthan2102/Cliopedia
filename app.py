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

import streamlit as st

from cliopedia.citations import attach
from cliopedia.config import ConfigError, settings
from cliopedia.display import as_excerpt, highlight_markers
from cliopedia.generate import GenerationError, answer, is_refusal, make_client
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


st.title("📚 Cliopedia")
st.caption("Ask a history question — every answer cites its source.")

with st.form("ask"):
    question = st.text_input(
        "Your question",
        placeholder="What caused the Louisiana Purchase?",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Ask", type="primary")

if submitted and not question.strip():
    st.warning("Type a question first.")

elif submitted:
    try:
        with st.spinner("Searching the textbook…"):
            passages = retrieve(question, embeddings=load_embeddings())
        with st.spinner("Reading the passages…"):
            client, model = load_client()
            text = answer(question, passages, client=client, model=model)
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

    if is_refusal(text):
        # Deliberately no sources. Nothing supported an answer, so listing the
        # retrieved passages would invite the reader to treat them as evidence.
        st.info(text)
        st.caption(
            "That is a correct answer, not a failure — this library covers one "
            "textbook, and saying so beats inventing a plausible date."
        )
    else:
        citations = attach(text, passages)
        st.markdown(highlight_markers(text))

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
