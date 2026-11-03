"""Pure ledger primitives shared by the project service."""

import io
import os
import re
import tempfile

from ruamel.yaml import YAML

from ...interfaces.paths import to_unix
from ..errors import ProjectError

DEFAULT_MAX_RETAINED_EVENTS = 10000
_MAX_DOC_BYTES = 1_000_000
_EVENTS_FILENAME = "events.yaml"
_LEDGER_FILENAME = "ledger.yaml"
_SNAPSHOTS_DIRNAME = "snapshots"
_LINKED_CARVEOUT = ".rocket"
_REVISION_RE = re.compile(r"^(.*?)(\d+)$")
_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_RUN_OUTCOMES = ("run_completed", "run_failed")
_REPLAY_EVENTS = ("run_started", "run_interrupted", "run_discarded")
_RESERVED_DOCS = frozenset({_LEDGER_FILENAME, _EVENTS_FILENAME})

# Document prefix owning the five design-truth settings files.
_SETTINGS_DOC_PREFIX = "settings/"


def _advance_revision(revision):
    """Next revision: trailing digits increment, else `-2` is suffixed."""
    match = _REVISION_RE.match(revision or "")
    if match is None:
        return f"{revision}-2"
    return f"{match.group(1)}{int(match.group(2)) + 1}"


def _dump_yaml(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def _atomic_write_text(path, text):
    """Write through a sibling temp file, then rename into place."""
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_write_bytes(path, data):
    """Write bytes through a sibling temp file, then rename."""
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _canonical_doc_path(path):
    """Canonical unix document path; rejects escapes and addresses.

    Args:
        path: Caller-supplied document path.

    Returns:
        Canonical slash-joined path with dot and empty segments
        dropped.

    Raises:
        ProjectError: invalid_path for a non-text, empty, or
            directory path; path_escape for an absolute path or
            one containing `..`. Every message names the supplied
            path.
    """
    if not isinstance(path, str):
        raise ProjectError(
            "invalid_path", f"Document path must be text, got {path!r}."
        )
    unix = to_unix(path)
    if unix == "" or unix.endswith("/"):
        raise ProjectError(
            "invalid_path", f"Bad document path: {path!r}."
        )
    if unix.startswith("/"):
        raise ProjectError(
            "path_escape", f"Absolute document path: {path!r}."
        )
    parts = [p for p in unix.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ProjectError(
            "path_escape", f"Document path escapes: {path!r}."
        )
    canonical = "/".join(parts)
    if canonical == "":
        raise ProjectError(
            "invalid_path", f"Bad document path: {path!r}."
        )
    return canonical


def _check_reserved_doc(canonical, original):
    """Reject engine-owned document paths.

    Args:
        canonical: Canonical document path.
        original: Caller-supplied path for error messages.

    Raises:
        ProjectError: invalid_path when the path names the ledger,
            the event log, or anything under `runs/` or
            `snapshots/`.
    """
    if (
        canonical in _RESERVED_DOCS
        or canonical == "runs"
        or canonical.startswith("runs/")
        or canonical == _SNAPSHOTS_DIRNAME
        or canonical.startswith(_SNAPSHOTS_DIRNAME + "/")
    ):
        raise ProjectError(
            "invalid_path",
            f"Engine-owned path is not a document: {original!r}.",
        )


def _canonical_prefix(prefix):
    """Canonical list filter; empty means no filtering.

    Args:
        prefix: Caller-supplied prefix or None.

    Returns:
        Canonical prefix string ("" matches everything).

    Raises:
        ProjectError: invalid_path for a non-text prefix;
            path_escape for an absolute prefix or one
            containing `..`.
    """
    if prefix is None:
        return ""
    if not isinstance(prefix, str):
        raise ProjectError(
            "invalid_path", f"Prefix must be text, got {prefix!r}."
        )
    unix = to_unix(prefix)
    if unix.startswith("/"):
        raise ProjectError(
            "path_escape", f"Absolute prefix: {prefix!r}."
        )
    parts = [p for p in unix.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ProjectError(
            "path_escape", f"Prefix escapes: {prefix!r}."
        )
    return "/".join(parts)
