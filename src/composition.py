"""Composition root (B9): the Engine wires core modules for adapters.

Adapters construct against this, never against services directly. The
root owns no domain logic: it routes cataloged names (see
`interfaces.vocabulary`) to live module state. Operations queue through
the project service with revision gating and envelope-id idempotency;
every accepted mutation advances the revision and appends an
actor-attributed event to the durable ledger (LEDGER-DURABLE/I30),
and every run appends its completion with a verdict link. Only
wired queries read state, the rest honestly report unwired.
Two-phase execution: `submit(op)` admits and returns an ack, then
`run_job(request_id)` executes the admitted command — over `run()`
directly or over submit-only transports via `submit(run_job)`.
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
from .execution.service import ExecutionService
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.catalog import Catalog
from .project.errors import ProjectError
from .project.service import ProjectService

_WIRED_QUERIES = frozenset({"get_project_snapshot", "get_events_since"})

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
    """

    def __init__(self, project_id, actor, catalog_root=".", engine_root=None):
        self._project_id = project_id
        self._project = ProjectService(project_id, actor, engine_root=engine_root)
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

    def submit(self, command):
        """Admit an operation (phase 1) or serve a wired query.

        Operations queue through the project service with revision
        gating and envelope-id idempotency; only wired queries read
        state, the rest honestly report unwired.

        Args:
            command: Envelope with project_id, operation, arguments,
                and request_id.

        Returns:
            Admission ack for operations, the snapshot for the
            wired get_project_snapshot query, or the event page
            for the wired get_events_since query.

        Raises:
            ProjectError: cross_project_denied for a foreign
                envelope, unsupported_operation for an unwired or
                unknown name, revision_conflict for a stale
                expected_revision, invalid_command for a malformed
                get_events_since cursor, resync_required when a
                get_events_since contiguity demand cannot be met.

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
        if name == "get_events_since":
            return self._query_events_since(arguments)
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
        if not self._solvers.get(name):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        return self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )

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
        """Execute an admitted request by id (phase 2 of submit-then-run)."""
        arguments = dict(command.get("arguments") or {})
        request_id = arguments.get("request_id")
        if request_id is None:
            raise ProjectError(
                "invalid_command", "run_job needs a request_id argument."
            )
        stored, ack = self._project.command_for(request_id)
        run_arguments = dict(stored.get("arguments") or {})
        # Submit-time admission data stays out of the solver job.
        run_arguments.pop("expected_revision", None)
        return self._run_operation(
            stored.get("operation"),
            run_arguments,
            ack.get("snapshot_id", ""),
            request_id,
        )

    def _run_operation(self, name, arguments, snapshot_id, request_id):
        """Select the solver, run it, judge the verdict, log completion."""
        solvers = self._solvers.get(name) or {}
        if not solvers:
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        arguments = dict(arguments)
        hint = (arguments.get("deck") or {}).get("tool")
        if hint is None:
            adapter = next(iter(solvers.values()))
        else:
            try:
                adapter = solvers[hint]
            except KeyError:
                raise ProjectError(
                    "unsupported_operation",
                    f"No {name} solver for deck tool: {hint}.",
                ) from None
        issued = self._execution.dispatch(
            name, {"cell": arguments.get("cell")}, snapshot_id
        )
        run_id = issued["run_id"]
        self._execution.mark_running(run_id)
        try:
            adapter.preflight({"operation": name, **arguments})
            native = adapter.execute({"operation": name, **arguments})
            result = adapter.parse(native)
        except AdapterError as exc:
            verdict = self._execution.record_not_run(run_id, f"{exc.code}: {exc}")
            self._project.append_run_event(
                "run_failed", run_id, name, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": name,
            }
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

        Args:
            command: Envelope with project_id, operation, and
                arguments (deck.tool selects the solver).

        Returns:
            Completion mapping with run_id, state, verdict, and
            operation. Adapter failures become not_run verdicts,
            never exceptions. Every judged run appends
            run_completed (PASS/FAIL) or run_failed (NOT_RUN) to
            the ledger with the engine's actor and the verdict.

        Raises:
            ProjectError: cross_project_denied for a foreign
                envelope, unsupported_operation for an unregistered
                operation or unknown deck tool, invalid_command
                when run_job lacks a request_id argument.

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
        return self._run_operation(
            name,
            dict(command.get("arguments") or {}),
            command.get("snapshot_id", ""),
            None,
        )
