"""Composition root (B9): the Engine wires core modules for adapters.

Adapters construct against this, never against services directly. The
root owns no domain logic: it routes cataloged names (see
`interfaces.vocabulary`) to live module state. Operations queue through
the project service with revision gating and envelope-id idempotency;
`drain()` then executes queued jobs under the run_id their ack carried,
so a caller can poll `get_job_status` for the result. Wired queries read
live state; the rest honestly report unwired. `run()` executes
registered solvers synchronously. Each operation maps to named solvers;
`deck.tool` selects one, defaulting to the first registered (run_drc:
magic, then klayout; run_optical: sax; run_extraction: magic; run_lvs:
netgen; run_spice: ngspice). Unregistered operations and unknown deck
tools raise instead of faking a verdict.

With `constraints` (metric -> {min, max, unit}), run_spice targets come
from the project, never the caller: caller-supplied min/max is refused.
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
from .execution.service import ExecutionService
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.catalog import Catalog
from .project.errors import ProjectError
from .project.service import ProjectService

_WIRED_QUERIES = frozenset(
    {"get_project_snapshot", "get_job_status", "get_check_results", "get_logs", "list_job_kinds"}
)
_LOG_PAGE_MAX = 200

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
    def __init__(self, project_id, actor, catalog_root=".", constraints=None):
        self._project_id = project_id
        self._project = ProjectService(project_id, actor)
        self._execution = ExecutionService(project_id)
        self._catalog = Catalog(catalog_root)
        self._solvers = {
            "run_drc": {"magic": MagicDrcAdapter(), "klayout": KlayoutDrcAdapter()},
            "run_hdl_test": {"icarus": HdlSimAdapter()},
            "run_optical": {"sax": SaxAdapter()},
            "run_extraction": {"magic": MagicExtractAdapter()},
            "run_lvs": {"netgen": NetgenLvsAdapter()},
            "run_spice": {"ngspice": NgspiceAdapter()},
        }
        self._yaml = YAML(typ="safe")
        self._constraints = dict(constraints) if constraints is not None else None
        self._pending = []
        self._logs = {}
        self._latest = {}

    def snapshot(self):
        return self._project.snapshot()

    def events_since(self, cursor):
        return self._project.events_since(cursor)

    def _check_scope(self, command):
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )

    def submit(self, command):
        self._check_scope(command)
        name = command.get("operation")
        arguments = dict(command.get("arguments") or {})
        if name in _WIRED_QUERIES:
            return self._query(name, arguments)
        if name in QUERIES or name not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation", f"Operation not wired yet: {name}."
            )
        arguments = self._apply_targets(name, arguments)
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        ack = self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )
        # An idempotent replay returns the same ack; queue its job only once.
        if not self._execution.known(ack["run_id"]):
            self._execution.dispatch(
                name, {"cell": arguments.get("cell")}, ack["snapshot_id"], run_id=ack["run_id"]
            )
            self._pending.append((ack["run_id"], name, arguments))
        return ack

    def drain(self):
        """Execute every queued job, in submission order."""
        done = []
        while self._pending:
            run_id, name, arguments = self._pending.pop(0)
            done.append(self._execute(run_id, name, arguments))
        return done

    def register_solver(self, operation, adapter, tool=None):
        name = tool if tool is not None else type(adapter).__name__
        self._solvers.setdefault(operation, {})[name] = adapter
        return {"operation": operation, "tool": name}

    def findings(self, run_id, limit=50, cursor=None):
        return self._execution.findings(run_id, limit=limit, cursor=cursor)

    def run(self, command):
        self._check_scope(command)
        name = command.get("operation")
        if not self._solvers.get(name):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        arguments = dict(command.get("arguments") or {})
        adapter = self._select_solver(name, arguments)
        issued = self._execution.dispatch(
            name, {"cell": arguments.get("cell")}, command.get("snapshot_id", "")
        )
        return self._execute(issued["run_id"], name, arguments, adapter=adapter, contain=False)

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

    def _execute(self, run_id, name, arguments, adapter=None, contain=True):
        """Run one job. contain=True (queued jobs) turns any failure into NOT_RUN with a
        reason; run() keeps contain=False so its callers still see raised errors."""

        def outcome(verdict):
            return {"run_id": run_id, "state": "completed", "verdict": verdict, "operation": name}

        if adapter is None:
            try:
                adapter = self._select_solver(name, arguments)
            except ProjectError as exc:
                self._latest[name] = run_id
                return outcome(self._execution.record_not_run(run_id, f"{exc.code}: {exc}"))
        self._execution.mark_running(run_id)
        self._latest[name] = run_id
        try:
            adapter.preflight({"operation": name, **arguments})
            native = adapter.execute({"operation": name, **arguments})
            result = adapter.parse(native)
        except AdapterError as exc:
            self._logs[run_id] = f"{exc.code}: {exc}"
            return outcome(self._execution.record_not_run(run_id, f"{exc.code}: {exc}"))
        except Exception as exc:  # A solver bug is NOT_RUN with a reason, never a crash or a verdict.
            if not contain:
                raise
            self._logs[run_id] = f"internal_error: {exc!r}"
            return outcome(self._execution.record_not_run(run_id, f"internal_error: {exc}"))
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
        return outcome(verdict)

    def _apply_targets(self, name, arguments):
        if name != "run_spice" or self._constraints is None:
            return arguments
        measurements = arguments.get("measurements")
        if not isinstance(measurements, list):
            return arguments  # the adapter's preflight reports the shape error
        filled = []
        for item in measurements:
            if not isinstance(item, dict):
                filled.append(item)
                continue
            metric = item.get("name")
            if "min" in item or "max" in item:
                raise ProjectError(
                    "invalid_command",
                    f"Targets come from the project's constraints, not the call: "
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
            filled.append({**item, **bounds, "unit": unit})
        return {**arguments, "measurements": filled}

    def _query(self, name, arguments):
        if name == "get_project_snapshot":
            return self._project.snapshot()
        if name == "get_job_status":
            return self._execution.status(arguments.get("run_id"))
        if name == "get_check_results":
            wanted = arguments.get("operation")
            checks = {}
            for operation, run_id in self._latest.items():
                if wanted and operation != wanted:
                    continue
                status = self._execution.status(run_id)
                verdict = status.get("verdict") or {}
                checks[operation] = {
                    "run_id": run_id,
                    "state": status["state"],
                    "status": verdict.get("status"),
                    "verdict": verdict,
                }
            return {"checks": checks, "current_revision": self._project.snapshot()["current_revision"]}
        if name == "get_logs":
            return self._logs_page(arguments)
        if name == "list_job_kinds":
            return {
                "job_kinds": [
                    {"operation": operation, "tools": list(solvers)}
                    for operation, solvers in sorted(self._solvers.items())
                ]
            }
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def _logs_page(self, arguments):
        run_id = arguments.get("run_id")
        self._execution.status(run_id)  # unknown runs raise unknown_run
        lines = self._logs.get(run_id, "").splitlines()
        numbered = [(index + 1, line) for index, line in enumerate(lines)]
        query = arguments.get("query")
        if query:
            numbered = [(n, line) for n, line in numbered if query.lower() in line.lower()]
        offset = max(0, int(arguments.get("offset", 0)))
        limit = max(1, min(int(arguments.get("limit", 40)), _LOG_PAGE_MAX))
        page = numbered[offset : offset + limit]
        return {
            "run_id": run_id,
            "total_lines": len(lines),
            "matched": len(numbered),
            "offset": offset,
            "lines": [f"{n}: {line}" for n, line in page],
            "more": offset + limit < len(numbered),
        }
