"""Stdio console adapter: MATLAB-esque script console over shared dispatch.

A REPL gateway onto the shared op dispatch: cells are Python with the
engine world prebound (`project/tools/pdk/gf/np/plot`), executed one
per fresh WORKERS worker with zero setup, while every `tools.<op>`
call inside a cell compiles to the same op call the batch command
surface runs — console history replays as command scripts by
construction. This adapter faces the use-case layer (`execution`
dispatch, console approvals, workers) directly; it never calls
another adapter, and no adapter calls it.

Framing (what the IDE xterm panel consumes): the interactive loop
reads `submit` + cell lines until `:end` (multiline cells),
`submit-file PATH` (script-file cells), `history`, `reset`, `help`,
`quit`. Human frames print the cell id, verbatim worker stdout,
harvested op calls as replayable command lines, then the terminal
execution line. `--json` prints one stable envelope per command.

History persists under the console root (`console.yaml`,
`cells/<execution_id>.py` holding the exact displayed cell,
`executions/<execution_id>.yaml` holding the terminal record):
reopening the same root continues numbering. Single console per
panel: one live handle per root, no tabs, no console-id multiplexing.

Approvals are reused from `execution.console`, never reimplemented:
a human Run requests and admits approval of the exact displayed
cell in one step (identical binding). Runs are serial and each
worker run already revokes its credential and confirms its tree-kill
before its terminal record, so `reset` retires the generation and
kills every outstanding approval; interrupting a live run is cancel
territory, not reset.

Local-only trust: this console speaks stdio to the local IDE panel
under OS identity. There is no token check, login, network listener,
remote execution, or second user to protect against — and deliberately
no code for any of those. See TRUST_NOTE.
"""

import hashlib
import io
import json
import shlex
import sys
import threading
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from ..composition import Engine
from ..execution.console import ConsoleSession
from ..execution.dispatch import OpDispatcher
from ..execution.errors import ExecutionError, UsageError
from ..execution.worker import CellRunner

__all__ = [
    "CELL_PRELUDE_TEMPLATE",
    "EXIT_OK",
    "EXIT_USAGE",
    "LOCAL_ONLY_TRUST",
    "OPS_LOG_NAME",
    "PREBOUND_NAMES",
    "PRELUDE_DIGEST",
    "TRUST_NOTE",
    "USAGE",
    "StdioConsole",
    "build_cell_source",
    "format_op_call",
    "main",
]

EXIT_OK = 0
EXIT_USAGE = 2

LOCAL_ONLY_TRUST = True

TRUST_NOTE = (
    "Local-only trust: this console speaks stdio to the local IDE panel "
    "under OS identity, with no auth step because there is no second party "
    "— no tokens, no broker, no listener, no remote execution, no multi-user. "
    "Human Run on the displayed cell is the approval; sandboxing (not "
    "identity) is the safety boundary."
)

PREBOUND_NAMES = ("project", "tools", "pdk", "gf", "np", "plot")

OPS_LOG_NAME = "__console_ops.jsonl"

