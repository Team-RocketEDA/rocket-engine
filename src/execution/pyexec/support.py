"""Worker substrate pieces: prelude, constants, cell helpers."""

import hashlib
import json
import os
import re
import time
from pathlib import PurePosixPath

from ...interfaces.paths import PathError, join_contained
from ..errors import ExecutionError
from ..runner import pgid_survivors


#: Worker entry filename inside the scratch (tracebacks cite this).
CELL_ENTRY = "cell.py"

#: Scratch-relative ops log the prelude appends; harvested every run.
OPS_LOG_NAME = "__pyexec_ops.jsonl"

#: Worker budget when the call omits one (matches the console runner).
DEFAULT_TIMEOUT_S = 120

#: Explicit overrides stay within these walls.
MIN_TIMEOUT_S = 1

MAX_TIMEOUT_S = 1800

#: Inline scripts are bounded text, never unbounded blobs.
MAX_LINES_BYTES = 65536

#: Project-relative script paths are bounded text too.
MAX_PATH_CHARS = 512

#: Declared harvest artifacts per run (plus the ops log itself).
MAX_ARTIFACTS = 16

#: Deepest traceback frames kept on the exception record.
EXCEPTION_FRAMES = 8

#: Exception message characters kept on the exception record.
EXCEPTION_MESSAGE_CHARS = 2000

_POLL_SLICE_S = 0.05

_KILL_CONFIRM_GRACE_S = 2.0

_KILL_CONFIRM_STEP_S = 0.05

_FRAME_RE = re.compile(r'^\s*File "(.+)", line (\d+)(?:, in (\S+))?')

PRELUDE_TEMPLATE = '''\
# --- rocket-pyexec prelude: pinned trusted bootstrap (do not edit) ---
import json as _json

__PYEXEC_PROJECT__ = @PROJECT_ID@
__PYEXEC_OPS_LOG__ = "@OPS_LOG@"


class _OpRecorder:
    """Prebound `tools`: tools.<op>(**kwargs) records one op call.

    Calls append {"operation", "arguments"} JSON lines to the worker
    scratch ops log; the host replays each through the shared op
    dispatch after the worker exits, so validation and execution are
    exactly what the batch surface runs. Positional args are rejected:
    op calls are keyword-shaped.
    """

    def __init__(self):
        self._index = 0

    def __getattr__(self, operation):
        def call(*args, **kwargs):
            if args:
                raise TypeError(
                    "op calls take keyword arguments only: %s." % operation
                )
            entry = {"operation": operation, "arguments": dict(kwargs)}
            with open(__PYEXEC_OPS_LOG__, "a", encoding="utf-8") as handle:
                handle.write(_json.dumps(entry, sort_keys=True) + "\\n")
            self._index += 1
            return {"state": "recorded", "operation": operation,
                    "index": self._index}

        return call


tools = _OpRecorder()


class _Project:
    """Prebound `project`: local identity plus query recording."""

    def __init__(self, project_id):
        self.id = project_id

    def top_ref(self):
        return {"project": self.id, "ref": "top"}

    def snapshot(self):
        return tools.get_project_snapshot()


project = _Project(__PYEXEC_PROJECT__)


class _Pdk:
    """Prebound `pdk`: worker-local view (discovery runs on the host)."""

    def describe(self):
        return {"project": project.id, "profile": "local",
                "note": "worker-local view;"
                " engine catalog discovery runs on the host."}


pdk = _Pdk()


class _MissingBinding:
    """Honest placeholder: missing profiles report, never fake."""

    def __init__(self, name, hint):
        self._name = name
        self._hint = hint

    def __repr__(self):
        return "<%s unavailable in this worker profile: %s>" % (
            self._name, self._hint)

    def __getattr__(self, item):
        raise RuntimeError(
            "%s unavailable in this worker profile: %s"
            % (self._name, self._hint)
        )

    def __call__(self, *args, **kwargs):
        raise RuntimeError(
            "%s unavailable in this worker profile: %s"
            % (self._name, self._hint)
        )


try:
    import gdsfactory as gf
except Exception as _gf_error:
    gf = _MissingBinding("gf", "gdsfactory not installed (%s)" % _gf_error)

try:
    import numpy as np
except Exception as _np_error:
    np = _MissingBinding("np", "numpy not installed (%s)" % _np_error)


class _Plot:
    """Prebound `plot`: availability flag plus figure helper."""

    def __init__(self):
        try:
            import matplotlib

            matplotlib.use("Agg")
            from matplotlib import pyplot as _pyplot
        except Exception as _plot_error:
            self.available = False
            self._error = str(_plot_error)
            self._pyplot = None
        else:
            self.available = True
            self._error = ""
            self._pyplot = _pyplot

    def __repr__(self):
        if self.available:
            return "<plot (matplotlib available)>"
        return "<plot unavailable in this worker profile: %s>" % self._error

    def figure(self, *args, **kwargs):
        if not self.available:
            raise RuntimeError(
                "plot unavailable in this worker profile: %s" % self._error
            )
        return self._pyplot.figure(*args, **kwargs)


plot = _Plot()
'''

