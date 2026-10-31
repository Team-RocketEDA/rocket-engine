"""Headless Python execution (PYTHON-EXEC): inline lines + project files.

First-class scripted execution on the prepared worker substrate the
stdio console shares: every `python_execute` call runs in a fresh
Bubblewrap-confined worker (pinned interpreter, PDK access, tool
binaries) with the console prebounds (`project/tools/pdk/gf/np/plot`)
available and zero setup. Exactly two input modes exist — `lines`
(inline script text) and `path` (a project-contained script file) —
and nothing else: no shells, no absolute host paths.

Approval resolves per python-console-spec, never inside the run:
`pending_approval` / `approved` / `denied` / `expired` are approval
states, distinct from the job states (`queued` / `running` /
`completed` / `cancelled`) the execution service owns. Agent calls
request approval; only the human UI route resolves it
(`resolve_approval(via="ui")`) — MCP self-approval raises
`approval_forbidden`. Denial and expiry create no run.

Completion is never a check verdict: every terminal record carries
`state`/`ok` plus a `NOT_RUN` verdict — zero exit is not PASS, read
the execution record. Effects (op calls the cell recorded) replay
through the shared op dispatch after the worker exits, and their
child `run_ids` ride on the record as structured data.
"""

import hashlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path, PurePosixPath

from ruamel.yaml import YAML

from ..interfaces.paths import PathError, join_contained
from .errors import ExecutionError
from .runner import BwrapRunner, clean_stream, pgid_survivors
from .service import ExecutionService
from .worker import CredentialGate, worker_profile

__all__ = [
    "CELL_ENTRY",
    "DEFAULT_APPROVAL_TTL_S",
    "DEFAULT_TIMEOUT_S",
    "MAX_ARTIFACTS",
    "MAX_LINES_BYTES",
    "MAX_PATH_CHARS",
    "MAX_TIMEOUT_S",
    "MCP_INPUT_SCHEMA",
    "MIN_TIMEOUT_S",
    "MODES",
    "OPS_LOG_NAME",
    "PRELUDE_DIGEST",
    "PRELUDE_TEMPLATE",
    "PythonExecRunner",
    "PythonExecService",
    "build_worker_source",
    "not_run_verdict",
    "parse_exception",
    "prelude_digest_for",
    "resolve_script_path",
]

#: Exactly two input modes: inline script text, or a project file.
MODES = ("lines", "path")

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
#: Pending approvals lapse after this long without a UI decision.
DEFAULT_APPROVAL_TTL_S = 900
#: Deepest traceback frames kept on the exception record.
EXCEPTION_FRAMES = 8
#: Exception message characters kept on the exception record.
EXCEPTION_MESSAGE_CHARS = 2000

_POLL_SLICE_S = 0.05
_KILL_CONFIRM_GRACE_S = 2.0
_KILL_CONFIRM_STEP_S = 0.05

MCP_INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Execute a Python cell in a fresh prepared worker. Exactly one "
        "of lines (inline script text) or path (a project-contained "
        "script file) is required; the other must be absent."
    ),
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["lines", "path"],
            "description": "Input mode: inline script text or project file.",
        },
        "lines": {
            "type": "string",
            "maxLength": MAX_LINES_BYTES,
            "description": "Inline script text (lines mode only).",
        },
        "path": {
            "type": "string",
            "maxLength": MAX_PATH_CHARS,
            "description": (
                "Project-relative script path (path mode only); "
                "traversal and out-of-project paths are rejected."
            ),
        },
        "timeout_s": {
            "type": "integer",
            "minimum": MIN_TIMEOUT_S,
            "maximum": MAX_TIMEOUT_S,
            "description": "Worker budget in seconds (default 120).",
        },
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_ARTIFACTS,
            "description": "Scratch-relative paths to harvest.",
        },
        "expected_revision": {
            "type": "string",
            "description": "Project revision the approval binds.",
        },
    },
    "required": ["mode"],
    "oneOf": [
        {
            "properties": {"mode": {"const": "lines"}},
            "required": ["mode", "lines"],
            "not": {"required": ["path"]},
        },
        {
            "properties": {"mode": {"const": "path"}},
            "required": ["mode", "path"],
            "not": {"required": ["lines"]},
        },
    ],
}

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


_FRAME_RE = re.compile(r'^\s*File "(.+)", line (\d+)(?:, in (\S+))?')


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


