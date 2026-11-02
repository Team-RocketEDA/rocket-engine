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
import tempfile
import threading
import time
import uuid
from pathlib import Path

from ruamel.yaml import YAML

from .errors import ExecutionError
from .service import ExecutionService
from .pyexec.approvals import _ApprovalMixin
from .pyexec.runner import PythonExecRunner
from .pyexec.support import (
    _check_timeout,
    _render_preamble,
    _validate_artifacts,
    CELL_ENTRY,
    DEFAULT_TIMEOUT_S,
    MAX_ARTIFACTS,
    MAX_LINES_BYTES,
    MAX_PATH_CHARS,
    MAX_TIMEOUT_S,
    MIN_TIMEOUT_S,
    OPS_LOG_NAME,
    PRELUDE_DIGEST,
    PRELUDE_TEMPLATE,
    build_worker_source,
    not_run_verdict,
    parse_exception,
    prelude_digest_for,
    resolve_script_path,
)


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

#: Pending approvals lapse after this long without a UI decision.
DEFAULT_APPROVAL_TTL_S = 900

#: Live index bound: denied/expired approvals past this count evict
#: oldest-first. Pending and approved approvals are live
#: references (runs and status reads resolve through them) and
#: never reap; the `approvals/*.yaml` audit trail keeps every
#: record on disk regardless of eviction.
MAX_TERMINAL_APPROVALS = 100


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


class PythonExecService(_ApprovalMixin):
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
        self._reap_terminal()

    def _reap_terminal(self):
        """Evict oldest terminal approvals past the live index bound.

        Denied and expired approvals are dead references: no run or
        status path can proceed through them. Past the bound the
        oldest evict first (by creation, then id); pending and
        approved approvals are live and never reap. The YAML audit
        trail on disk is untouched — this bounds the live index,
        not history.
        """
        terminal = [
            record for record in self._approvals.values()
            if record["state"] in ("denied", "expired")
        ]
        excess = len(terminal) - MAX_TERMINAL_APPROVALS
        if excess <= 0:
            return
        # Stable sort: ties keep admission order, so the earliest
        # admitted terminal approval evicts first even when the
        # clock never advanced between admissions.
        terminal.sort(key=lambda record: record.get("created_at", 0))
        for record in terminal[:excess]:
            del self._approvals[record["approval_id"]]


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
        self._reap_terminal()
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
        self._reap_terminal()
        return {"generation": self._generation}
