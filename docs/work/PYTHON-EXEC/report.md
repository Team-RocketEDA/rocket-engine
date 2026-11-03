# PYTHON-EXEC lane report — `python_execute` (lines + path)

## Outcome

Implemented headless `python_execute` with exactly two input modes (`lines`,
`path`) per `docs/tickets/PYTHON-EXEC.md`, approval-gated per
`python-console-spec`, running on the prepared worker substrate shared with
the console. New module + new tests pass standalone on the unpatched tree;
Engine API + MCP tool + contract wiring is delivered as an exact unified-diff
patch (`wiring.patch`, also embedded below) verified end-to-end in a scratch
clone (patch applies, wiring tests green, `api_spec` + `contract` regen clean,
freshness gates pass).

## Files added (new files only — no existing file edited)

- `src/execution/python_exec.py` — the module: `PythonExecService`
  (request/resolve/run/cancel + effects replay), `PythonExecRunner` (fresh
  prepared workers on the `BwrapRunner`/`worker_profile`/`CredentialGate`
  substrate), `resolve_script_path`, `parse_exception`,
  `build_worker_source`, `MCP_INPUT_SCHEMA`, `not_run_verdict`.
- `tests/execution/test_python_exec_modes.py` — 32 tests, no isolation:
  modes, containment, approvals, bounds, schema, replay, verdicts.
- `tests/execution/test_python_exec_live.py` — 10 live worker tests:
  gdsfactory cell-build, curve fit, ledger effects, child run_ids,
  exception location, timeout, cancel, crash, interpreter, NOT_RUN.
- `tests/execution/test_python_exec_wiring.py` — 7 integrator tests, run
  AFTER applying the wiring patch (skip loudly before it).
- `docs/work/PYTHON-EXEC/wiring.patch` — exact wiring diff for existing
  files (this report embeds it verbatim below).
- `docs/work/PYTHON-EXEC/report.md` — this file.

## Design (what the ticket's clauses became)

- **Two modes, no more**: `mode: lines` takes inline text (≤64 KiB,
  non-empty); `mode: path` takes a project-relative script resolved with
  the `PATH-GUARD` `join_contained` helper — absolute paths, `..`, and
  symlink escapes raise `path_escape`; missing/non-files raise
  `invalid_path`. Any mode/field mismatch raises `invalid_command`.
- **Shared prepared substrate**: the runner reuses `BwrapRunner`,
  `worker_profile`, `CredentialGate`, `clean_stream`, and the
  revoke-plus-confirmed-tree-kill lifecycle; the interpreter is the
  prepared profile's Python (venv) with its full symlink chain bound
  read-only, so gdsfactory/numpy resolve inside the sandbox. No admission
  means `isolation_unavailable` — never a host fallback.
- **Approvals ≠ job state**: `pending_approval`/`approved`/`denied`/
  `expired` live in the approval ledger; `queued`/`running`/`completed`/
  `cancelled` live in the `ExecutionService` job surface. Denial/expiry
  create no run. `resolve_approval` requires `via="ui"` — any agent/MCP
  route raises `approval_forbidden`. Bindings pin code hash, history
  cursor, env digest, revision, and generation; request_id replays are
  idempotent, changed code conflicts.
- **Effects as data**: the cell records `tools.<op>` calls to a scratch
  JSONL log; the host replays each through the shared op dispatch after
  the worker exits. Child `run_ids`, per-op results, and skip counts ride
  on the terminal record. Replay is verbatim (console precedent): the
  caller binds `expected_revision` on mutating ops.
- **Zero exit never PASS**: every terminal record carries a `NOT_RUN`
  verdict with a reason pointing at the record; the Engine patch appends
  the `run_failed` ledger event that owns the NOT_RUN shape. Check
  verdicts stay with qualified evaluators.
- **Timeouts + cancel**: bounded default 120 s, explicit override
  1–1800 s; cancel works before dispatch (never spawns) and mid-run
  (50 ms poll slices kill the worker tree).

## RED → GREEN evidence

New tests written first, module absent:

