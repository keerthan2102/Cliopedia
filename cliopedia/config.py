"""Every environment variable in this project is read here, and nowhere else.

The rule earns its keep at deployment. When the hosted app behaves differently
from the laptop, the cause is almost always configuration — and if variables are
read wherever they happen to be needed, finding it means searching the whole
codebase. One file means one place to look.

Two kinds of setting live here, and they are handled differently on purpose:

  Index settings   CHROMA_DIR, EMBEDDING_MODEL, RETRIEVAL_K
                   These have obviously correct development values, so they
                   default and are validated at import. Reading them can never
                   fail.

  LLM settings     LLM_BASE_URL, LLM_MODEL, LLM_API_KEY
                   These are genuinely environment-specific — there is no
                   sensible default for "which API key" — so they are required,
                   and missing ones raise immediately with the variable named.

The LLM settings are read on demand rather than at import. Ingest, retrieval and
the tests never call a language model, and none of them should fail to import
because a key they will not use is absent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

# Point dotenv at the repo root explicitly rather than letting it search upward
# from the working directory. `streamlit run app.py`, `pytest`, and
# `python -m cliopedia.ask` can all be launched from different directories, and
# configuration that depends on where you happened to be standing is a bug that
# only appears on someone else's machine.
load_dotenv(REPO_ROOT / ".env")


class ConfigError(RuntimeError):
    """Raised when the environment cannot produce a usable configuration.

    A distinct type so callers can tell "you have not configured this" apart
    from "the model call failed", which are very different problems for whoever
    is reading the error.
    """


@dataclass(frozen=True)
class Settings:
    """Everything needed to build or query the index.

    Frozen because configuration read once and then mutated is the source of the
    hardest deployment bugs — the value at the point of failure no longer tells
    you what was configured.
    """

    chroma_dir: Path
    embedding_model: str
    retrieval_k: int


@dataclass(frozen=True)
class LLMSettings:
    """Where to send a prompt, and as whom.

    One shape for both backends. Ollama locally and Groq in production both
    speak the OpenAI-compatible chat-completions API, so switching between them
    changes these three values and nothing else — no branch, no second client.
    """

    base_url: str
    model: str
    api_key: str


def _required(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set.\n"
            f"Locally: copy .env.example to .env and fill it in.\n"
            f"On Streamlit Cloud: set it in the app's secrets, never in the repo."
        )
    return value


def _positive_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}.") from None
    if value < 1:
        raise ConfigError(f"{name} must be at least 1, got {value}.")
    return value


def _resolved_dir(name: str, default: str) -> Path:
    """Resolve a directory setting against the repo root, not the shell's cwd.

    A relative CHROMA_DIR would otherwise point somewhere different depending on
    where the command was launched — and a vector store silently created in the
    wrong place looks exactly like an empty one.
    """
    raw = (os.getenv(name) or "").strip() or default
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def _load_settings() -> Settings:
    return Settings(
        chroma_dir=_resolved_dir("CHROMA_DIR", "data/chroma"),
        # Baked into every vector in the index. Changing it requires a full
        # rebuild: vectors from two different models are coordinates in
        # unrelated spaces, so a stale index read with a new model does not
        # error — it returns confidently wrong citations.
        embedding_model=(os.getenv("EMBEDDING_MODEL") or "").strip()
        or "all-MiniLM-L6-v2",
        # How many chunks are retrieved and handed to the model. Too few starves
        # the answer, too many dilutes the prompt with noise.
        #
        # 6, set from measurement rather than taste: on the 15-question set in
        # eval/questions.txt, hit rate runs 86.7% at k=4, 93.3% at k=5 and
        # 100% at k=6, then stays at 100% through k=7, 8 and 16. Six is the
        # smallest k that retrieves every known-correct page, and paying for
        # more passages past that buys no recall while giving the model more
        # unrelated text to blend in unattributed.
        retrieval_k=_positive_int("RETRIEVAL_K", 6),
    )


settings = _load_settings()


def llm_settings() -> LLMSettings:
    """Read the LLM configuration, failing loudly if it is incomplete.

    Called at the point of use rather than at import so that a missing API key
    cannot break `pytest` or `python -m cliopedia.ingest`, neither of which
    talks to a language model.
    """
    return LLMSettings(
        base_url=_required("LLM_BASE_URL"),
        model=_required("LLM_MODEL"),
        api_key=_required("LLM_API_KEY"),
    )


def _redacted(secret: str) -> str:
    """Never print a key, even to a terminal the author trusts.

    Terminal output ends up in screenshots, in shared logs, and in pasted bug
    reports. Showing the length and last two characters is enough to answer "did
    it read the value I think it did" without disclosing the value.
    """
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{'*' * (len(secret) - 2)}{secret[-2:]}  ({len(secret)} chars)"


def main() -> int:
    """Print the resolved configuration — `python -m cliopedia.config`.

    Exists because "what does this deployment actually think its settings are"
    is the first question worth asking when the hosted app misbehaves, and
    guessing at it from the code is slower than reading it.
    """
    print("Index settings (always available):")
    print(f"  CHROMA_DIR       {settings.chroma_dir}")
    print(f"                   exists: {settings.chroma_dir.exists()}")
    print(f"  EMBEDDING_MODEL  {settings.embedding_model}")
    print(f"  RETRIEVAL_K      {settings.retrieval_k}")

    print("\nLLM settings (required — read on demand):")
    try:
        llm = llm_settings()
    except ConfigError as exc:
        print("  NOT CONFIGURED")
        for line in str(exc).splitlines():
            print(f"    {line}")
        return 1

    print(f"  LLM_BASE_URL     {llm.base_url}")
    print(f"  LLM_MODEL        {llm.model}")
    print(f"  LLM_API_KEY      {_redacted(llm.api_key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