CELL_PRELUDE_TEMPLATE = '''\
# --- rocket-console prelude: pinned trusted bootstrap (do not edit) ---
import json as _json

__CONSOLE_PROJECT__ = @PROJECT_ID@
__CONSOLE_OPS_LOG__ = "__console_ops.jsonl"


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
            with open(__CONSOLE_OPS_LOG__, "a", encoding="utf-8") as handle:
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


project = _Project(__CONSOLE_PROJECT__)


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

PRELUDE_DIGEST = hashlib.sha256(
    CELL_PRELUDE_TEMPLATE.encode("utf-8")
).hexdigest()

USAGE = """usage: rocket-console [--project ID] [--actor NAME] [--root DIR] [--json]

MATLAB-esque script console, stdio-only (local IDE panel). One console
per panel: no tabs, no multiplexing. Commands, one per line; blank
lines and `#` comments are skipped:

  submit            read cell lines until `:end`, then run them
  submit-file PATH  run a script file as one cell (history keeps a copy)
  history           list persisted executions
  reset             retire the generation, kill outstanding approvals
  help              print this usage
  quit              leave the console (EOF also leaves)

Every cell runs in a fresh worker with project/tools/pdk/gf/np/plot
prebound and zero setup. tools.<op> calls replay through the shared
op dispatch after the worker exits — the printed op lines rerun as a
batch script. --json prints one envelope per command instead.
"""

_yaml = YAML(typ="safe")

_LIVE = set()
_LIVE_LOCK = threading.Lock()


def _render_preamble(project_id):
    return CELL_PRELUDE_TEMPLATE.replace(
        "@PROJECT_ID@", json.dumps(project_id)
    )


def build_cell_source(code, project_id="default"):
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


def format_op_call(operation, arguments):
    """Format one op call as a batch-surface command line (replayable).

    Values render as JSON (a YAML subset, so types round-trip through
    the one parser of record) and the whole `key=value` token is shell
    quoted when needed. Argument order is sorted for stability.

    Args:
        operation: Cataloged operation or query name.
        arguments: Operation arguments rendered as key=value pairs.

    Returns:
        Replayable batch-surface command line for the op call.
    """
    parts = [operation]
    for key in sorted(arguments):
        value_text = json.dumps(arguments[key], sort_keys=True, default=str)
        parts.append(shlex.quote("%s=%s" % (key, value_text)))
    return " ".join(parts)


def _dump_yaml(data):
    buf = io.StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def _load_yaml(text):
    return _yaml.load(text) or {}


class StdioConsole:
    """One stdio console: cells in fresh workers, ops via dispatch.

    Args:
        engine: Engine ops replay against; constructed from
            project_id/actor when omitted.
        project_id: Project id stamped on every command.
        actor: Actor stamped on every command.
        root: Console state dir; defaults under cwd `.rocket/`.
        cell_runner: Worker runner; constructed when omitted.
        expected_revision: Revision cells bind approvals against.
    """

    def __init__(self, engine=None, project_id="default", actor="console",
                 root=None, cell_runner=None, expected_revision="local"):
        self._engine = (
            engine if engine is not None else Engine(project_id, actor=actor)
        )
        self._project_id = project_id
        self._actor = actor
        self._expected_revision = expected_revision
        self._root = (
            Path(root) if root is not None
            else Path.cwd() / ".rocket" / "consoles" / "stdio"
        )
        key = str(self._root.resolve())
        with _LIVE_LOCK:
            if key in _LIVE:
                raise ExecutionError(
                    "console_busy",
                    f"One console per panel: {self._root} is already open.",
                )
            _LIVE.add(key)
        self._live_key = key
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            (self._root / "cells").mkdir(exist_ok=True)
            (self._root / "executions").mkdir(exist_ok=True)
            self._dispatch = OpDispatcher(
                self._engine, project_id=project_id, actor=actor
            )
            self._session = ConsoleSession(project_id, actor)
            self._runner = (
                cell_runner if cell_runner is not None
                else CellRunner(artifacts_root=str(self._root / "harvest"))
            )
            self._env_digest = hashlib.sha256(
                _render_preamble(project_id).encode("utf-8")
            ).hexdigest()
            self._load_or_create()
        except Exception:
            self.close()
            raise

    def _load_or_create(self):
        console_file = self._root / "console.yaml"
        if console_file.is_file():
            data = _load_yaml(console_file.read_text(encoding="utf-8"))
            self._console_id = data.get("console_id") or uuid.uuid4().hex
            self._generation = data.get("generation") or uuid.uuid4().hex
        else:
            self._console_id = uuid.uuid4().hex
            self._generation = self._session.generation
        self._session.generation = self._generation
        self._cursor = len(list((self._root / "executions").glob("*.yaml")))
        self._write_console_yaml()

    def _write_console_yaml(self):
        (self._root / "console.yaml").write_text(
            _dump_yaml({
                "console_id": self._console_id,
                "generation": self._generation,
                "project_id": self._project_id,
                "actor": self._actor,
                "prelude_digest": PRELUDE_DIGEST,
                "env_digest": self._env_digest,
                "executions": self._cursor,
            }),
            encoding="utf-8",
        )

    @property
    def console_id(self):
        """Stable console id, persisted across restarts.

        Returns:
            Console id string.
        """
        return self._console_id

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
    def root(self):
        """Console state directory.

        Returns:
            Root path string.
        """
        return str(self._root)

    @property
    def engine(self):
        """Engine ops replay against.

        Returns:
            Bound engine.
        """
        return self._engine

    @property
    def gate(self):
        """Execution-scoped credential gate of the worker runner.

        Returns:
            Credential gate.
        """
        return self._runner.gate

    @property
    def admission(self):
        """Worker isolation admission record.

        Returns:
            Admission mapping copy.
        """
        return dict(self._runner.admission)

    @staticmethod
    def _normalize(code):
        if not isinstance(code, str):
            raise ExecutionError(
                "invalid_cell", "Cell code must be UTF-8 text."
            )
        if not code.strip():
            raise ExecutionError("empty_cell", "Cell is empty.")
        return code if code.endswith("\n") else code + "\n"

    def request_approval(self, code):
        """Approve-later path: bind an approval to one display cell.

        Args:
            code: Display cell text to bind.

        Returns:
            Approval record with approval_id and pending state.

        Raises:
            ExecutionError: invalid_cell for non-text code,
                empty_cell for a blank cell.
        """
        display = self._normalize(code)
        full = build_cell_source(display, project_id=self._project_id)
        return self._session.request_cell_approval(
            code=full, history_cursor=self._cursor,
            env_digest=self._env_digest,
            expected_revision=self._expected_revision,
        )

    def run_approved(self, approval_id, code, artifacts=(), timeout_s=None,
                     on_live=None):
        """Run a cell against an earlier approval (tamper raises).

        Args:
            approval_id: Approval bound by request_approval.
            code: Display cell text; must match the binding.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Worker budget in seconds; runner default
                when omitted.
            on_live: Optional callback while the worker is live.

        Returns:
            Persisted execution record with state, stdio, ops
                replay, and artifacts.

        Raises:
            ExecutionError: approval_invalid when the code drifts
                from its binding, invalid_cell/empty_cell for bad
                code.
        """
        display = self._normalize(code)
        full = build_cell_source(display, project_id=self._project_id)
        return self._run_full(approval_id, full, display,
                              {"source_file": None}, artifacts, timeout_s,
                              on_live)

    def submit(self, code, artifacts=(), timeout_s=None, on_live=None):
        """Human-Run path: approve and run the exact displayed cell.

        Args:
            code: Display cell text to approve and run.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Worker budget in seconds; runner default
                when omitted.
            on_live: Optional callback while the worker is live.

        Returns:
            Persisted execution record with state, stdio, ops
                replay, and artifacts.

        Raises:
            ExecutionError: invalid_cell for non-text code,
                empty_cell for a blank cell.
        """
        display = self._normalize(code)
        full = build_cell_source(display, project_id=self._project_id)
        approval = self._session.request_cell_approval(
            code=full, history_cursor=self._cursor,
            env_digest=self._env_digest,
            expected_revision=self._expected_revision,
        )
        return self._run_full(approval["approval_id"], full, display,
                              {"source_file": None}, artifacts, timeout_s,
                              on_live)

    def submit_file(self, path, artifacts=(), timeout_s=None, on_live=None):
        """Run a script file as one cell; history keeps its own copy.

        Args:
            path: Script file path to run as one cell.
            artifacts: Scratch-relative paths to harvest.
            timeout_s: Worker budget in seconds; runner default
                when omitted.
            on_live: Optional callback while the worker is live.

        Returns:
            Persisted execution record with state, stdio, ops
                replay, and artifacts.

        Raises:
            ExecutionError: cell_unreadable when the file cannot
                be read, invalid_cell/empty_cell for bad content.
        """
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ExecutionError(
                "cell_unreadable", f"Cannot read cell file {path}: {exc}."
            ) from exc
        display = self._normalize(text)
        full = build_cell_source(display, project_id=self._project_id)
        approval = self._session.request_cell_approval(
            code=full, history_cursor=self._cursor,
            env_digest=self._env_digest,
            expected_revision=self._expected_revision,
        )
        return self._run_full(approval["approval_id"], full, display,
                              {"source_file": str(path)}, artifacts,
                              timeout_s, on_live)

    def _run_full(self, approval_id, full, display, extra, artifacts,
                  timeout_s, on_live):
        execution_id = uuid.uuid4().hex
        cell_rel = "cells/%s.py" % execution_id
        (self._root / cell_rel).write_text(display, encoding="utf-8")
        base = {
            "execution_id": execution_id,
            "cell": cell_rel,
            "code_sha256": hashlib.sha256(
                display.encode("utf-8")
            ).hexdigest(),
            "history_cursor": self._cursor + 1,
        }
        try:
            result = self._runner.run_cell(
                self._session, approval_id, full,
                history_cursor=self._cursor, env_digest=self._env_digest,
                expected_revision=self._expected_revision,
                artifacts=(OPS_LOG_NAME,) + tuple(artifacts),
                timeout_s=timeout_s, on_live=on_live,
            )
        except ExecutionError as exc:
            if exc.code == "approval_invalid":
                raise
            record = {
                **base,
                "state": "not_run",
                "ok": False,
                "code": exc.code,
                "reason": str(exc),
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "partial": False,
                "ops": [],
                "op_results": [],
                "ops_ok": True,
                "ops_skipped": 0,
                "cli_script": [],
                "artifacts": [],
                "rejected_artifacts": [],
                "network_isolated": self.admission.get(
                    "network_isolated", False),
                "run_id": None,
                **extra,
            }
            self._persist(record)
            return record
        ops, skipped = self._load_harvested_ops(result)
        op_results = self._replay(ops)
        record = {
            **base,
            "state": result["state"],
            "ok": bool(result["ok"]),
            "reason": result.get("reason"),
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "partial": bool(result.get("partial", False)),
            "ops": ops,
            "op_results": op_results,
            "ops_ok": all(item["ok"] for item in op_results),
            "ops_skipped": skipped,
            "cli_script": [
                format_op_call(op["operation"], op["arguments"]) for op in ops
            ],
            "artifacts": result.get("artifacts", []),
            "rejected_artifacts": result.get("rejected_artifacts", []),
            "network_isolated": result.get("network_isolated", False),
            "credential_revoked": result.get("credential_revoked", False),
            "tree_killed": result.get("tree_killed", False),
            "run_id": result.get("run_id"),
            **extra,
        }
        self._persist(record)
        return record

    def _persist(self, record):
        stored = {
            **record,
            "console_id": self._console_id,
            "generation": self._generation,
            "project_id": self._project_id,
            "prelude_digest": PRELUDE_DIGEST,
            "env_digest": self._env_digest,
            "expected_revision": self._expected_revision,
        }
        (self._root / "executions" / ("%s.yaml" % record["execution_id"])
         ).write_text(_dump_yaml(stored), encoding="utf-8")
        self._cursor += 1
        self._write_console_yaml()

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
        replayed = []
        for op in ops:
            try:
                payload = self._dispatch.execute(
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

    def history(self):
        """Persisted executions, oldest first (survives restarts).

        Returns:
            Execution records sorted by history cursor.
        """
        records = []
        for path in (self._root / "executions").glob("*.yaml"):
            records.append(_load_yaml(path.read_text(encoding="utf-8")))
        records.sort(key=lambda item: item.get("history_cursor", 0))
        return records

    def reset(self):
        """Retire the generation and kill every outstanding approval.

        Returns:
            Mapping with the fresh generation id.
        """
        out = self._session.reset()
        self._generation = out["generation"]
        self._write_console_yaml()
        return {"generation": self._generation}

    def close(self):
        """Release this console's single-panel slot (idempotent)."""
        key = getattr(self, "_live_key", None)
        if key is None:
            return
        with _LIVE_LOCK:
            _LIVE.discard(key)
        self._live_key = None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _split_flag(token, name):
    prefix = "--%s=" % name
    if token.startswith(prefix):
        return token[len(prefix):]
    return None


def _parse_argv(argv):
    options = {"json": False, "root": None, "project": "default",
               "actor": "console", "help": False}
    rest = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--json":
            options["json"] = True
        elif token in ("--help", "-h"):
            options["help"] = True
        elif token == "--root":
            i += 1
            if i >= len(argv):
                raise UsageError(
                    "invalid_command", "`--root` needs a directory.")
            options["root"] = argv[i]
        elif token == "--project":
            i += 1
            if i >= len(argv):
                raise UsageError("invalid_command", "`--project` needs an ID.")
            options["project"] = argv[i]
        elif token == "--actor":
            i += 1
            if i >= len(argv):
                raise UsageError("invalid_command", "`--actor` needs a NAME.")
            options["actor"] = argv[i]
        elif _split_flag(token, "root") is not None:
            options["root"] = _split_flag(token, "root")
        elif _split_flag(token, "project") is not None:
            options["project"] = _split_flag(token, "project")
        elif _split_flag(token, "actor") is not None:
            options["actor"] = _split_flag(token, "actor")
        elif token == "--":
            rest.extend(argv[i + 1:])
            break
        elif token.startswith("-"):
            raise UsageError("invalid_command", f"Unknown flag: {token}.")
        else:
            rest.extend(argv[i:])
            break
        i += 1
    return options, rest


def _emit_result(command, result, as_json, stdout):
    if as_json:
        stdout.write(json.dumps(
            {"command": command, "ok": True, "result": result},
            sort_keys=True, default=str,
        ) + "\n")
        return
    if command == "history":
        executions = result["executions"]
        stdout.write("--- history (%d) ---\n" % len(executions))
        for item in executions:
            stdout.write("cursor=%s %s %s ok=%s\n" % (
                item.get("history_cursor"), item.get("execution_id"),
                item.get("state"), item.get("ok"),
            ))
        return
    if command == "reset":
        stdout.write("--- reset generation=%s ---\n"
                     % result["generation"])
        return
    stdout.write("--- cell %s cursor=%s ---\n" % (
        result["execution_id"], result["history_cursor"]))
    if result.get("stdout"):
        stdout.write(result["stdout"])
        if not result["stdout"].endswith("\n"):
            stdout.write("\n")
    if result.get("stderr"):
        stdout.write("--- stderr ---\n")
        stdout.write(result["stderr"])
        if not result["stderr"].endswith("\n"):
            stdout.write("\n")
    script = result.get("cli_script", [])
    stdout.write("--- ops (%d) ---\n" % len(script))
    if script:
        for line in script:
            stdout.write(line + "\n")
    else:
        stdout.write("(none)\n")
    for item in result.get("op_results", []):
        if not item["ok"]:
            stdout.write("op %s: error [%s] %s\n" % (
                item["operation"], item["error"]["code"],
                item["error"]["message"],
            ))
    if result.get("state") == "not_run":
        stdout.write("--- not run [%s] ---\n%s\n" % (
            result.get("code"), result.get("reason")))
    stdout.write("--- execution %s ok=%s ---\n" % (
        result["state"], "true" if result["ok"] else "false"))


def _emit_error(command, exc, as_json, stdout, stderr):
    code = getattr(exc, "code", None) or "internal_error"
    message = str(exc) or code
    if as_json:
        stdout.write(json.dumps(
            {"command": command, "ok": False,
             "error": {"code": code, "message": message}},
            sort_keys=True, default=str,
        ) + "\n")
    else:
        stderr.write("error [%s]: %s\n" % (code, message))


def _do_submit(console, options, code, stdout, stderr):
    try:
        record = console.submit(code)
    except ExecutionError as exc:
        _emit_error("submit", exc, options["json"], stdout, stderr)
        return
    _emit_result("submit", record, options["json"], stdout)


def _do_submit_file(console, options, path, stdout, stderr):
    try:
        record = console.submit_file(path)
    except ExecutionError as exc:
        _emit_error("submit-file", exc, options["json"], stdout, stderr)
        return
    _emit_result("submit-file", record, options["json"], stdout)


def _do_history(console, options, stdout):
    _emit_result("history", {"executions": console.history()},
                 options["json"], stdout)


def _do_reset(console, options, stdout):
    _emit_result("reset", console.reset(), options["json"], stdout)


def _run_session(console, options, stdin, stdout, stderr):
    interactive = stdin.isatty() if hasattr(stdin, "isatty") else False
    if interactive:
        stdout.write("console> ")
        stdout.flush()
    while True:
        line = stdin.readline()
        if line == "":
            break
        stripped = line.strip()
        if interactive:
            stdout.write("console> ")
            stdout.flush()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("exit", "quit"):
            break
        if stripped == "help":
            stdout.write(USAGE)
            continue
        if stripped == "submit":
            cell_lines = []
            while True:
                cell_line = stdin.readline()
                if cell_line == "":
                    break
                if cell_line.strip() == ":end":
                    break
                cell_lines.append(cell_line)
            eof = cell_line == ""
            code = "".join(cell_lines)
            if eof and not code.strip():
                break
            _do_submit(console, options, code, stdout, stderr)
            if eof:
                break
            continue
        if stripped == "submit-file" or stripped.startswith("submit-file "):
            _, _, path = stripped.partition(" ")
            path = path.strip()
            if not path:
                _emit_error("submit-file", UsageError(
                    "invalid_command", "`submit-file` needs a PATH."),
                    options["json"], stdout, stderr)
                continue
            _do_submit_file(console, options, path, stdout, stderr)
            continue
        if stripped == "history":
            _do_history(console, options, stdout)
            continue
        if stripped == "reset":
            _do_reset(console, options, stdout)
            continue
        _emit_error(stripped.split()[0], UsageError(
            "invalid_command",
            f"Unknown command: {stripped} (want submit, submit-file,"
            " history, reset, help, quit).",
        ), options["json"], stdout, stderr)
    return EXIT_OK


def main(argv=None, engine=None, cell_runner=None, stdin=None, stdout=None,
         stderr=None):
    """Run the stdio console; return the process exit code (never raise).

    Args:
        argv: Argument vector without the program name; defaults to
            sys.argv[1:].
        engine: Engine to run against; constructed from
            --project/--actor when omitted.
        cell_runner: Worker runner; constructed when omitted.
        stdin: Input stream for the interactive session.
        stdout: Stream for results and machine envelopes.
        stderr: Stream for human-readable errors plus usage.

    Returns:
        Process exit code: 0 session-ok, 2 usage error.

    Caution: Exit zero is not PASS — per-cell verdicts live in the
        persisted records; read them, never the exit code.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    try:
        options, rest = _parse_argv(argv)
    except UsageError as exc:
        _emit_error(None, exc, False, stdout, stderr)
        return EXIT_USAGE
    if options["help"]:
        stdout.write(USAGE)
        return EXIT_OK
    if rest:
        _emit_error(None, UsageError(
            "invalid_command",
            f"Unknown command: {rest[0]} (the console is interactive).",
        ), options["json"], stdout, stderr)
        return EXIT_USAGE
    if engine is None:
        engine = Engine(options["project"], actor=options["actor"])
    try:
        console = StdioConsole(
            engine, project_id=options["project"], actor=options["actor"],
            root=options["root"], cell_runner=cell_runner,
        )
    except ExecutionError as exc:
        _emit_error(None, exc, options["json"], stdout, stderr)
        return EXIT_USAGE
    try:
        return _run_session(console, options, stdin, stdout, stderr)
    finally:
        console.close()


if __name__ == "__main__":
    raise SystemExit(main())