- Command: `PYTHONPATH=/tmp/pyexec_rocket MPLCONFIGDIR=/tmp/mplcfg
  .venv/bin/python -m pytest tests/execution/test_python_exec_modes.py
  tests/execution/test_python_exec_live.py
  tests/execution/test_python_exec_wiring.py --no-header -q`
- RED: `33 failed, 6 skipped, 8 errors` —
  `ImportError: cannot import name 'python_exec' from
  'rocket_engine.execution'`; wiring tests skipped pre-patch by design.

After implementing `src/execution/python_exec.py` (same command):

- GREEN: `42 passed, 7 skipped` (32 modes + 10 live; 7 wiring skips are
  the pre-patch probes).
- Neighbors: `tests/execution/test_console.py
  tests/execution/test_execution_service.py tests/execution/test_dispatch.py`
  → `30 passed`.
- Guards on the new module: `scripts/check_docstrings.py
  src/execution/python_exec.py` clean, `scripts/check_no_cloud.py` clean,
  no line over 100 chars.

Note: tests run with `PYTHONPATH=/tmp/pyexec_rocket` (a symlink
`rocket_engine -> <repo>/src`) because the installed `rocket_engine` copy
in `.venv` predates new modules and `uv sync` / `.venv` writes are
forbidden to this lane. The integrator's reinstall removes the need.

## Integrator instructions

1. Apply: `git apply docs/work/PYTHON-EXEC/wiring.patch`
   (verified: `git apply --check` passes on this tree).
2. Regen (after ALL lane patches merge):
   `python scripts/api_spec.py --write && python scripts/contract.py --write`
3. Verify: `python scripts/api_spec.py --check &&
   python scripts/contract.py --check` (both exit 0), then run
   `tests/execution/test_python_exec_wiring.py` (7/7 green post-patch),
   plus `tests/test_api_spec.py tests/test_contract.py
   tests/test_check_contract.py`.
4. Reinstall the package so `import rocket_engine` picks up the new
   module without the `PYTHONPATH` shim.

