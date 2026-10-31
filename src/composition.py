"""Composition root (B9): the Engine wires core modules for adapters.

Adapters construct against this, never against services directly. The
root owns no domain logic: it routes cataloged names (see
`interfaces.vocabulary`) to live module state. Operations queue through
the project service with revision gating and envelope-id idempotency;
CRUD mutations (CRUD-API/I31) and rewind (REWIND) execute immediately
through the same admission machinery with no queue and no solver;
every accepted mutation advances the revision and appends an
actor-attributed event to the durable ledger (LEDGER-DURABLE/I30),
and every run appends its completion with a verdict link. Only wired
queries read state, the rest honestly report unwired.
Two-phase execution: `submit(op)` admits and returns an ack, then
`run_job` executes the admitted command — over `run()` directly or
over submit-only transports via `submit(run_job)`. The ack run_id is
the execution id: `get_job_status` reports queued after submit and the
verdict after `run_job`; nothing runs implicitly (no auto-drain).
With `constraints` (metric -> {min, max, unit[, expr, control]}),
run_spice targets come from the project, never the caller:
caller-supplied min/max — or a caller expr where the project defines
one — is refused.
`run()` executes registered solvers synchronously. Each operation
maps to named solvers; `deck.tool` selects one, defaulting to the
first registered (run_drc: magic, then klayout; run_optical: sax;
run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
run_syntax: slang; run_hdl_test: icarus).
Unregistered operations and unknown deck tools raise instead of
faking a verdict.
"""

import io
import uuid

from ruamel.yaml import YAML

from .adapters.drc import MagicDrcAdapter
from .adapters.drc_kl import KlayoutDrcAdapter
from .adapters.errors import AdapterError
from .adapters.extract_magic import MagicExtractAdapter
from .adapters.hdl_sim import HdlSimAdapter
from .adapters.lvs_netgen import NetgenLvsAdapter
from .adapters.ngspice import NgspiceAdapter
from .adapters.sax import SaxAdapter
from .adapters.syntax import SyntaxAdapter
from .execution.block_runs_scope import (
    BlockScopeError,
    build_scope_record,
    check_operation_scope,
    narrow_job_for_block,
    parse_target,
    resolve_block,
    snapshot_closure,
    stamp_verdict,
)
from .execution.errors import ExecutionError
from .execution.service import ExecutionService
from .interfaces.runparams import RunParamsError, validate_run_request
from .interfaces.setup import report_capabilities
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.catalog import Catalog
from .project.errors import ProjectError
from .project.service import ProjectService

_WIRED_QUERIES = frozenset(
    {
        "get_project_snapshot",
        "get_capabilities",
        "get_events_since",
        "list_projects",
        "list_docs",
        "read_doc",
    }
)

# Wired query -> ProjectService method serving it. Engine.submit keeps
# its explicit dispatch (argument checks differ per query); this map
# is the docs/help seam — scripts/api_spec.py and the MCP server read
# handler docstrings through it, so a rewired query updates here.
QUERY_METHODS = {
    "get_project_snapshot": "snapshot",
    "get_events_since": "events_since",
    "list_projects": "list_projects",
    "list_docs": "list_docs",
    "read_doc": "read_doc",
}

# Wired query -> Engine method serving it. Same docs/help seam as
# QUERY_METHODS, for the queries the composition root answers
# itself (solver + store introspection the project ledger cannot
# serve). scripts/api_spec.py and the MCP server read Engine
# handler docstrings through this map.
QUERY_ENGINE_METHODS = {
    "get_capabilities": "capabilities",
    "get_job_status": "job_status",
    "get_check_results": "check_results",
    "get_logs": "run_logs",
    "list_job_kinds": "job_kinds",
}

# Job-result queries served from execution state (plus the captured run log).
_JOB_QUERIES = frozenset(
    {"get_job_status", "get_check_results", "get_logs", "list_job_kinds"}
)

# A get_logs page never dumps more than this many lines at once.
_LOG_PAGE_MAX = 200