PRELUDE_DIGEST = hashlib.sha256(PRELUDE_TEMPLATE.encode("utf-8")).hexdigest()


def _render_preamble(project_id):
    return PRELUDE_TEMPLATE.replace("@OPS_LOG@", OPS_LOG_NAME).replace(
        "@PROJECT_ID@", json.dumps(project_id)
    )


def build_worker_source(code, project_id="default"):
    """Render the worker source: pinned preamble plus the display cell.

    The project binding renders into the preamble template first, so
    display text is concatenated verbatim afterwards — cell bytes that
    happen to look like the slot stay data. The result ends with the
    exact displayed cell (trailing newline normalized).

    Args:
        code: Display cell text to wrap.
        project_id: Project id rendered into the preamble binding.

    Returns:
        Worker source: pinned preamble plus the display cell.
    """
    display = code if code.endswith("\n") else code + "\n"
    return _render_preamble(project_id) + "\n" + display


def prelude_digest_for(project_id):
    """Environment digest: the rendered preamble, hashed.

    Approval bindings pin this value; a preamble change invalidates
    outstanding approvals instead of running under a new env.

    Args:
        project_id: Project id rendered into the preamble binding.

    Returns:
        Hex sha256 of the rendered preamble.
    """
    return hashlib.sha256(_render_preamble(project_id).encode("utf-8")).hexdigest()


def not_run_verdict(reason):
    """The only verdict python_execute ever carries: NOT_RUN.

    Scripted execution has no qualified evaluator, so a terminal
    script is never PASS and never FAIL — the execution record
    (`state`/`ok`/effects) holds the truth, not the verdict.

    Args:
        reason: Why no check verdict exists (points at the record).

    Returns:
        NOT_RUN verdict mapping with the reason.
    """
    return {"status": "NOT_RUN", "reason": reason}


def resolve_script_path(project_root, path):
    """Resolve a project-relative script path, contained or loud.

    Root-join only: absolute inputs, `..` segments, and symlink
    escapes fail closed; the survivor must be a regular file.

    Args:
        project_root: Project directory the path joins under.
        path: Project-relative script path text.

    Returns:
        Resolved contained path to the script file.

    Raises:
        ExecutionError: invalid_command without a configured root
            or for non-text/empty/oversize input, path_escape for
            absolute inputs, `..` segments, or symlink escapes,
            invalid_path when no regular file survives.
    """
    if project_root is None:
        raise ExecutionError(
            "invalid_command",
            "path mode needs a configured project root; none is set.",
        )
    if not isinstance(path, str) or not path.strip():
        raise ExecutionError(
            "invalid_command",
            f"Script path must be non-empty text, got {path!r}.",
        )
    if len(path) > MAX_PATH_CHARS:
        raise ExecutionError(
            "invalid_command",
            f"Script path exceeds {MAX_PATH_CHARS} characters.",
        )
    try:
        resolved = join_contained(project_root, path)
    except PathError as exc:
        raise ExecutionError(exc.code, str(exc)) from exc
    if not resolved.is_file():
        raise ExecutionError(
            "invalid_path", f"Script file not found: {path}."
        )
    return resolved


