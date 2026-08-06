"""What `--rebuild` must do when the old index will not delete.

Deleting the index is the one step in ingest that touches something outside
this process's control. On Windows a file held open by another program cannot
be removed, and `shutil.rmtree` deletes as it walks — so the failure lands
halfway, leaving a directory that is neither empty nor a usable index.

That state is dangerous rather than merely inconvenient: `open_index()` treats
any non-empty directory as an index, so a half-deleted one is queried as if it
were whole, and answers cite pages from segments that no longer exist.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from cliopedia.ingest import IngestError, _remove_index


def _denied(path: Path) -> PermissionError:
    """A PermissionError shaped like the one Windows raises (WinError 5)."""
    error = PermissionError(5, "Access is denied")
    error.filename = str(path / "1460f369-9083-448e-a50b-ca47a3f09f56")
    return error


def test_removes_the_index_when_nothing_holds_it(tmp_path):
    chroma_dir = tmp_path / "chroma"
    (chroma_dir / "segment").mkdir(parents=True)
    (chroma_dir / "chroma.sqlite3").write_text("catalogue")

    _remove_index(chroma_dir)

    assert not chroma_dir.exists()


def test_a_locked_index_raises_ingest_error_not_a_traceback(tmp_path):
    """A PermissionError escaping to the top is a stack trace where the reader
    needs an instruction. It must arrive as the error type this module uses for
    "your corpus or index is not in a usable state"."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    with patch.object(shutil, "rmtree", side_effect=_denied(chroma_dir)):
        with pytest.raises(IngestError):
            _remove_index(chroma_dir)


def test_the_lock_message_names_the_file_and_the_way_out(tmp_path):
    """The message has one job: turn "access denied" into a next action.

    It must say which path was locked — the caller cannot guess which of
    hundreds of segment files it was — and it must warn that the index is now
    partly deleted, because the obvious response otherwise is to re-run the
    query and trust what comes back.
    """
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    with patch.object(shutil, "rmtree", side_effect=_denied(chroma_dir)):
        with pytest.raises(IngestError) as exc:
            _remove_index(chroma_dir)

    message = str(exc.value)
    assert "1460f369-9083-448e-a50b-ca47a3f09f56" in message, "must name the locked path"
    assert "PARTLY deleted" in message, "must warn the index is now invalid"
    assert "streamlit" in message.lower(), "must name the usual culprit"
    assert "OneDrive" in message, "this repo lives inside a OneDrive folder"
    assert "--rebuild" in message, "must say how to resume"
    # Every platform the author might be on gets a literal command, because the
    # recovery is manual and a half-remembered flag is how a whole data/ folder
    # gets deleted instead of one index.
    assert "rmdir /s /q" in message
    assert "Remove-Item -Recurse -Force" in message
    assert "rm -rf" in message


def test_the_original_error_is_kept_as_the_cause(tmp_path):
    """`raise ... from exc` keeps the OS error reachable. A friendlier message
    that discards the underlying errno makes a genuinely odd failure — a
    corrupted filesystem, say — indistinguishable from a routine lock."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    with patch.object(shutil, "rmtree", side_effect=_denied(chroma_dir)):
        with pytest.raises(IngestError) as exc:
            _remove_index(chroma_dir)

    assert isinstance(exc.value.__cause__, PermissionError)