# CRUD mutations + rewind execute immediately inside submit()
# (run_job precedent): revision gate + idempotency + event logging,
# no queue, no solver. Engine.run delegates them back to submit so
# the CLI `run` path shares the one implementation.
_CRUD_OPERATIONS = frozenset(
    {
        "create_project",
        "write_doc",
        "delete_doc",
        "apply_mutations",
        "rewind",
    }
)

# Adapter violation key -> finding location key. bbox keeps its legacy
# lambda-units name; everything else passes through unchanged.
_LOCATION_KEYS = (
    ("bbox", "bbox_lambda"),
    ("bbox_um", "bbox_um"),
    ("area", "area"),
    ("file", "file"),
    ("line", "line"),
    ("col", "col"),
    ("sim_time", "sim_time"),
)


class Engine:
    """Composition root: one bound project plus its solvers and services.

    Args:
        project_id: Project this engine is bound to; cross-project
            envelopes are denied, never routed.
        actor: Attribution for mutations this engine submits
            (human / rocket-fuel / system); passed through to every
            ledger event verbatim.
        catalog_root: Root the component catalog resolves against.
        engine_root: Engine root for ledger durability; the log
            persists under `projects/<project_id>/` beneath it.
            None keeps the in-memory ledger.
        linked_root: Caller tree for linked projects; rewind
            reports files outside `.rocket/` and never writes
            there. None means a managed project.
        constraints: Optional run_spice metric targets
            ({metric: {min, max, unit[, expr, control]}}); caller
            targets are refused, unknown metrics fail loudly.
        blocks: Optional block store for block-scoped runs (a
            mapping of id to block entity, or a list of block
            mappings); runs without a block target never read it.
    """

    def __init__(self, project_id, actor, catalog_root=".",
                 engine_root=None, linked_root=None, constraints=None,
                 blocks=None):
        self._project_id = project_id
        self._actor = actor
        self._blocks = blocks if blocks is not None else {}
        self._project = ProjectService(
            project_id, actor, engine_root=engine_root,
            linked_root=linked_root,
        )
        self._execution = ExecutionService(project_id)
        self._catalog = Catalog(catalog_root)
        self._solvers = {
            "run_drc": {"magic": MagicDrcAdapter(), "klayout": KlayoutDrcAdapter()},
            "run_hdl_test": {"icarus": HdlSimAdapter()},
            "run_optical": {"sax": SaxAdapter()},
            "run_extraction": {"magic": MagicExtractAdapter()},
            "run_lvs": {"netgen": NetgenLvsAdapter()},
            "run_spice": {"ngspice": NgspiceAdapter()},
            "run_syntax": {"slang": SyntaxAdapter()},
        }
        self._yaml = YAML(typ="safe")
        self._constraints = dict(constraints) if constraints is not None else None
        self._logs = {}
        self._latest = {}
        self._run_jobs = {}

    def snapshot(self):
        """Read the current project snapshot.

        Returns:
            Snapshot mapping for the bound project.
        """
        return self._project.snapshot()

    def events_since(self, cursor, require_contiguous_from=None):
        """Read ledger events after a cursor.

        Args:
            cursor: Opaque position from a previous read.
            require_contiguous_from: Assert contiguous history from
                this seq; unmet demands fail instead of gap-hiding.

        Returns:
            Events appended after the cursor, oldest first.

        Raises:
            ProjectError: resync_required when the contiguity
                demand cannot be met — re-read the snapshot plus
                the full retained log and reset the cursor.
        """
        return self._project.events_since(
            cursor, require_contiguous_from=require_contiguous_from
        )

    def capabilities(self, target=None, engine_root=None):
        """Report per-solver availability, store state, and the provision menu.

        The engine side of the Vivado-style setup surface: every
        cataloged operation with readiness (ready when some
        registered tool resolves, or when the Engine serves the
        operation directly; blocked with reason + missing items
        + remedy when no tool resolves; unsupported when no
        solver is registered), each tool's availability from its
        own detection probe plus its adapter capabilities(),
        PDK/deck install state from the store, BYOC-gated cloud
        rows, and the checkbox provision catalogue with live
        install state.

        Args:
            target: Target passed to each adapter's capabilities().
            engine_root: Explicit store root; ROCKETEDA_HOME
                resolution when omitted.

        Returns:
            Capability mapping with operations, store, pdks,
                decks, cloud, and catalogue sections.

        Raises:
            SetupError: unknown_solver when a registered
                (operation, tool) has no detection spec — the
                report fails instead of misreporting a solver it
                cannot probe.

        Caution: Read-only: never creates the store skeleton and
            never attempts network — cloud rows report gated with
            key_state missing until CLOUD-AUTH supplies keys plus
            an explicit opt-in (F12/I32 BYOC).
        """
        return report_capabilities(
            self._solvers,
            target=target,
            engine_root=engine_root,
            served=_CRUD_OPERATIONS | {"run_job"},
        )

    def submit(self, command):
        """Admit an operation (phase 1) or serve a wired query.

        Operations queue through the project service with revision
        gating and envelope-id idempotency; CRUD mutations and
        rewind execute immediately through the same admission
        machinery (no queue, no solver); only wired queries read
        state, the rest honestly report unwired.

        Args:
            command: Envelope with project_id, operation, arguments,
                and request_id.

        Returns:
            Admission ack for queued operations, the immediate
            mutation mapping (new revision + events + approval-UI
            fields) for CRUD/rewind operations, the snapshot for
            the wired get_project_snapshot query, the capability
            mapping for get_capabilities, the event page for
            get_events_since, the project/document listing for
            the CRUD queries, the status/checks/logs/kinds for
            the job-result queries, or the completed mapping for
            run_job.

        Raises:
            ProjectError: cross_project_denied for a foreign
                envelope, unsupported_operation for an unwired or
                unknown name, unknown_block for a block target
                naming no block, invalid_target for a malformed
                target, unsupported_scope for a block target on a
                verb serving no block runs yet, unknown_run_param
                for an unknown run.request field, invalid_run_param
                for a mistyped run.request knob, invalid_run_request
                for a non-mapping run.request, invalid_command
                for caller-supplied run_spice targets,
                revision_conflict for a stale
                expected_revision, invalid_command for a malformed
                get_events_since cursor, a malformed mutation, or
                a rewind that lacks a target or targets the live
                head, resync_required when a get_events_since
                contiguity demand cannot be met, invalid_project
                for a bad project id, project_exists for a
                duplicate create, unknown_document for a missing
                document, unknown_revision for a rewind target
                with no snapshot, invalid_path or path_escape for
                a bad document path, request_conflict for a reused
                envelope id with new text.

        Caution: Bound to one project: cross-project envelopes are
            denied, never routed — and a stale expected_revision
            fails instead of merging.
        """
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )
        name = command.get("operation")
        arguments = dict(command.get("arguments") or {})
        arguments = self._apply_targets(name, arguments)
        arguments = self._apply_run_request(arguments)
        if name == "get_capabilities":
            return self.capabilities(
                target=arguments.get("target"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "get_events_since":
            return self._query_events_since(arguments)
        if name == "list_projects":
            return self._project.list_projects()
        if name == "list_docs":
            return self._project.list_docs(prefix=arguments.get("prefix"))
        if name == "read_doc":
            if "path" not in arguments:
                raise ProjectError(
                    "invalid_command", "read_doc needs a path argument."
                )
            return self._project.read_doc(arguments["path"])
        if name in _JOB_QUERIES:
            return self._query_job(name, arguments)
        if name in _WIRED_QUERIES:
            return self._project.snapshot()
        if name in QUERIES or name not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation", f"Operation not wired yet: {name}."
            )
        if name == "run_job":
            # Phase 2 executes immediately: admission (and its revision
            # gate) already happened at submit time.
            return self.run(command)
        if name in _CRUD_OPERATIONS:
            return self._submit_crud(name, arguments, command)
        if not self._solvers.get(name):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        scope_request = self._admit_block_scope(name, arguments)
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        ack = self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )
        # The ack run_id is the execution id: register its queued
        # record now so get_job_status can poll it — and run_job can
        # execute it — under the one id. A replay returns the same
        # ack; its record already exists, so register it only once.
        if not self._execution.known(ack["run_id"]):
            target = {"cell": arguments.get("cell")}
            if scope_request is not None:
                target["scope"] = "block"
                target["block_id"] = scope_request["block_id"]
            self._execution.dispatch(
                name, target, ack["snapshot_id"], run_id=ack["run_id"]
            )
        self._run_jobs.setdefault(
            ack["run_id"],
            {
                "operation": name,
                "arguments": arguments,
                "snapshot_id": ack["snapshot_id"],
                "request_id": str(request_id),
            },
        )
        if scope_request is not None:
            pending = self._run_jobs[ack["run_id"]]
            if "block_scope" not in pending:
                pending["block_scope"] = build_scope_record(
                    run_id=ack["run_id"],
                    revision=self._project.snapshot()["current_revision"],
                    block_id=scope_request["block_id"],
                    deck=arguments.get("deck"),
                    closure=scope_request["closure"],
                )
        return ack

    def _query_events_since(self, arguments):
        """Serve the wired get_events_since query (cursor + resync)."""
        cursor = arguments.get("cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool):
            raise ProjectError(
                "invalid_command", f"Cursor must be an int, got {cursor!r}."
            )
        demand = arguments.get("require_contiguous_from")
        if (
            demand is not None
            and (not isinstance(demand, int) or isinstance(demand, bool))
        ):
            raise ProjectError(
                "invalid_command",
                f"require_contiguous_from must be an int, got {demand!r}.",
            )
        events = self._project.events_since(
            cursor, require_contiguous_from=demand
        )
        return {
            "project_id": self._project_id,
            "events": events,
            "cursor": self._project.snapshot()["event_cursor"],
        }

    def _submit_crud(self, name, arguments, command):
        """Execute one CRUD/rewind mutation immediately (no queue)."""
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        command_text = buf.getvalue()
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        if name == "create_project":
            if "new_project_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "create_project needs a new_project_id argument.",
                )
            return self._project.create_project(
                arguments["new_project_id"], request_id, command_text
            )
        if name == "write_doc":
            if "path" not in arguments or "content" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "write_doc needs path and content arguments.",
                )
            return self._project.write_doc(
                arguments["path"],
                arguments["content"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_doc":
            if "path" not in arguments:
                raise ProjectError(
                    "invalid_command", "delete_doc needs a path argument."
                )
            return self._project.delete_doc(
                arguments["path"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "rewind":
            if "target_revision" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "rewind needs a target_revision argument.",
                )
            return self._project.rewind(
                arguments["target_revision"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if "mutations" not in arguments:
            raise ProjectError(
                "invalid_command",
                "apply_mutations needs a mutations argument.",
            )
        return self._project.apply_mutations(
            arguments["mutations"],
            request_id,
            command_text,
            expected_revision=arguments.get("expected_revision"),
        )

    def _select_solver(self, name, arguments):
        solvers = self._solvers.get(name) or {}
        if not solvers:
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        hint = (arguments.get("deck") or {}).get("tool")
        if hint is None:
            return next(iter(solvers.values()))
        try:
            return solvers[hint]
        except KeyError:
            raise ProjectError(
                "unsupported_operation",
                f"No {name} solver for deck tool: {hint}.",
            ) from None

    def _apply_targets(self, name, arguments):
        """Fill run_spice metric targets from project constraints.

        Caller-supplied min/max are refused (invalid_command):
        the agent must not grade its own homework. Metrics
        without a constraint entry fail loudly, listing the
        constrained ones.
        """
        if name != "run_spice" or self._constraints is None:
            return arguments
        measurements = arguments.get("measurements")
        if not isinstance(measurements, list):
            return arguments  # the adapter's preflight reports the shape error
        filled = []
        control = []
        for item in measurements:
            if not isinstance(item, dict):
                filled.append(item)
                continue
            metric = item.get("name")
            if "min" in item or "max" in item:
                raise ProjectError(
                    "invalid_command",
                    "Targets come from the project's constraints, not the call: "
                    f"remove min/max from {metric!r}.",
                )
            target = self._constraints.get(metric)
            if target is None:
                raise ProjectError(
                    "invalid_command",
                    f"No target for {metric!r} in the project's constraints; "
                    f"constrained metrics: {sorted(self._constraints)}.",
                )
            bounds = {key: target[key] for key in ("min", "max") if target.get(key) is not None}
            unit = item.get("unit") or target.get("unit", "")
            item = {**item, **bounds, "unit": unit}
            # How a metric is measured is part of the target: a caller formula could read anything.
            if target.get("expr") is not None:
                if item.get("expr") not in (None, "", target["expr"]):
                    raise ProjectError(
                        "invalid_command",
                        f"How {metric!r} is measured comes from the project's constraints; "
                        "omit expr.",
                    )
                item["expr"] = target["expr"]
                for line in target.get("control") or []:
                    if line not in control:
                        control.append(line)
            filled.append(item)
        updated = {**arguments, "measurements": filled}
        if control:
            updated["analyses"] = list(arguments.get("analyses") or []) + control
        return updated

    def _apply_run_request(self, arguments):
        """Validate and freeze the explicit run.request knobs (RUN-PARAMS).

        Every submit carries its knobs explicitly: a missing
        `request` freezes to all defaults, a partial one fills
        defaults, and unknown fields fail loudly — never
        ignored. All callers (IDE, MCP, console) share this one
        path, so the shape is identical whoever submits.

        Args:
            arguments: Submitted arguments, maybe with `request`.

        Returns:
            Arguments with `request` normalized to every knob.

        Raises:
            ProjectError: unknown_run_param for an unknown
                field, invalid_run_param for a mistyped knob,
                invalid_run_request for a non-mapping
                `request`.
        """
        try:
            normalized = validate_run_request(arguments.get("request"))
        except RunParamsError as exc:
            raise ProjectError(exc.code, str(exc), fields=exc.fields) from exc
        return {**arguments, "request": normalized}

    def _admit_block_scope(self, name, arguments):
        """Validate a block run target and snapshot its closure.

        Arguments without a target run at project scope and skip
        this path untouched; block targets resolve their entity
        and pin the component closure the verdict later cites.

        Args:
            name: Cataloged operation about to run.
            arguments: Operation arguments (target rides here).

        Returns:
            None for project runs, else the admitted scope with
                block_id and closure keys (the run_id-bound record
                is built once the ack id exists).

        Raises:
            ProjectError: unknown_block for a block target naming
                no block, invalid_target for a malformed target,
                unsupported_scope for a block target on a verb
                serving no block runs yet.
        """
        if "target" not in arguments:
            return None
        try:
            parsed = parse_target(arguments["target"])
            check_operation_scope(name, parsed["scope"])
            if parsed["scope"] != "block":
                return None
            block = resolve_block(parsed["id"], self._blocks)
            closure = snapshot_closure(block)
        except BlockScopeError as exc:
            raise ProjectError(exc.code, str(exc)) from exc
        return {"block_id": parsed["id"], "closure": closure}

    def job_status(self, run_id=None):
        """Read one run's state, verdict, and evidence links.

        Args:
            run_id: Run to inspect (the submit-ack id, shared
                with the execution record).

        Returns:
            Run state mapping with state, verdict, and log links.

        Raises:
            ExecutionError: unknown_run for an unregistered id.
        """
        return self._execution.status(run_id)

    def check_results(self, operation=None):
        """Read the latest check verdict per operation.

        Args:
            operation: Restrict to one operation; all latest
                verdicts when omitted.

        Returns:
            Mapping of operation to run state plus the current
            project revision.
        """
        checks = {}
        for op, run_id in self._latest.items():
            if operation and op != operation:
                continue
            status = self._execution.status(run_id)
            verdict = status.get("verdict") or {}
            checks[op] = {
                "run_id": run_id,
                "state": status["state"],
                "status": verdict.get("status"),
                "verdict": verdict,
            }
        return {
            "checks": checks,
            "current_revision": self._project.snapshot()["current_revision"],
        }

    def run_logs(self, run_id=None, query=None, offset=0, limit=40):
        """Search and page one run's captured native log.

        Args:
            run_id: Run whose log to read.
            query: Case-insensitive substring filter; all lines
                when omitted.
            offset: First matching line to return (0-based).
            limit: Maximum lines per page (capped server-side).

        Returns:
            Page mapping with numbered lines, totals, and a
            more flag.

        Raises:
            ExecutionError: unknown_run for an unregistered id.
            ProjectError: invalid_command for a non-int
                offset or limit.
        """
        return self._logs_page(
            {"run_id": run_id, "query": query, "offset": offset, "limit": limit}
        )

    def job_kinds(self):
        """List registered operations with their deck tools.

        Returns:
            Mapping of job kinds with operation names and the
            tool keys each accepts.
        """
        return {
            "job_kinds": [
                {"operation": operation, "tools": list(solvers)}
                for operation, solvers in sorted(self._solvers.items())
            ]
        }

    def _query_job(self, name, arguments):
        """Route a job-result query to its Engine reader."""
        if name == "get_job_status":
            return self.job_status(arguments.get("run_id"))
        if name == "get_check_results":
            return self.check_results(arguments.get("operation"))
        if name == "get_logs":
            return self.run_logs(
                arguments.get("run_id"),
                query=arguments.get("query"),
                offset=arguments.get("offset", 0),
                limit=arguments.get("limit", 40),
            )
        if name == "list_job_kinds":
            return self.job_kinds()
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _logs_page(self, arguments):
        run_id = arguments.get("run_id")
        self._execution.status(run_id)  # unknown runs raise unknown_run
        lines = self._logs.get(run_id, "").splitlines()
        numbered = [(index + 1, line) for index, line in enumerate(lines)]
        query = arguments.get("query")
        if query:
            numbered = [(n, line) for n, line in numbered if query.lower() in line.lower()]
        try:
            offset = max(0, int(arguments.get("offset", 0)))
        except (TypeError, ValueError):
            raise ProjectError(
                "invalid_command",
                f"get_logs offset must be an int, got {arguments.get('offset')!r}.",
            ) from None
        try:
            limit = max(1, min(int(arguments.get("limit", 40)), _LOG_PAGE_MAX))
        except (TypeError, ValueError):
            raise ProjectError(
                "invalid_command", f"get_logs limit must be an int, got {arguments.get('limit')!r}."
            ) from None
        page = numbered[offset : offset + limit]
        return {
            "run_id": run_id,
            "total_lines": len(lines),
            "matched": len(numbered),
            "offset": offset,
            "lines": [f"{n}: {line}" for n, line in page],
            "more": offset + limit < len(numbered),
        }

    def log_text(self, run_id):
        """Return the captured native log for a run.

        Args:
            run_id: Run whose native log to read.

        Returns:
            Captured log text, or "" when the run logged nothing.
        """
        return self._logs.get(run_id, "")

    def register_solver(self, operation, adapter, tool=None):
        """Register a solver adapter under an operation name.

        Args:
            operation: Cataloged operation the adapter serves.
            adapter: ToolAdapter owning the preflight/execute/parse
                round trip.
            tool: Deck-tool key selecting this adapter; defaults to
                the adapter class name.

        Returns:
            Mapping with the operation and tool key registered.
        """
        name = tool if tool is not None else type(adapter).__name__
        self._solvers.setdefault(operation, {})[name] = adapter
        return {"operation": operation, "tool": name}

    def solvers_for(self, operation):
        """Return the tool-keyed solvers serving one operation.

        Introspection for docs and MCP help: per-operation prose
        derives from the serving adapters' docstrings, so this map
        is the seam — never a second source. Deck-tool selection
        reads the keys; the default is the first registered.

        Args:
            operation: Cataloged operation name.

        Returns:
            Mapping of deck-tool key to serving adapter; empty
            when no solver is registered.
        """
        return dict(self._solvers.get(operation) or {})

    def findings(self, run_id, limit=50, cursor=None):
        """Read a page of findings for a completed run.

        Args:
            run_id: Run whose findings to read.
            limit: Maximum findings in this page.
            cursor: Opaque position from a previous page, if any.

        Returns:
            Finding page for the run.
        """
        return self._execution.findings(run_id, limit=limit, cursor=cursor)

    def _run_queued(self, command):
        """Execute an admitted request by id (phase 2 of submit-then-run).

        Request keys:
            request_id (required): Envelope id admitted by an
                earlier submit.

        Args:
            command: Envelope whose arguments carry request_id, the
                id admitted by an earlier submit.

        Returns:
            Completion mapping with run_id, state, verdict, and
            operation for the admitted command.

        Raises:
            ProjectError: invalid_command when the arguments lack a
                request_id, unknown_request for an id never
                admitted, unsupported_operation when the admitted
                operation has no registered solver.
        """
        arguments = dict(command.get("arguments") or {})
        run_id = arguments.get("run_id")
        if run_id is not None:
            try:
                pending = self._run_jobs[run_id]
            except KeyError:
                raise ProjectError(
                    "unknown_request", f"No queued request: {run_id}."
                ) from None
            stored_operation = pending["operation"]
            run_arguments = dict(pending["arguments"])
            snapshot_id = pending["snapshot_id"]
            request_id = pending["request_id"]
        else:
            request_id = arguments.get("request_id")
            if request_id is None:
                raise ProjectError(
                    "invalid_command", "run_job needs a run_id or request_id argument."
                )
            stored, ack = self._project.command_for(request_id)
            stored_operation = stored.get("operation")
            run_arguments = dict(stored.get("arguments") or {})
            snapshot_id = ack.get("snapshot_id", "")
            request_id = str(request_id)
            run_id = ack.get("run_id")
        if not self._solvers.get(stored_operation):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {stored_operation}."
            )
        # Submit-time admission data stays out of the solver job.
        # Targets were already filled at submit time; never re-fill
        # here (filled min/max would read as caller targets).
        run_arguments.pop("expected_revision", None)
        return self._run_operation(
            stored_operation,
            run_arguments,
            snapshot_id,
            request_id,
            run_id=run_id,
            contain=True,
        )

    def _run_operation(self, name, arguments, snapshot_id, request_id, run_id=None,
                       contain=False, block_scope=None):
        """Select the solver, run it, judge the verdict, log completion."""
        solvers = self._solvers.get(name) or {}
        if not solvers:
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        arguments = dict(arguments)
        try:
            adapter = self._select_solver(name, arguments)
        except ProjectError as exc:
            if not contain:
                raise
            self._latest[name] = run_id
            self._logs[run_id] = f"{exc.code}: {exc}"
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            stored_scope = self._run_jobs.get(run_id, {}).get("block_scope")
            if stored_scope is not None:
                verdict = stamp_verdict(verdict, stored_scope["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        if run_id is None:
            issued = self._execution.dispatch(
                name, {"cell": arguments.get("cell")}, snapshot_id
            )
            run_id = issued["run_id"]
        else:
            # Reuses the submit-time record: unknown ids fail as unknown_run.
            self._execution.status(run_id)
        self._execution.mark_running(run_id)
        self._latest[name] = run_id
        scope_record = block_scope
        if scope_record is None:
            scope_record = self._run_jobs.get(run_id, {}).get("block_scope")
        elif "provenance" not in scope_record:
            # Direct runs admit the closure without a run_id; bind it now.
            scope_record = build_scope_record(
                run_id=run_id,
                revision=self._project.snapshot()["current_revision"],
                block_id=scope_record["block_id"],
                deck=arguments.get("deck"),
                closure=scope_record["closure"],
            )
        if scope_record is not None:
            arguments = narrow_job_for_block(arguments, scope_record["closure"])
        try:
            adapter.preflight({"operation": name, **arguments})
            native = adapter.execute({"operation": name, **arguments})
            result = adapter.parse(native)
        except AdapterError as exc:
            self._logs[run_id] = f"{exc.code}: {exc}"
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            if scope_record is not None:
                verdict = stamp_verdict(verdict, scope_record["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        except Exception as exc:
            # A solver bug in a queued job is NOT_RUN with a reason,
            # never a crash and never a verdict. Direct runs re-raise.
            if not contain:
                raise
            self._logs[run_id] = f"internal_error: {exc!r}"
            verdict = self._execution.record_not_run(run_id, f"internal_error: {exc}")
            if scope_record is not None:
                verdict = stamp_verdict(verdict, scope_record["provenance"])
                self._execution.mark_completed(run_id, verdict)
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        self._logs[run_id] = native.get("log") or "\n".join(
            part for part in (native.get("stdout"), native.get("stderr")) if part
        )
        # Solver convention (see ToolAdapter.parse): violations carry
        # rule/severity/message plus flat location keys, nested here.
        findings = []
        for violation in result.get("violations", []):
            location = {}
            for source, dest in _LOCATION_KEYS:
                if violation.get(source) is not None:
                    location[dest] = violation[source]
            findings.append(
                {
                    "severity": violation.get("severity", "error"),
                    "rule": violation["rule"],
                    "message": violation.get("message", violation["rule"]),
                    "location": location,
                }
            )
        buf = io.StringIO()
        self._yaml.dump({"findings": findings}, buf)
        verdict = self._execution.evaluate(
            run_id, native.get("exit_code", 0), buf.getvalue()
        )
        # Keep measured values on PASS too: a verdict without numbers can't be reviewed.
        if result.get("measurements") is not None:
            verdict = dict(verdict, measurements=result["measurements"])
            self._execution.mark_completed(run_id, verdict)
        if scope_record is not None:
            verdict = stamp_verdict(verdict, scope_record["provenance"])
            self._execution.mark_completed(run_id, verdict)
        if (verdict or {}).get("status") == "NOT_RUN":
            outcome = "run_failed"
        else:
            outcome = "run_completed"
        self._project.append_run_event(outcome, run_id, name, verdict, request_id)
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": verdict,
            "operation": name,
        }

    def run(self, command):
        """Execute an operation synchronously through its solver.

        `deck.tool` selects the registered solver, defaulting to
        the first registered; solver violations nest into findings
        and the verdict is evaluated from the native exit code.
        CRUD/rewind mutations delegate to submit's immediate path
        so the CLI `run` spelling shares the one implementation.

        Args:
            command: Envelope with project_id, operation, and
                arguments (deck.tool selects the solver).

        Returns:
            Completion mapping with run_id, state, verdict, and
            operation. Measured values ride on the verdict (PASS
            included), never only on failure. Adapter failures become not_run verdicts,
            never exceptions. Every judged run appends
            run_completed (PASS/FAIL) or run_failed (NOT_RUN) to
            the ledger with the engine's actor and the verdict.
            CRUD/rewind operations return the immediate mutation
            mapping instead (new revision + events + approval-UI
            fields).

        Raises:
            ProjectError: cross_project_denied for a foreign
                envelope, unsupported_operation for an unregistered
                operation or unknown deck tool, unknown_block for
                a block target naming no block, invalid_target for
                a malformed target, unsupported_scope for a block
                target on a verb serving no block runs yet,
                unknown_run_param for an unknown run.request field,
                invalid_run_param for a mistyped run.request knob,
                invalid_run_request for a non-mapping run.request,
                invalid_command when run_job lacks a
                run_id/request_id argument, for caller-supplied
                run_spice targets, when a CRUD
                mutation is malformed, or a rewind lacks a target
                or targets the live head, revision_conflict for a
                stale CRUD/rewind expected_revision,
                unknown_document for a missing CRUD document,
                unknown_revision for a rewind target with no
                snapshot.

        Caution: Runs the solver now and records the verdict —
            exit zero is not PASS; read the verdict, never the
            exit path.
        """
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )
        name = command.get("operation")
        if name == "run_job":
            return self._run_queued(command)
        if name in _CRUD_OPERATIONS:
            return self.submit(command)
        arguments = self._apply_targets(name, dict(command.get("arguments") or {}))
        arguments = self._apply_run_request(arguments)
        block_scope = self._admit_block_scope(name, arguments)
        return self._run_operation(
            name,
            arguments,
            command.get("snapshot_id", ""),
            None,
            block_scope=block_scope,
        )