def parse_exception(stderr, entry_name=CELL_ENTRY):
    """Parse the last traceback into a bounded exception location.

    Frames cite file/line/function; frames from the worker entry
    file are flagged so callers can point at cell code rather than
    library internals. Bounds: the deepest frames and a truncated
    message survive; anything else is dropped, never dumped whole.

    Args:
        stderr: Cleaned worker stderr text to parse.
        entry_name: Worker entry filename flagging cell frames.

    Returns:
        Exception record with type, message, frames, and a location
            line, or None when no traceback is present.
    """
    if not stderr:
        return None
    lines = stderr.splitlines()
    starts = [
        index for index, line in enumerate(lines)
        if line.strip() == "Traceback (most recent call last):"
    ]
    block = lines[starts[-1] + 1:] if starts else lines
    frames = []
    for line in block:
        match = _FRAME_RE.match(line)
        if match:
            frames.append(match)
    tail = [line for line in block if line.strip()]
    if not tail:
        return None
    parsed = re.match(r"^([A-Za-z_][\w.]*)(?:: (.*))?$", tail[-1].strip())
    if parsed is None or (not starts and not frames):
        return None
    kept = []
    for match in frames[-EXCEPTION_FRAMES:]:
        name, lineno, function = match.groups()
        kept.append({
            "file": name[:200],
            "line": int(lineno),
            "function": function,
            "in_cell": os.path.basename(name) == entry_name,
        })
    cell_frames = [frame for frame in kept if frame["in_cell"]]
    deepest = cell_frames[-1] if cell_frames else (kept[-1] if kept else None)
    if deepest is None:
        location = None
    elif deepest["function"]:
        location = "%s:%d in %s" % (
            deepest["file"], deepest["line"], deepest["function"])
    else:
        location = "%s:%d" % (deepest["file"], deepest["line"])
    return {
        "type": parsed.group(1)[:120],
        "message": (parsed.group(2) or "")[:EXCEPTION_MESSAGE_CHARS],
        "frames": kept,
        "location": location,
    }


def _check_timeout(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExecutionError(
            "invalid_command",
            f"timeout_s must be an int, got {value!r}.",
        )
    if not MIN_TIMEOUT_S <= value <= MAX_TIMEOUT_S:
        raise ExecutionError(
            "invalid_command",
            f"timeout_s must be {MIN_TIMEOUT_S}..{MAX_TIMEOUT_S}, "
            f"got {value}.",
        )
    return value


def _validate_artifacts(artifacts):
    if len(list(artifacts)) > MAX_ARTIFACTS:
        raise ExecutionError(
            "invalid_command",
            f"At most {MAX_ARTIFACTS} artifacts per run.",
        )
    names = []
    for name in artifacts:
        parsed = PurePosixPath(name)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or not parsed.parts
            or str(name) != parsed.as_posix()
        ):
            raise ExecutionError(
                "invalid_reference",
                f"Artifact escapes the scratch: {name}.",
            )
        names.append(parsed.as_posix())
    return names


def _display_exception(parsed, cell_name, cell_line_offset):
    """Remap in_cell frames onto display coordinates.

    Worker tracebacks cite the deleted scratch path plus the
    trusted preamble's line numbers; callers need the submitted
    cell's file and lines instead. Library frames pass through
    untouched.

    Args:
        parsed: Exception record from parse_exception, if any.
        cell_name: Display filename in_cell frames report.
        cell_line_offset: Worker lines preceding the display cell.

    Returns:
        Remapped exception record, or None when no traceback.
    """
    if parsed is None:
        return None
    frames = []
    for frame in parsed["frames"]:
        if frame["in_cell"]:
            frame = {
                **frame,
                "file": cell_name,
                "line": frame["line"] - cell_line_offset,
            }
        frames.append(frame)
    cell_frames = [frame for frame in frames if frame["in_cell"]]
    deepest = cell_frames[-1] if cell_frames else None
    if deepest is None:
        return {**parsed, "frames": frames}
    if deepest["function"]:
        location = "%s:%d in %s" % (
            deepest["file"], deepest["line"], deepest["function"])
    else:
        location = "%s:%d" % (deepest["file"], deepest["line"])
    return {**parsed, "frames": frames, "location": location}


def _interp_chain(python):
    """Interpreter symlink chain, every level (cycle-capped).

    Args:
        python: Interpreter path starting the chain.

    Returns:
        Chain paths from the venv entry to the resolved leaf.
    """
    chain, seen, current = [], set(), python
    for _ in range(32):
        if current in seen:
            break
        seen.add(current)
        chain.append(current)
        if not os.path.islink(current):
            break
        link = os.readlink(current)
        current = (
            link if os.path.isabs(link)
            else os.path.join(os.path.dirname(current), link)
        )
    return chain


def _confirm_tree_dead(pgid, grace_s=_KILL_CONFIRM_GRACE_S):
    """True once no process-group member survives (bounded wait)."""
    deadline = time.monotonic() + grace_s
    while True:
        if not pgid_survivors(pgid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_KILL_CONFIRM_STEP_S)
