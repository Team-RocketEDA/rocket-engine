"""Composition root (B9): the Engine wires core modules for adapters.

Adapters construct against this, never against services directly. The
root owns no domain logic: it routes cataloged names (see
`interfaces.vocabulary`) to live module state. Operations queue through
the project service with revision gating and envelope-id idempotency;
only wired queries read state, the rest honestly report unwired.
`run()` executes registered solvers synchronously (run_drc live via
Magic); unregistered operations raise instead of faking a verdict.
"""

import io
import uuid

from ruamel.yaml import YAML

from .adapters.drc import MagicDrcAdapter
from .adapters.errors import AdapterError
from .execution.service import ExecutionService
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.catalog import Catalog
from .project.errors import ProjectError
from .project.service import ProjectService

_WIRED_QUERIES = frozenset({"get_project_snapshot"})


class Engine:
    def __init__(self, project_id, actor, catalog_root="."):
        self._project_id = project_id
        self._project = ProjectService(project_id, actor)
        self._execution = ExecutionService(project_id)
        self._catalog = Catalog(catalog_root)
        self._solvers = {"run_drc": MagicDrcAdapter()}
        self._yaml = YAML(typ="safe")

    def snapshot(self):
        return self._project.snapshot()

    def submit(self, command):
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )
        name = command.get("operation")
        arguments = dict(command.get("arguments") or {})
        if name in _WIRED_QUERIES:
            return self._project.snapshot()
        if name in QUERIES or name not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation", f"Operation not wired yet: {name}."
            )
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        return self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )

    def register_solver(self, operation, adapter):
        self._solvers[operation] = adapter
        return {"operation": operation, "solver": type(adapter).__name__}

    def findings(self, run_id, limit=50, cursor=None):
        return self._execution.findings(run_id, limit=limit, cursor=cursor)

    def run(self, command):
        envelope = command.get("project_id")
        if envelope != self._project_id:
            raise ProjectError(
                "cross_project_denied",
                f"Bound to {self._project_id}, got {envelope}.",
            )
        name = command.get("operation")
        try:
            adapter = self._solvers[name]
        except KeyError:
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            ) from None
        arguments = dict(command.get("arguments") or {})
        issued = self._execution.dispatch(
            name, {"cell": arguments.get("cell")}, command.get("snapshot_id", "")
        )
        run_id = issued["run_id"]
        self._execution.mark_running(run_id)
        try:
            adapter.preflight({"operation": name, **arguments})
            native = adapter.execute({"operation": name, **arguments})
            result = adapter.parse(native)
        except AdapterError as exc:
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
        # Solver convention: violations carry rule text plus a bbox.
        # Per-solver finding translators arrive with the second solver.
        findings = [
            {
                "severity": "error",
                "rule": violation["rule"],
                "message": violation["rule"],
                "location": {
                    "bbox_lambda": violation["bbox"],
                    "area": violation.get("area"),
                },
            }
            for violation in result.get("violations", [])
        ]
        buf = io.StringIO()
        self._yaml.dump({"findings": findings}, buf)
        verdict = self._execution.evaluate(
            run_id, native.get("exit_code", 0), buf.getvalue()
        )
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": verdict,
            "operation": name,
        }