Scratch-clone proof (patch applied + regen in `/tmp/pyexec_verify`):
wiring 7/7 green, modes 32/32, `test_api_spec`/`test_contract`/
`test_check_contract` green (1 pre-existing environmental skip: "no fuel
checkout beside the engine"), both `--check` gates exit 0.

## Refusals

- Edited no existing file (composition/server/vocabulary/scripts/docs):
  all wiring is delivered as the patch below. Refused per lane ownership.
- Ran no full suite: only new tests + named neighbors, per lane rules.
- Did not commit or push: a later integrator commits.
- Did not touch `tests/pdk_*/` or `docs/pdk/*/` (PDK-lane owned).
- Did not add `python_execute` to `list_job_kinds` (deck-tool shaped;
  approval-gated ops don't fit) — left for a follow-up.
- Did not unify the worker prelude with the stdio console's: the new
  module keeps its own prelude to avoid an execution→adapter dependency
  inversion; unification (e.g. moving the prelude to shared core) is a
  proposed follow-up, not smuggled into this patch.
- Regenerated docs (`engine-api.md`, `api-schema.json`, `api-help.json`,
  `contract.json`) are NOT in the patch: regen must run after all lane
  patches merge, or outputs go stale.

## Wiring patch (exact, also in `wiring.patch`)

```diff
diff --git a/scripts/api_spec.py b/scripts/api_spec.py
index f808d22..8a94873 100644
--- a/scripts/api_spec.py
+++ b/scripts/api_spec.py
@@ -21,6 +21,8 @@ Contract sources read (all AST, all code):
 - adapter preflight/execute/parse docstrings — Returns/Raises,
 - ProjectService method docstrings — CRUD/query Args/Returns/Raises,
 - Engine._run_queued docstring — run_job contract.
+- execution/python_exec.py request_execution docstring —
+  python_execute contract (Engine-direct op).
 
 Conventions honored: `Job keys:` / `Request keys:` sections list
 `name:` or `name (required):` items; envelope plumbing
@@ -384,6 +386,17 @@ def endpoint_spec(name, root=None):
         spec["summary"] = parse_docstring(doc_of(
             "composition.py", "Engine._run_queued", root=root
         ))["summary"]
+    elif name == "python_execute":
+        spec["wired"] = True
+        spec["handlers"] = [
+            "rocket_engine.composition.Engine.submit",
+            "rocket_engine.execution.python_exec."
+            "PythonExecService.request_execution",
+        ]
+        spec["summary"] = parse_docstring(doc_of(
+            "execution/python_exec.py",
+            "PythonExecService.request_execution", root=root
+        ))["summary"]
     elif name in qmethods:
         spec["wired"] = True
         spec["handlers"] = [
@@ -457,6 +470,21 @@ def section_body(name, root=None):
             _optional_block("Returns", parsed["returns"]),
             _optional_block("Raises", parsed["raises"]),
         ])
+    if name == "python_execute":
+        parsed = parse_docstring(doc_of(
+            "execution/python_exec.py",
+            "PythonExecService.request_execution", root=root
+        ))
+        return _join_blocks([
+            spec["summary"],
+            "Handler: `rocket_engine.composition.Engine.submit` "
+            "(submit opens a pending approval; the human UI route "
+            "resolves it, then `run_job` executes the admitted run).",
+            _arguments_block(parsed["job_keys"]),
+            _optional_block("Returns", parsed["returns"]),
+            _optional_block("Raises", parsed["raises"]),
+            "\n".join(f"Caution: {c}" for c in parsed["cautions"]),
+        ])
     return (
         spec["summary"]
         + "\n\n`Engine.submit` raises `unsupported_operation` for this "
@@ -650,6 +678,18 @@ def _schema_for(name, kind, solvers, crud, qmethods, qengines,
         schema["returns"] = parsed["returns"]
         schema["raises"] = parsed["raises"]
         return schema
+    if name == "python_execute":
+        parsed = parse_docstring(doc_of(
+            "execution/python_exec.py",
+            "PythonExecService.request_execution", root=root
+        ))
+        schema["properties"] = {
+            n: {"description": d} for n, _r, d in parsed["job_keys"]
+        }
+        schema["required"] = [n for n, r, _d in parsed["job_keys"] if r]
+        schema["returns"] = parsed["returns"]
+        schema["raises"] = parsed["raises"]
+        return schema
     schema["returns"] = ""
     return schema
 
diff --git a/src/adapters/mcp/server.py b/src/adapters/mcp/server.py
index 6956cc0..dd84f4a 100644
--- a/src/adapters/mcp/server.py
+++ b/src/adapters/mcp/server.py
@@ -28,6 +28,7 @@ from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
 from ruamel.yaml import YAML
 
 from ...execution.errors import ExecutionError
+from ...execution.python_exec import MCP_INPUT_SCHEMA
 from ...interfaces.vocabulary import OPERATIONS, QUERIES
 from ...project.errors import ProjectError
 from ..errors import AdapterError
@@ -36,6 +37,11 @@ from . import McpTransport
 _ENGINE_ERRORS = (AdapterError, ProjectError, ExecutionError)
 
 
+_TOOL_SCHEMAS = {
+    "python_execute": MCP_INPUT_SCHEMA,
+}
+
+
 _HELP_ENGINE = None
 
 
@@ -94,6 +100,12 @@ def describe_tool(name):
         # run_job's contract doc lives on the phase-2 runner
         # (introspection only; never called for help).
         return _summary_of(Engine._run_queued)
+    if name == "python_execute":
+        # python_execute's contract doc lives on the approval
+        # request (introspection only; never called for help).
+        from ...execution.python_exec import PythonExecService
+
+        return _summary_of(PythonExecService.request_execution)
     if name in OPERATIONS and hasattr(ProjectService, name):
         return _summary_of(getattr(ProjectService, name))
     method = QUERY_METHODS.get(name)
@@ -120,7 +132,7 @@ def tool_definitions():
         tools.append(Tool(
             name=name,
             description=describe_tool(name),
-            inputSchema={"type": "object"},
+            inputSchema=_TOOL_SCHEMAS.get(name, {"type": "object"}),
         ))
     return tools
 
diff --git a/src/composition.py b/src/composition.py
index 576c431..f62d2d5 100644
--- a/src/composition.py
+++ b/src/composition.py
@@ -42,7 +42,9 @@ from .adapters.lvs_netgen import NetgenLvsAdapter
 from .adapters.ngspice import NgspiceAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
+from .execution.dispatch import OpDispatcher
 from .execution.errors import ExecutionError
+from .execution.python_exec import PythonExecService
 from .execution.service import ExecutionService
 from .interfaces.setup import report_capabilities
 from .interfaces.vocabulary import OPERATIONS, QUERIES
@@ -84,6 +86,7 @@ QUERY_ENGINE_METHODS = {
     "get_check_results": "check_results",
     "get_logs": "run_logs",
     "list_job_kinds": "job_kinds",
+    "get_python_console": "python_console",
 }
 
 # Job-result queries served from execution state (plus the captured run log).
@@ -140,10 +143,13 @@ class Engine:
         constraints: Optional run_spice metric targets
             ({metric: {min, max, unit[, expr, control]}}); caller
             targets are refused, unknown metrics fail loudly.
+        project_dir: Project folder python_execute path mode
+            resolves inside; path mode refuses loudly without one.
     """
 
     def __init__(self, project_id, actor, catalog_root=".",
-                 engine_root=None, linked_root=None, constraints=None):
+                 engine_root=None, linked_root=None, constraints=None,
+                 project_dir=None):
         self._project_id = project_id
         self._actor = actor
         self._project = ProjectService(
@@ -166,6 +172,13 @@ class Engine:
         self._logs = {}
         self._latest = {}
         self._run_jobs = {}
+        self._pyexec = PythonExecService(
+            project_id, actor,
+            execution=self._execution,
+            project_root=project_dir,
+            dispatcher=OpDispatcher(
+                self, project_id=project_id, actor=actor),
+        )
 
     def snapshot(self):
         """Read the current project snapshot.
@@ -233,7 +246,7 @@ class Engine:
             self._solvers,
             target=target,
             engine_root=engine_root,
-            served=_CRUD_OPERATIONS | {"run_job"},
+            served=_CRUD_OPERATIONS | {"run_job", "python_execute"},
         )
 
     def submit(self, command):
@@ -257,8 +270,9 @@ class Engine:
             mapping for get_capabilities, the event page for
             get_events_since, the project/document listing for
             the CRUD queries, the status/checks/logs/kinds for
-            the job-result queries, or the completed mapping for
-            run_job.
+            the job-result queries, the completed mapping for
+            run_job, the approval handle for python_execute, or
+            the console view for get_python_console.
 
         Raises:
             ProjectError: cross_project_denied for a foreign
@@ -295,6 +309,8 @@ class Engine:
                 target=arguments.get("target"),
                 engine_root=arguments.get("engine_root"),
             )
+        if name == "get_python_console":
+            return self.python_console()
         if name == "get_events_since":
             return self._query_events_since(arguments)
         if name == "list_projects":
@@ -321,6 +337,8 @@ class Engine:
             return self.run(command)
         if name in _CRUD_OPERATIONS:
             return self._submit_crud(name, arguments, command)
+        if name == "python_execute":
+            return self._submit_pyexec(arguments, command)
         if not self._solvers.get(name):
             raise ProjectError(
                 "unsupported_operation", f"No solver registered: {name}."
@@ -443,6 +461,134 @@ class Engine:
             expected_revision=arguments.get("expected_revision"),
         )
 
+    def _submit_pyexec(self, arguments, command):
+        """Admit a python_execute request: gate, then open an approval.
+
+        Shape validation runs before the revision gate so malformed
+        requests fail before anything is persisted or queued; the
+        gated submit then advances the revision and appends
+        job_queued like every other operation. The ack run_id IS
+        the execution id: approval admits it, run_job executes it.
+
+        Args:
+            arguments: python_execute arguments (mode plus lines
+                or path, timeout_s, artifacts, expected_revision).
+            command: Envelope carrying request_id.
+
+        Returns:
+            Admission mapping with the ack fields plus
+                execution_id, approval_id, and pending_approval
+                state. No run exists until the UI route approves.
+
+        Raises:
+            ProjectError: revision_conflict for a stale
+                expected_revision, request_conflict for a reused
+                envelope id with new text.
+            ExecutionError: invalid_command/invalid_cell/empty_cell
+                for malformed requests, path_escape/invalid_path/
+                cell_unreadable for bad project files.
+        """
+        self._pyexec.validate_request(
+            arguments.get("mode"),
+            lines=arguments.get("lines"),
+            path=arguments.get("path"),
+            artifacts=arguments.get("artifacts", ()),
+            timeout_s=arguments.get("timeout_s"),
+        )
+        buf = io.StringIO()
+        self._yaml.dump(
+            {"operation": "python_execute", "arguments": arguments}, buf)
+        request_id = command.get("request_id") or uuid.uuid4().hex
+        ack = self._project.submit(
+            buf.getvalue(),
+            str(request_id),
+            expected_revision=arguments.get("expected_revision"),
+        )
+        handle = self._pyexec.request_execution(
+            arguments["mode"],
+            lines=arguments.get("lines"),
+            path=arguments.get("path"),
+            request_id=str(request_id),
+            run_id=ack["run_id"],
+            expected_revision=arguments.get("expected_revision"),
+            artifacts=arguments.get("artifacts", ()),
+            timeout_s=arguments.get("timeout_s"),
+        )
+        self._run_jobs.setdefault(
+            ack["run_id"],
+            {
+                "operation": "python_execute",
+                "arguments": dict(arguments),
+                "snapshot_id": ack["snapshot_id"],
+                "request_id": str(request_id),
+            },
+        )
+        return {**ack, **handle, "state": "pending_approval"}
+
+    def resolve_python_approval(self, approval_id, decision, actor=None):
+        """Resolve a python_execute approval via the human UI route.
+
+        Agent calls request approval; they never grant it — this
+        method is the trusted UI route, and no MCP tool maps to it.
+
+        Args:
+            approval_id: Approval bound by the submit call.
+            decision: `approved` to admit the queued run, `denied`
+                to lapse the approval with no run.
+            actor: Human actor the decision is attributed to; the
+                engine actor when omitted.
+
+        Returns:
+            Resolution with approval_id, approval_state,
+                execution_id, and the run_id once admitted.
+
+        Raises:
+            ExecutionError: approval_invalid/approval_denied/
+                approval_expired/approval_forbidden per the
+                approval ledger.
+
+        Caution: Human route only — MCP agents must never call
+            this; there is deliberately no MCP tool for it.
+        """
+        return self._pyexec.resolve_approval(
+            approval_id, decision, via="ui",
+            actor=actor if actor is not None else self._actor,
+        )
+
+    def python_console(self):
+        """Read the python_execute console view.
+
+        Returns:
+            Console view with project_id, generation, env_digest,
+                history cursor, and pending approvals.
+
+        Caution: Read-only: reports approval queue state, never
+            resolves anything.
+        """
+        return self._pyexec.console_view()
+
+    def cancel_job(self, run_id=None):
+        """Cancel a queued or running job through the job surface.
+
+        A live python_execute worker tree is killed promptly;
+        finished runs keep their terminal state, truthfully.
+
+        Args:
+            run_id: Admitted execution id to cancel.
+
+        Returns:
+            Mapping with run_id and state.
+
+        Raises:
+            ProjectError: invalid_command without a run_id.
+            ExecutionError: unknown_run for an id never admitted.
+        """
+        if run_id is None:
+            raise ProjectError(
+                "invalid_command", "cancel_job needs a run_id argument."
+            )
+        return self._pyexec.cancel(run_id)
+
     def _select_solver(self, name, arguments):
         solvers = self._solvers.get(name) or {}
         if not solvers:
@@ -746,6 +892,8 @@ class Engine:
             snapshot_id = ack.get("snapshot_id", "")
             request_id = str(request_id)
             run_id = ack.get("run_id")
+        if stored_operation == "python_execute":
+            return self._run_pyexec(run_id, request_id)
         if not self._solvers.get(stored_operation):
             raise ProjectError(
                 "unsupported_operation", f"No solver registered: {stored_operation}."
@@ -763,6 +911,58 @@ class Engine:
             contain=True,
         )
 
+    def _run_pyexec(self, run_id, request_id):
+        """Execute an admitted python_execute run (phase 2).
+
+        Approval lapses propagate as approval errors — approval
+        state is never folded into a verdict. Completion carries
+        the NOT_RUN verdict (zero exit is never check PASS) and
+        appends the run_failed ledger event the NOT_RUN shape
+        owns; cancellation returns the cancelled state with no
+        ledger event, like every cancelled job.
+
+        Args:
+            run_id: Admitted execution id (the submit ack id).
+            request_id: Queued request this run discharges.
+
+        Returns:
+            Completion mapping with run_id, state, verdict, and
+                operation.
+
+        Raises:
+            ExecutionError: unknown_run for an id never admitted,
+                approval_pending/approval_denied/approval_expired
+                when the approval lapses, approval_invalid for
+                binding drift.
+
+        Caution: Runs the approved worker now — read the verdict
+            (always NOT_RUN) plus the execution record, never the
+            exit path.
+        """
+        record = self._pyexec.run_job(run_id)
+        self._latest["python_execute"] = run_id
+        log = record.get("stdout", "")
+        if record.get("stderr"):
+            log += "\n--- stderr ---\n" + record["stderr"]
+        self._logs[run_id] = log
+        if record["state"] == "cancelled":
+            return {
+                "run_id": run_id,
+                "state": "cancelled",
+                "verdict": record["verdict"],
+                "operation": "python_execute",
+            }
+        self._project.append_run_event(
+            "run_failed", run_id, "python_execute", record["verdict"],
+            request_id,
+        )
+        return {
+            "run_id": run_id,
+            "state": "completed",
+            "verdict": record["verdict"],
+            "operation": "python_execute",
+        }
+
     def _run_operation(self, name, arguments, snapshot_id, request_id, run_id=None, contain=False):
         """Select the solver, run it, judge the verdict, log completion."""
         solvers = self._solvers.get(name) or {}
@@ -922,6 +1122,12 @@ class Engine:
             return self._run_queued(command)
         if name in _CRUD_OPERATIONS:
             return self.submit(command)
+        if name == "python_execute":
+            raise ProjectError(
+                "invalid_command",
+                "python_execute needs submit, human approval, then "
+                "run_job; direct run cannot approve.",
+            )
         arguments = self._apply_targets(name, dict(command.get("arguments") or {}))
         return self._run_operation(
             name,
diff --git a/src/execution/__init__.py b/src/execution/__init__.py
index 0df8509..0e57ed6 100644
--- a/src/execution/__init__.py
+++ b/src/execution/__init__.py
@@ -3,6 +3,16 @@
 from .console import ConsoleSession, get_help
 from .dispatch import OpDispatcher, parse_op_call, parse_op_tokens
 from .errors import ExecutionError, UsageError
+from .python_exec import (
+    MCP_INPUT_SCHEMA,
+    PythonExecRunner,
+    PythonExecService,
+    build_worker_source,
+    not_run_verdict,
+    parse_exception,
+    prelude_digest_for,
+    resolve_script_path,
+)
 from .runner import BwrapRunner
 from .service import ExecutionService
 from .worker import CellRunner, CredentialGate, worker_profile
@@ -14,10 +24,18 @@ __all__ = [
     "CredentialGate",
     "ExecutionError",
     "ExecutionService",
+    "MCP_INPUT_SCHEMA",
     "OpDispatcher",
+    "PythonExecRunner",
+    "PythonExecService",
     "UsageError",
+    "build_worker_source",
     "get_help",
+    "not_run_verdict",
+    "parse_exception",
     "parse_op_call",
     "parse_op_tokens",
+    "prelude_digest_for",
+    "resolve_script_path",
     "worker_profile",
 ]
```