class PythonExecRunner:
    """Fresh prepared workers on the console's sandbox substrate.

    Same confinement machinery as console cells (`BwrapRunner` +
    `worker_profile` + `CredentialGate`): one worker per run, a
    scratch-only write area, execution-scoped IPC credentials, and
    revocation plus confirmed tree-kill before every terminal
    record. The interpreter is the prepared profile's Python (with
    gdsfactory/numpy where the profile installs them), bound
    read-only into the sandbox — never the host interpreter, and
    with no host fallback when isolation is unprovable.

    Args:
        python: Prepared interpreter path; the running engine's
            interpreter when omitted.
        extra_tool_paths: Extra resolved paths ro-bound with the
            profile (tool binaries on PATH inside the worker).
        profile: Full sandbox profile override; worker_profile()
            over the interpreter when omitted.
        binary: bwrap binary name or path.
        artifacts_root: Harvest destination root; temp dir default.
        default_timeout_s: Worker budget when the call omits one.
        require_net: Refuse admission unless net isolation probes;
            degrade loudly to user-only otherwise.
    """

    def __init__(self, python=None, extra_tool_paths=(), profile=None,
                 binary="bwrap", artifacts_root=None,
                 default_timeout_s=DEFAULT_TIMEOUT_S, require_net=False):
        self._python = python or sys.executable
        if profile is None:
            # venv interpreters are often symlink chains into a
            # manager-owned install (uv): the kernel traverses every
            # dirent inside the sandbox, so cover each level's root
            # or exec fails with ENOENT.
            tool_paths = _interp_chain(self._python)
            tool_paths.extend(extra_tool_paths)
            base = worker_profile(tool_paths=tool_paths)
            env = dict(base.get("env", {}))
            env["MPLBACKEND"] = "Agg"
            env["MPLCONFIGDIR"] = "/tmp"
            base["env"] = env
            self._base_profile = base
        else:
            self._base_profile = dict(profile)
        self._binary = binary
        self._gate = CredentialGate()
        self._default_timeout_s = default_timeout_s
        self._artifacts_root = Path(
            artifacts_root
            if artifacts_root is not None
            else Path(tempfile.gettempdir()) / "rocketeda_pyexec_artifacts"
        )
        self._admission, self._runner = self._preflight(require_net)

    def _preflight(self, require_net):
        try:
            runner = BwrapRunner(self._base_profile, binary=self._binary)
            runner.preflight()
        except ExecutionError as exc:
            return (
                {"admitted": False, "reason": str(exc),
                 "network_isolated": False},
                None,
            )
        network_isolated = False
        try:
            netted = dict(self._base_profile)
            namespaces = list(netted.get("namespaces", ["user"]))
            if "net" not in namespaces:
                namespaces.append("net")
            netted["namespaces"] = namespaces
            BwrapRunner(netted, binary=self._binary).preflight()
            network_isolated = True
            runner = BwrapRunner(netted, binary=self._binary)
        except ExecutionError:
            if require_net:
                return (
                    {
                        "admitted": False,
                        "reason": "network isolation unprovable: "
                        "net namespace refused by the kernel.",
                        "network_isolated": False,
                    },
                    None,
                )
        try:
            self._prove_python(runner)
        except ExecutionError as exc:
            return (
                {"admitted": False, "reason": str(exc),
                 "network_isolated": False},
                None,
            )
        return (
            {"admitted": True, "reason": None,
             "network_isolated": network_isolated},
            runner,
        )

    def _prove_python(self, runner):
        with tempfile.TemporaryDirectory(prefix="pyexec_python_probe_") as tmp:
            try:
                proc = runner.run(
                    [self._python, "-c", "pass"], tmp, timeout_s=30
                )
            except ExecutionError as exc:
                raise ExecutionError(
                    "isolation_unavailable",
                    f"sandbox python unavailable: {exc}.",
                ) from exc
        if proc.returncode != 0:
            raise ExecutionError(
                "isolation_unavailable",
                f"sandbox python unavailable: exit {proc.returncode}.",
            )

    @property
    def admission(self):
        """Isolation admission record, stamped on every result.

        Returns:
            Admission mapping copy (admitted, reason,
                network_isolated).
        """
        return dict(self._admission)

    @property
    def gate(self):
        """Execution-scoped credential gate for worker IPC.

        Returns:
            Credential gate.
        """
        return self._gate

    @property
    def python(self):
        """Prepared interpreter path this runner executes.

        Returns:
            Interpreter path string.
        """
        return self._python

    def run(self, source, run_id=None, timeout_s=None, artifacts=(),
            extra_env=None, on_live=None, is_cancelled=None,
            cell_name=CELL_ENTRY, cell_line_offset=0):
        """Run one source text in a fresh worker; return its record.

        Pre-spawn checks precede any execution, cheapest first:
        artifact paths, then timeout shape, then isolation
        admission. Without admission the call raises
        isolation_unavailable and nothing runs anywhere — no host
        fallback, ever. The wait polls in short slices so a
        cancelled job kills its worker tree promptly instead of
        sleeping out the budget.

        Args:
            source: Full worker source to execute.
            run_id: Execution id; generated when omitted.
            timeout_s: Worker budget; runner default when omitted.
            artifacts: Scratch-relative paths to harvest.
            extra_env: Per-run env additions inside the worker.
            on_live: Optional callback while the worker is live.
            is_cancelled: Optional zero-arg callable; a true
                reading kills the worker and reports cancelled.
            cell_name: Display filename in_cell frames report.
            cell_line_offset: Worker lines preceding the display
                cell; in_cell frames shift back by this much so
                the location points at submitted code, never at
                the deleted scratch or the trusted preamble.

        Returns:
            Terminal worker record (completed/failed/timeout/
                crashed/cancelled) with bounded stdio, the parsed
                exception location, artifacts, and kill
                confirmations.

        Raises:
            ExecutionError: invalid_reference for escaping artifact
                paths, invalid_command for a malformed timeout,
                isolation_unavailable without admission,
                runner_unavailable when the worker cannot spawn.
        """
        names = _validate_artifacts(artifacts)
        budget = self._default_timeout_s if timeout_s is None else _check_timeout(timeout_s)
        if not self._admission["admitted"]:
            raise ExecutionError(
                "isolation_unavailable", self._admission["reason"]
            )
        scratch = tempfile.mkdtemp(prefix="rocketeda_pyexec_")
        run_id = run_id or uuid.uuid4().hex
        token = self._gate.issue(run_id)
        Path(scratch, CELL_ENTRY).write_text(source, encoding="utf-8")
        env = {
            "ROCKETEDA_RUN_ID": run_id,
            "ROCKETEDA_PYEXEC_TOKEN": token,
            "HOME": scratch,
        }
        env.update(extra_env or {})
        argv = self._runner.argv_for(
            scratch, [self._python, CELL_ENTRY], extra_env=env,
        )
        try:
            try:
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=scratch,
                    start_new_session=True,
                )
            except OSError as exc:
                raise ExecutionError(
                    "runner_unavailable", f"Worker spawn failed: {exc}."
                ) from exc
            try:
                if on_live is not None:
                    on_live(run_id, token)
                out_bytes, err_bytes, outcome = self._wait(
                    proc, budget, is_cancelled
                )
                if outcome == "timeout":
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="timeout", ok=False,
                        reason=f"timeout after {budget}s; partials retained.",
                        exit_code=None, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                if outcome == "cancelled":
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="cancelled", ok=False,
                        reason="cancelled via the job surface; "
                        "worker tree killed.",
                        exit_code=None, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                returncode = proc.returncode
                if returncode == 0:
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="completed", ok=True, reason=None,
                        exit_code=0, partial=False, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                # bwrap reports child signal death as 128+signo (the
                # shell convention), so exits above 128 read as crashes.
                # A script deliberately exiting 129+ misreads the same
                # way; both land ok False, so the ambiguity never
                # fake-passes.
                if returncode < 0 or returncode > 128:
                    signo = -returncode if returncode < 0 else returncode - 128
                    return self._finish(
                        run_id, scratch, names, out_bytes, err_bytes,
                        state="crashed", ok=False,
                        reason=f"death by signal {signo}.",
                        exit_code=returncode, partial=True, pgid=proc.pid,
                        cell_name=cell_name,
                        cell_line_offset=cell_line_offset,
                    )
                return self._finish(
                    run_id, scratch, names, out_bytes, err_bytes,
                    state="failed", ok=False,
                    reason=f"exit {returncode}.",
                    exit_code=returncode, partial=False, pgid=proc.pid,
                    cell_name=cell_name,
                    cell_line_offset=cell_line_offset,
                )
            finally:
                if proc.poll() is None:
                    self._terminate(proc)
                    proc.communicate()
        finally:
            self._gate.revoke(run_id)
            shutil.rmtree(scratch, ignore_errors=True)

    @staticmethod
    def _wait(proc, budget, is_cancelled):
        start = time.monotonic()
        while True:
            if is_cancelled is not None and is_cancelled():
                PythonExecRunner._terminate(proc)
                out_bytes, err_bytes = proc.communicate()
                return out_bytes, err_bytes, "cancelled"
            remaining = budget - (time.monotonic() - start)
            if remaining <= 0:
                PythonExecRunner._terminate(proc)
                out_bytes, err_bytes = proc.communicate()
                return out_bytes, err_bytes, "timeout"
            try:
                out_bytes, err_bytes = proc.communicate(
                    timeout=min(_POLL_SLICE_S, remaining)
                )
            except subprocess.TimeoutExpired:
                continue
            return out_bytes, err_bytes, "exited"

    @staticmethod
    def _terminate(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
        proc.wait()

    def _finish(self, run_id, scratch, names, out_bytes, err_bytes,
                state, ok, reason, exit_code, partial, pgid,
                cell_name=CELL_ENTRY, cell_line_offset=0):
        # Revocation + tree-kill confirmation strictly precede the
        # terminal record (and therefore the next run).
        self._gate.revoke(run_id)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        tree_killed = _confirm_tree_dead(pgid)
        harvested, rejected = self._harvest(run_id, scratch, names)
        stdout = clean_stream(out_bytes)
        stderr = clean_stream(err_bytes)
        exception = _display_exception(
            parse_exception(stderr), cell_name, cell_line_offset)
        return {
            "run_id": run_id,
            "state": state,
            "ok": ok,
            "reason": reason,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "partial": partial,
            "exception": exception,
            "artifacts": harvested,
            "rejected_artifacts": rejected,
            "network_isolated": self._admission["network_isolated"],
            "credential_revoked": True,
            "tree_killed": tree_killed,
            "spawned": True,
            "scratch": scratch,
        }

    def _harvest(self, run_id, scratch, names):
        base = Path(scratch).resolve()
        harvested, rejected = [], []
        for name in names:
            target = (base / name).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                rejected.append(name)
                continue
            digest = hashlib.sha256()
            with open(target, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
            dest = self._artifacts_root / run_id / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, dest)
            harvested.append(
                {
                    "name": name,
                    "path": str(dest),
                    "bytes": dest.stat().st_size,
                    "sha256": digest.hexdigest(),
                }
            )
        return harvested, rejected


class PythonExecService:
    """Approval-gated headless execution: request, resolve, run, cancel.

    Agents request executions; the human UI route resolves the
    approval; admitted runs execute in fresh prepared workers and
    their recorded effects replay through the shared op dispatch.
    Approval states (`pending_approval`/`approved`/`denied`/
    `expired`) live in this service's approval ledger, never in the
    job records — denial and expiry create no run, and a pending
    approval addresses no runnable job.

    History persists under the service root (`cells/<id>.py` holds
    the exact submitted cell, `executions/<id>.yaml` the terminal
    record, `approvals/<id>.yaml` the approval audit trail).

    Args:
        project_id: Project executions are bound to.
        actor: Attribution recorded on approvals and runs.
        root: Service state dir; temp dir default.
        execution: Job surface owning run records; an in-memory
            execution service when omitted.
        project_root: Project dir path mode resolves inside; path
            mode refuses loudly without one.
        runner: Worker runner; a prepared runner when omitted
            (built lazily, on the first admitted run).
        dispatcher: Op dispatch effects replay through
            (`execute(operation, arguments)`); without one, ops
            are recorded but never replayed, loudly marked.
        approval_ttl_s: Pending approvals lapse after this long.
        clock: Monotonic clock seconds source (tests inject fakes).
        revision_provider: Zero-arg callable returning the live
            project revision; admission fails closed on drift when
            set, skips the check when omitted.
    """

    def __init__(self, project_id, actor="agent", root=None, execution=None,
                 project_root=None, runner=None, dispatcher=None,
                 approval_ttl_s=DEFAULT_APPROVAL_TTL_S,
                 clock=time.monotonic, revision_provider=None):
        self._project_id = project_id
        self._actor = actor
        self._root = Path(
            root if root is not None
            else Path(tempfile.gettempdir()) / "rocketeda_pyexec" / project_id
        )
        (self._root / "cells").mkdir(parents=True, exist_ok=True)
        (self._root / "executions").mkdir(parents=True, exist_ok=True)
        (self._root / "approvals").mkdir(parents=True, exist_ok=True)
        self._execution = (
            execution if execution is not None
            else ExecutionService(project_id)
        )
        self._project_root = project_root
        self._runner = runner
        self._dispatcher = dispatcher
        self._approval_ttl_s = approval_ttl_s
        self._clock = clock
        self._revision_provider = revision_provider
        self._generation = uuid.uuid4().hex
        self._approvals = {}
        self._requests = {}
        self._runs = {}
        self._records = {}
        self._cancel_flags = set()
        self._cancel_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._env_digest = prelude_digest_for(project_id)
        self._cursor = len(list((self._root / "executions").glob("*.yaml")))
        self._yaml = YAML(typ="safe")

    @property
    def generation(self):
        """Current approval generation; reset retires it.

        Returns:
            Generation id string.
        """
        return self._generation

    @property
    def cursor(self):
        """History cursor: count of persisted executions.

        Returns:
            Execution count as an int.
        """
        return self._cursor

    @property
    def job_surface(self):
        """Execution service owning this service's run records.

        Returns:
            Bound execution service.
        """
        return self._execution

    def _dump(self, data):
        buf = io.StringIO()
        self._yaml.dump(data, buf)
        return buf.getvalue()

    @staticmethod
    def _normalize(code):
        text = code if code.endswith("\n") else code + "\n"
        return text

    def _read_cell(self, execution_id):
        return (self._root / "cells" / ("%s.py" % execution_id)).read_text(
            encoding="utf-8")

    def _cell_digest(self, execution_id):
        try:
            data = (self._root / "cells" / ("%s.py" % execution_id)).read_bytes()
        except OSError:
            return None
        return hashlib.sha256(data).hexdigest()

    def _sweep_expired(self):
        now = self._clock()
        for record in self._approvals.values():
            if record["state"] == "pending_approval" and now > record["expires_at"]:
                record["state"] = "expired"
                record["reason"] = "Approval TTL elapsed without a UI decision."
                self._persist_approval(record)

    def _persist_approval(self, record):
        (self._root / "approvals" / ("%s.yaml" % record["approval_id"])).write_text(
            self._dump({**record, "project_id": self._project_id}),
            encoding="utf-8",
        )

    def _persist_execution(self, record):
        stored = {
            **record,
            "project_id": self._project_id,
            "actor": self._actor,
            "generation": self._generation,
            "env_digest": self._env_digest,
            "history_cursor": self._cursor + 1,
        }
        (self._root / "executions" / ("%s.yaml" % record["execution_id"])).write_text(
            self._dump(stored), encoding="utf-8"
        )
        self._cursor += 1
        return stored

    def validate_request(self, mode, lines=None, path=None, artifacts=(),
                       timeout_s=None):
        """Validate one execution request without changing state.

        Pure pre-check: the Engine runs this before its own
        revision-gated admission so malformed requests fail before
        anything is persisted or queued.

        Args:
            mode: Input mode, exactly `lines` or `path`.
            lines: Inline script text for lines mode.
            path: Project-relative script path for path mode.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Worker budget; the bounded default when
                omitted.

        Returns:
            (display, source_file, budget, artifacts) tuple: the
                normalized cell text, the project-relative source
                (path mode) or None, the resolved budget, and the
                validated artifact names.

        Raises:
            ExecutionError: invalid_command for a bad mode, a
                mode/field mismatch, oversize input, or a malformed
                timeout, invalid_cell/empty_cell for bad script
                text, path_escape/invalid_path/cell_unreadable for
                bad project files.
        """
        if mode not in MODES:
            raise ExecutionError(
                "invalid_command",
                f"mode must be one of {list(MODES)}, got {mode!r}.",
            )
        if mode == "lines" and (lines is None or path is not None):
            raise ExecutionError(
                "invalid_command",
                "lines mode needs lines text and no path.",
            )
        if mode == "path" and (path is None or lines is not None):
            raise ExecutionError(
                "invalid_command",
                "path mode needs a path and no lines text.",
            )
        budget = DEFAULT_TIMEOUT_S if timeout_s is None else _check_timeout(timeout_s)
        names = _validate_artifacts(artifacts)
        if mode == "lines":
            if not isinstance(lines, str):
                raise ExecutionError(
                    "invalid_cell",
                    f"Cell code must be UTF-8 text, got {type(lines).__name__}.",
                )
            if not lines.strip():
                raise ExecutionError("empty_cell", "Cell is empty.")
            if len(lines.encode("utf-8")) > MAX_LINES_BYTES:
                raise ExecutionError(
                    "invalid_command",
                    f"lines exceed {MAX_LINES_BYTES} bytes.",
                )
            return self._normalize(lines), None, budget, names
        script = resolve_script_path(self._project_root, path)
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            raise ExecutionError(
                "cell_unreadable",
                f"Cannot read script file {path}: {exc}.",
            ) from exc
        if not text.strip():
            raise ExecutionError("empty_cell", "Cell is empty.")
        return self._normalize(text), path, budget, names

    def request_execution(self, mode, lines=None, path=None, request_id=None,
                          run_id=None, expected_revision="local",
                          artifacts=(), timeout_s=None):
        """Request one execution: persist the cell, open an approval.

        Job keys:
            mode (required): `lines` for inline script text, `path`
                for a project-contained script file.
            lines: Inline script text (lines mode only).
            path: Project-relative script path (path mode only).
            timeout_s: Worker budget in seconds (default 120).
            artifacts: Scratch-relative paths to harvest.
            expected_revision: Project revision the approval binds.

        The call returns promptly with an approval handle; it runs
        nothing. Repeating a request_id with identical code returns
        the stored handle; changed code under the same id conflicts.

        Args:
            mode: Input mode, exactly `lines` or `path`.
            lines: Inline script text for lines mode.
            path: Project-relative script path for path mode.
            request_id: Client envelope id; generated when omitted.
            run_id: Prescribed execution id (the Engine submit ack
                id); minted at approval when omitted.
            expected_revision: Revision the approval binds.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Worker budget; the bounded default when
                omitted.

        Returns:
            Approval handle with execution_id, approval_id,
                pending_approval state, code hash, and the run_id
                only when the caller prescribed one.

        Raises:
            ExecutionError: invalid_command for a bad mode, a
                mode/field mismatch, oversize input, or a malformed
                timeout, invalid_cell/empty_cell for bad script
                text, path_escape/invalid_path/cell_unreadable for
                bad project files, request_conflict for a reused
                request id with new code.
        """
        display, source_file, budget, names = self.validate_request(
            mode, lines=lines, path=path, artifacts=artifacts,
            timeout_s=timeout_s,
        )
        code_sha256 = hashlib.sha256(display.encode("utf-8")).hexdigest()
        request_id = request_id or uuid.uuid4().hex
        prev = self._requests.get(request_id)
        if prev is not None:
            if prev["code_sha256"] != code_sha256:
                raise ExecutionError(
                    "request_conflict",
                    f"Request id reused with different code: {request_id}.",
                )
            return self._handle_for(prev["execution_id"], request_id)
        if run_id is not None and run_id in self._runs:
            raise ExecutionError(
                "invalid_command",
                f"run_id already admitted: {run_id}.",
            )
        execution_id = uuid.uuid4().hex
        (self._root / "cells" / ("%s.py" % execution_id)).write_text(
            display, encoding="utf-8")
        approval_id = uuid.uuid4().hex
        now = self._clock()
        record = {
            "approval_id": approval_id,
            "execution_id": execution_id,
            "run_id": run_id,
            "request_id": request_id,
            "mode": mode,
            "source_file": source_file,
            "code_sha256": code_sha256,
            "history_cursor": self._cursor,
            "env_digest": self._env_digest,
            "expected_revision": expected_revision,
            "generation": self._generation,
            "timeout_s": budget,
            "artifacts": names,
            "state": "pending_approval",
            "reason": None,
            "created_at": now,
            "expires_at": now + self._approval_ttl_s,
        }
        self._approvals[approval_id] = record
        if run_id is not None:
            self._runs[run_id] = execution_id
        self._requests[request_id] = {
            "execution_id": execution_id,
            "approval_id": approval_id,
            "code_sha256": code_sha256,
        }
        self._persist_approval(record)
        return self._handle_for(execution_id, request_id)

    def _handle_for(self, execution_id, request_id):
        record = next(
            item for item in self._approvals.values()
            if item["execution_id"] == execution_id
        )
        handle = {
            "request_id": request_id,
            "execution_id": execution_id,
            "approval_id": record["approval_id"],
            "approval_state": record["state"],
            "mode": record["mode"],
            "source_file": record["source_file"],
            "code_sha256": record["code_sha256"],
            "history_cursor": record["history_cursor"],
            "expected_revision": record["expected_revision"],
            "timeout_s": record["timeout_s"],
        }
        if record["run_id"] is not None:
            handle["run_id"] = record["run_id"]
        return handle

    def _binding(self, approval_id):
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ExecutionError(
                "approval_invalid", "Unknown or expired approval."
            ) from None

    def approval_status(self, approval_id):
        """Read one approval's state (approvals, never job state).

        Args:
            approval_id: Approval bound by request_execution.

        Returns:
            Approval state mapping with approval_id, approval_state,
                execution_id, and the run_id only once admitted.

        Raises:
            ExecutionError: approval_invalid for an unknown approval.
        """
        record = self._binding(approval_id)
        self._sweep_expired()
        out = {
            "approval_id": approval_id,
            "approval_state": record["state"],
            "execution_id": record["execution_id"],
        }
        if record["run_id"] is not None:
            out["run_id"] = record["run_id"]
        if record.get("reason"):
            out["reason"] = record["reason"]
        return out

    def resolve_approval(self, approval_id, decision, via="ui", actor=None):
        """Resolve an approval through the human UI route.

        Agent calls request approval; they never grant it: any `via`
        other than the human UI route raises approval_forbidden and
        the approval stays pending. Approving admits exactly one
        queued run; denying lapses the approval with no run.

        Args:
            approval_id: Approval bound by request_execution.
            decision: `approved` to admit one run, `denied` to
                lapse the approval with no run.
            via: Resolution route; only `ui` (the trusted human
                route) resolves.
            actor: Human actor the decision is attributed to.

        Returns:
            Resolution with approval_id, approval_state,
                execution_id, and the run_id once admitted.

        Raises:
            ExecutionError: approval_invalid for an unknown approval
                or any binding drift, approval_forbidden for a
                non-UI route, approval_denied when a lapsed
                approval is approved, approval_expired when a
                lapsed approval is approved, invalid_command for
                any other decision text.
        """
        record = self._binding(approval_id)
        if decision not in ("approved", "denied"):
            raise ExecutionError(
                "invalid_command",
                f"decision must be approved or denied, got {decision!r}.",
            )
        if via != "ui":
            raise ExecutionError(
                "approval_forbidden",
                "Approvals resolve through the human UI route only; "
                "agent calls cannot self-approve.",
            )
        state = record["state"]
        if state == "denied":
            raise ExecutionError(
                "approval_denied", "Approval was denied; no run exists."
            )
        if state == "expired":
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if state == "approved":
            return {
                "approval_id": approval_id,
                "approval_state": "approved",
                "execution_id": record["execution_id"],
                "run_id": record["run_id"],
            }
        if decision == "denied":
            record["state"] = "denied"
            record["reason"] = "Denied on the human UI route."
            record["resolved_by"] = actor or self._actor
            self._persist_approval(record)
            return {
                "approval_id": approval_id,
                "approval_state": "denied",
                "execution_id": record["execution_id"],
            }
        self._sweep_expired()
        if record["state"] == "expired":
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if record["generation"] != self._generation:
            record["state"] = "expired"
            record["reason"] = "Approval generation retired; request again."
            self._persist_approval(record)
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if record["history_cursor"] != self._cursor:
            raise ExecutionError(
                "approval_invalid",
                "History moved since the approval was bound.",
            )
        if self._cell_digest(record["execution_id"]) != record["code_sha256"]:
            raise ExecutionError(
                "approval_invalid",
                "Cell bytes changed under their approval.",
            )
        if self._revision_provider is not None:
            current = self._revision_provider()
            if current != record["expected_revision"]:
                raise ExecutionError(
                    "approval_invalid",
                    f"Project moved since approval: {record['expected_revision']} "
                    f"is stale at {current}.",
                )
        run_id = record["run_id"] or uuid.uuid4().hex
        self._execution.dispatch(
            "python_execute",
            {"project": self._project_id,
             "revision": record["expected_revision"]},
            "",
            run_id=run_id,
        )
        record["run_id"] = run_id
        record["state"] = "approved"
        record["resolved_by"] = actor or self._actor
        self._runs[run_id] = record["execution_id"]
        self._persist_approval(record)
        return {
            "approval_id": approval_id,
            "approval_state": "approved",
            "execution_id": record["execution_id"],
            "run_id": run_id,
        }

    def run_job(self, run_id, on_live=None):
        """Execute an admitted run in a fresh worker, then replay ops.

        Second preflight precedes any spawn: a lapsed approval (or a
        retired generation) cancels the run instead of executing a
        stranger's cell, and a cancelled run never spawns. Effects
        the cell recorded replay through the shared op dispatch
        after the worker exits; their child run_ids ride on the
        terminal record as structured data.

        Args:
            run_id: Admitted execution id from resolve_approval.
            on_live: Optional callback while the worker is live.

        Returns:
            Terminal execution record with state, bounded stdio,
                the parsed exception location, replayed effects
                with child run_ids, and the NOT_RUN verdict.

        Raises:
            ExecutionError: unknown_run for an id never admitted,
                approval_pending/approval_denied/approval_expired
                when the run's approval lapses, approval_invalid
                for binding drift or tampered cell bytes.
        """
        try:
            execution_id = self._runs[run_id]
        except KeyError:
            raise ExecutionError(
                "unknown_run", f"Unknown run: {run_id}."
            ) from None
        record = next(
            item for item in self._approvals.values()
            if item["execution_id"] == execution_id
        )
        approval_state = record["state"]
        if approval_state == "pending_approval":
            self._sweep_expired()
            if record["state"] == "expired":
                raise ExecutionError(
                    "approval_expired", "Approval expired; no run exists."
                )
            raise ExecutionError(
                "approval_pending",
                "Approval is still pending; the UI route has not resolved it.",
            )
        if approval_state == "denied":
            raise ExecutionError(
                "approval_denied", "Approval was denied; no run exists."
            )
        if approval_state == "expired":
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        with self._run_lock:
            if run_id in self._records:
                return dict(self._records[run_id])
            state = self._execution.status(run_id)["state"]
            if state == "cancelled":
                return self._store_cancelled(
                    run_id, execution_id, spawned=False,
                    reason="cancelled before dispatch; worker never spawned.",
                )
            if state != "queued":
                raise ExecutionError(
                    "invalid_command",
                    f"Run is already {state}: {run_id}.",
                )
            self._execution.mark_running(run_id)
        lapse = self._lapse_reason(record)
        if lapse is not None:
            self._execution.cancel(run_id)
            return self._store_cancelled(
                run_id, execution_id, spawned=False, reason=lapse,
            )
        if self._cell_digest(execution_id) != record["code_sha256"]:
            self._execution.cancel(run_id)
            raise ExecutionError(
                "approval_invalid",
                "Cell bytes changed under their approval.",
            )
        display = self._read_cell(execution_id)
        source = build_worker_source(display, project_id=self._project_id)
        # Display line 1 sits one blank line below the preamble.
        cell_line_offset = (
            _render_preamble(self._project_id).count("\n") + 1
        )
        runner = self._runner or PythonExecRunner(
            artifacts_root=str(self._root / "harvest"))
        try:
            result = runner.run(
                source,
                run_id=run_id,
                timeout_s=record["timeout_s"],
                artifacts=(OPS_LOG_NAME,) + tuple(record["artifacts"]),
                on_live=on_live,
                is_cancelled=lambda: self._cancelled(run_id),
                cell_name=record["source_file"] or CELL_ENTRY,
                cell_line_offset=cell_line_offset,
            )
        finally:
            with self._cancel_lock:
                self._cancel_flags.discard(run_id)
        ops, skipped = self._load_harvested_ops(result)
        op_results = self._replay(ops)
        run_ids = [
            item["result"]["run_id"] for item in op_results
            if item["ok"] and isinstance(item.get("result"), dict)
            and isinstance(item["result"].get("run_id"), str)
        ]
        replayed = self._dispatcher is not None
        effects = {
            "ops": ops,
            "op_results": op_results,
            "ops_ok": all(item["ok"] for item in op_results) if replayed else not ops,
            "ops_skipped": skipped,
            "run_ids": run_ids,
            "replayed": replayed,
        }
        verdict = not_run_verdict(self._verdict_reason(result, record))
        terminal = {
            "execution_id": execution_id,
            "run_id": run_id,
            "mode": record["mode"],
            "source_file": record["source_file"],
            "code_sha256": record["code_sha256"],
            "state": result["state"],
            "ok": bool(result["ok"]),
            "reason": result.get("reason"),
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "partial": bool(result.get("partial", False)),
            "exception": result.get("exception"),
            "effects": effects,
            "artifacts": result.get("artifacts", []),
            "rejected_artifacts": result.get("rejected_artifacts", []),
            "network_isolated": result.get("network_isolated", False),
            "credential_revoked": result.get("credential_revoked", False),
            "tree_killed": result.get("tree_killed", False),
            "spawned": True,
            "timeout_s": record["timeout_s"],
            "verdict": verdict,
        }
        self._persist_execution(terminal)
        self._records[run_id] = dict(terminal)
        if result["state"] == "cancelled":
            self._execution.cancel(run_id)
        else:
            self._execution.mark_completed(run_id, verdict)
        return terminal

    def _lapse_reason(self, record):
        if record["generation"] != self._generation:
            return "Approval generation retired before dispatch."
        if self._clock() > record["expires_at"]:
            return "Approval expired before dispatch."
        return None

    def _store_cancelled(self, run_id, execution_id, spawned, reason):
        record = next(
            item for item in self._approvals.values()
            if item["execution_id"] == execution_id
        )
        verdict = not_run_verdict(reason + " Not a check verdict.")
        terminal = {
            "execution_id": execution_id,
            "run_id": run_id,
            "mode": record["mode"],
            "source_file": record["source_file"],
            "code_sha256": record["code_sha256"],
            "state": "cancelled",
            "ok": False,
            "reason": reason,
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "partial": False,
            "exception": None,
            "effects": {
                "ops": [], "op_results": [], "ops_ok": True,
                "ops_skipped": 0, "run_ids": [], "replayed": True,
            },
            "artifacts": [],
            "rejected_artifacts": [],
            "network_isolated": False,
            "credential_revoked": False,
            "tree_killed": False,
            "spawned": spawned,
            "timeout_s": record["timeout_s"],
            "verdict": verdict,
        }
        self._persist_execution(terminal)
        self._records[run_id] = dict(terminal)
        return terminal

    @staticmethod
    def _verdict_reason(result, record):
        state = result["state"]
        if state == "completed":
            return (
                "python_execute is not a check: exit 0 is not PASS; "
                "read the execution record (state/ok/effects)."
            )
        if state == "failed":
            exc = result.get("exception") or {}
            where = exc.get("location") or "unknown location"
            what = exc.get("type") or "error"
            return (
                f"Script failed ({what} at {where}; "
                f"exit {result.get('exit_code')}); not a check verdict."
            )
        if state == "timeout":
            return (
                f"Timeout after {record['timeout_s']}s; partials retained; "
                "not a check verdict."
            )
        if state == "crashed":
            return "Worker died by signal; not a check verdict."
        return "Cancelled via the job surface; not a check verdict."

    def _cancelled(self, run_id):
        with self._cancel_lock:
            return run_id in self._cancel_flags

    @staticmethod
    def _load_harvested_ops(result):
        ops, skipped = [], 0
        for entry in result.get("artifacts", []):
            if entry.get("name") != OPS_LOG_NAME:
                continue
            try:
                lines = Path(entry["path"]).read_text(
                    encoding="utf-8").splitlines()
            except OSError:
                skipped += 1
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    skipped += 1
                    continue
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("operation"), str)
                    or not isinstance(item.get("arguments"), dict)
                ):
                    skipped += 1
                    continue
                ops.append({"operation": item["operation"],
                            "arguments": dict(item["arguments"])})
        return ops, skipped

    def _replay(self, ops):
        if self._dispatcher is None:
            return []
        replayed = []
        for op in ops:
            try:
                payload = self._dispatcher.execute(
                    op["operation"], op["arguments"]
                )
            except Exception as exc:  # per-op truth: record, never raise
                replayed.append({
                    "operation": op["operation"],
                    "ok": False,
                    "error": {
                        "code": getattr(exc, "code", None)
                        or "internal_error",
                        "message": str(exc),
                    },
                })
                continue
            replayed.append({
                "operation": op["operation"],
                "ok": True,
                "result": json.loads(json.dumps(payload, default=str)),
            })
        return replayed

    def cancel(self, run_id):
        """Cancel a queued or running run through the job surface.

        The cooperative flag kills a live worker tree promptly;
        finished runs keep their terminal state, truthfully.

        Args:
            run_id: Admitted execution id to cancel.

        Returns:
            Mapping with run_id and state.

        Raises:
            ExecutionError: unknown_run for an id never admitted.
        """
        with self._cancel_lock:
            self._cancel_flags.add(run_id)
        return self._execution.cancel(run_id)

    def status(self, run_id):
        """Read one run's job state, verdict, and evidence links.

        Pure job surface: approval states never appear here — read
        them from approval_status instead.

        Args:
            run_id: Admitted execution id to inspect.

        Returns:
            Run state mapping with run_id, operation, state,
                snapshot_id, and verdict.

        Raises:
            ExecutionError: unknown_run for an id never admitted.
        """
        return self._execution.status(run_id)

    def execution_record(self, run_id):
        """Read one run's terminal execution record, when finished.

        Args:
            run_id: Admitted execution id to inspect.

        Returns:
            Terminal record copy, or None while unfinished.
        """
        record = self._records.get(run_id)
        return dict(record) if record is not None else None

    def console_view(self):
        """Read generation, environment, and pending approvals.

        Args:
            None.

        Returns:
            Console view with project_id, generation, env_digest,
                history cursor, pending approval count, and the
                pending approval ids.
        """
        self._sweep_expired()
        pending = [
            item["approval_id"] for item in self._approvals.values()
            if item["state"] == "pending_approval"
        ]
        return {
            "project_id": self._project_id,
            "generation": self._generation,
            "env_digest": self._env_digest,
            "cursor": self._cursor,
            "pending_approvals": len(pending),
            "pending_approval_ids": pending,
            "executions": self._cursor,
        }

    def reset(self):
        """Retire the generation; lapse pending, cancel queued.

        Pending approvals expire (their generation is gone);
        approved-but-unrun jobs cancel through the job surface.
        Live workers are cancel territory, not reset: interrupting
        one needs cancel(run_id), never reset.

        Returns:
            Mapping with the fresh generation id.
        """
        self._generation = uuid.uuid4().hex
        for record in self._approvals.values():
            if record["state"] == "pending_approval":
                record["state"] = "expired"
                record["reason"] = "Approval generation retired; request again."
                self._persist_approval(record)
            elif record["state"] == "approved" and record["run_id"] is not None:
                run_id = record["run_id"]
                if run_id not in self._records:
                    with self._cancel_lock:
                        self._cancel_flags.add(run_id)
                    try:
                        self._execution.cancel(run_id)
                    except ExecutionError:
                        pass
        return {"generation": self._generation}
