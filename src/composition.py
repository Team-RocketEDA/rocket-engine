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
Submit-immediate execution (API-GENERALIZE): `submit(op)` admits and
runs inline, returning the ack shape plus the verdict payload under
the one run id; `run_job` stays for explicit/deferred/batch pumping
plus idempotent result fetch — over `run()` directly or over
submit-only transports via `submit(run_job)`. Replays return the
stored completion without re-executing, and a fresh Engine reports
crash survivors once (boot report, never executed) on its first
mutating call; every replay surface stays gated behind an explicit
resume decision (REPLAY-SAFE).
With `constraints` (metric -> {min, max, unit[, expr, control]}),
run_spice targets come from the project, never the caller:
caller-supplied min/max — or a caller expr where the project defines
one — is refused.
`run()` executes registered solvers synchronously. Each operation
maps to named solvers; `deck.tool` selects one, defaulting to the
first registered (run_drc: magic, then klayout; run_optical: sax;
run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
run_syntax: slang; run_hdl_test: icarus; run_synth: yosys;
run_connectivity: connectgraph; run_erc: connectgraph).
Unregistered operations and unknown deck tools raise instead of
faking a verdict.
"""

import io
import uuid

from ruamel.yaml import YAML

from .adapters.connectivity import ConnectivityAdapter
from .adapters.drc import MagicDrcAdapter
from .adapters.drc_kl import KlayoutDrcAdapter
from .adapters.errors import AdapterError
from .adapters.extract_magic import MagicExtractAdapter
from .adapters.hdl_sim import HdlSimAdapter
from .adapters.lvs_netgen import NetgenLvsAdapter
from .adapters.ngspice import NgspiceAdapter
from .adapters.sax import SaxAdapter
from .adapters.syntax import SyntaxAdapter
from .adapters.synth_yosys import YosysSynthAdapter
from .execution.apig_pool import (
    ApigPool,
    request_for_run,
    stored_completion_from_events,
)
from .execution.apig_submit import merge_ack_completion
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
from .execution.coalesce import Coalescer, content_key
from .execution.dispatch import OpDispatcher
from .execution.errors import ExecutionError
from .execution.python_exec import PythonExecService
from .execution.replay_safe import ReplaySafe, content_key_for
from .execution.service import ExecutionService
from .interfaces import apig_assets
from .interfaces.celllink import resolve_run as resolve_celllink_run
from .interfaces.errors import ContractError
from .interfaces.layer_serving_stackup import (
    PresetStore,
    get_stackup,
    viewer_rows,
    viewer_rows_for_preset,
)
from .interfaces.runparams import RunParamsError, validate_run_request
from .interfaces.setup import report_capabilities
from .interfaces.vocabulary import OPERATIONS, QUERIES
from .library.apig_catalog import (
    ApigCatalog,
    gdsfactory_provider,
    static_provider,
)
from .library.catalog import Catalog
from .library.errors import LibraryError
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
    "get_component": "get_component",
    "components_of": "components_of",
    "entities_with": "entities_with",
    "get_world_snapshot": "world_snapshot",
    "read_settings": "read_settings",
    "get_resolved_config": "resolved_config",
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
    "get_python_console": "python_console",
    "list_cells": "catalog_cells",
    "serve_asset": "serve_asset",
    "list_assets": "list_assets",
    "get_layer_stackup": "layer_stackup",
    "get_layer_rows": "layer_rows",
    "list_layer_presets": "layer_presets",
    "save_layer_preset": "layer_preset_save",
    "delete_layer_preset": "layer_preset_delete",
    "apply_layer_preset": "layer_preset_apply",
    "list_survivors": "boot_report",
}

# Job-result queries served from execution state (plus the captured run log).
_JOB_QUERIES = frozenset(
    {"get_job_status", "get_check_results", "get_logs", "list_job_kinds"}
)

# Catalogue + raw-asset queries served from engine state (the cell
# index and the PDK store); read-only, never replay the backlog.
_APIG_QUERIES = frozenset({"list_cells", "serve_asset", "list_assets"})

# Replay-safety query (REPLAY-SAFE): the boot survivor report, served
# from ledger state. Report-only — never executes, only records
# idempotent interruption marks for newly found outages.
_REPLAY_QUERIES = frozenset({"list_survivors"})

# Layer-serving queries (LAYER-SERVING): stackup/rows/presets served
# from the PDK store plus Engine-memory user presets (PresetStore).
_LAYER_QUERIES = frozenset(
    {
        "get_layer_stackup",
        "get_layer_rows",
        "list_layer_presets",
        "save_layer_preset",
        "delete_layer_preset",
        "apply_layer_preset",
    }
)

# A get_logs page never dumps more than this many lines at once.
_LOG_PAGE_MAX = 200

# CRUD mutations + rewind execute immediately inside submit()
# (run_job precedent): revision gate + idempotency + event logging,
# no queue, no solver. Engine.run delegates them back to submit so
# the CLI `run` path shares the one implementation. Wire ops
# (WIRE-PLACE) ride the same immediate path once the ENGINE-ECS
# store lands; without it they report unsupported.
_CRUD_OPERATIONS = frozenset(
    {
        "create_project",
        "write_doc",
        "delete_doc",
        "apply_mutations",
        "rewind",
        "create_entity",
        "set_component",
        "attach_component",
        "detach_component",
        "delete_entity",
        "write_settings",
        "place_wire",
        "place_junction",
        "connect_endpoint",
        "move_wire",
        "split_wire",
        "delete_wire",
        "delete_junction",
        "materialize_nets",
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
        pool_max_depth: Maximum undrained execution backlog;
            admissions past it are refused, never queued.
        project_dir: Project folder python_execute path mode
            resolves inside; path mode refuses loudly without one.
    """

    def __init__(self, project_id, actor, catalog_root=".",
                 engine_root=None, linked_root=None, constraints=None,
                 blocks=None, pool_max_depth=64, project_dir=None):
        self._project_id = project_id
        self._actor = actor
        self._blocks = blocks if blocks is not None else {}
        self._project = ProjectService(
            project_id, actor, engine_root=engine_root,
            linked_root=linked_root,
        )
        self._execution = ExecutionService(project_id)
        self._coalescer = Coalescer()
        self._layer_presets = PresetStore()
        self._catalog = Catalog(catalog_root)
        self._solvers = {
            "run_drc": {"magic": MagicDrcAdapter(), "klayout": KlayoutDrcAdapter()},
            "run_hdl_test": {"icarus": HdlSimAdapter()},
            "run_optical": {"sax": SaxAdapter()},
            "run_extraction": {"magic": MagicExtractAdapter()},
            "run_lvs": {"netgen": NetgenLvsAdapter()},
            "run_spice": {"ngspice": NgspiceAdapter()},
            "run_syntax": {"slang": SyntaxAdapter()},
            "run_synth": {"yosys": YosysSynthAdapter()},
            "run_connectivity": {"connectgraph": ConnectivityAdapter()},
            "run_erc": {"connectgraph": ConnectivityAdapter()},
        }
        self._yaml = YAML(typ="safe")
        self._constraints = dict(constraints) if constraints is not None else None
        self._logs = {}
        self._latest = {}
        self._run_jobs = {}
        self._pool = ApigPool(
            self._project, self._pool_execute, max_depth=pool_max_depth
        )
        self._replay = ReplaySafe(self._project, self._replay_execute)
        self._cells = ApigCatalog(
            catalog_root, providers=[gdsfactory_provider()]
        )
        self._replayed = False
        self._pyexec = PythonExecService(
            project_id, actor,
            execution=self._execution,
            project_root=project_dir,
            dispatcher=OpDispatcher(
                self, project_id=project_id, actor=actor),
        )

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
            served=_CRUD_OPERATIONS | {"run_job", "place_cell", "python_execute"},
        )

    def submit(self, command):
        """Admit and run an operation inline, or serve a wired query.

        Solver operations admit through the project service with
        revision gating and envelope-id idempotency, then execute
        immediately: the returned mapping is the admission ack
        shape plus the completion (state, verdict, operation) under
        the one run id. CRUD mutations, rewind, and place_cell
        execute immediately through the same admission machinery
        (no queue, no solver); only wired queries read state, the
        rest honestly report unwired.

        Args:
            command: Envelope with project_id, operation, arguments,
                and request_id.

        Returns:
            Merged ack-plus-completion for solver operations (ack
            identity fields plus state, verdict, operation), the
            immediate mutation mapping (new revision + events +
            approval-UI fields) for CRUD/rewind/place_cell
            operations, the snapshot for the wired
            get_project_snapshot query, the capability mapping
            for get_capabilities, the event page for
            get_events_since, the project/document listing for
            the CRUD queries, the status/checks/logs/kinds for
            the job-result queries, the cell listing or asset
            bytes for the catalogue/asset queries, the
            stackup/rows/presets for the layer-serving queries,
            the stored-or-fresh completion for run_job, the
            boot survivor report for list_survivors, the resume
            completion for resume_run, the discard record for
            discard_run, the gated batch for resume_all_retryable,
            the approval handle for python_execute, or the console
            view for get_python_console.

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
                get_events_since cursor, a malformed mutation, a
                place_cell without a cell, a serve_asset without
                pdk id/revision/path, a rewind that lacks a target
                or targets the live head, a write_settings missing
                kind or settings, an unknown settings kind, or
                settings that break the kind schema, future_format
                for a settings write over a newer on-disk file,
                or a layer query missing its pdk_id/name, a
                resume_run or discard_run without a run_id, a
                component verb missing entity, component, or
                data, or a world snapshot with a non-bool
                flag, unknown_entity or unknown_component for
                a missing entity or component, component_exists
                for a duplicate attach, backfill_readonly for a
                write over a read-only backfilled id,
                resync_required when a get_events_since contiguity
                demand cannot be met, invalid_project
                for a bad project id,
                project_exists for a duplicate create,
                unknown_document for a missing document,
                unknown_revision for a rewind target with no
                snapshot, invalid_path or path_escape for a bad
                document path, request_conflict for a reused
                envelope id with new text, unknown_cell,
                ambiguous_cell, unknown_param, incompatible_port,
                or instance_exists for a bad placement,
                invalid_reference for a bad asset address,
                unknown_request for an id never admitted.
            ExecutionError: pool_full when the execution backlog
                is saturated — drain (run_job) before submitting
                more; nothing was admitted. coalesced_run_lost
                when a joined run finished with no completion
                stored (its owner died mid-drain). Resume refusals
                carry unknown_survivor, already_completed,
                already_decided, or poison_quarantined with a
                user-facing message (full context is logged
                dev-side).

        Caution: Bound to one project: cross-project envelopes are
            denied, never routed — and a stale expected_revision
            fails instead of merging. The first mutating call per
            Engine also builds the crash-survivor boot report
            (report-only — nothing executes without an explicit
            resume decision); queries never do.
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
        if name == "get_python_console":
            return self.python_console()
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
        if name == "read_settings":
            if "kind" not in arguments:
                raise ProjectError(
                    "invalid_command", "read_settings needs a kind argument."
                )
            return self._project.read_settings(arguments["kind"])
        if name == "get_resolved_config":
            return self._project.resolved_config(
                session_id=arguments.get("session_id"),
                run_id=arguments.get("run_id"),
            )
        if name == "get_component":
            if "entity" not in arguments or "component" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "get_component needs entity and component arguments.",
                )
            return self._project.get_component(
                arguments["entity"], arguments["component"]
            )
        if name == "components_of":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "components_of needs an entity argument.",
                )
            return self._project.components_of(arguments["entity"])
        if name == "entities_with":
            if "component" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "entities_with needs a component argument.",
                )
            return self._project.entities_with(
                arguments["component"],
                predicate=arguments.get("predicate"),
            )
        if name == "get_world_snapshot":
            return self._project.world_snapshot(
                include_backfill=arguments.get("include_backfill", True)
            )
        if name in _JOB_QUERIES:
            return self._query_job(name, arguments)
        if name in _APIG_QUERIES:
            return self._query_apig(name, arguments)
        if name in _LAYER_QUERIES:
            return self._query_layer(name, arguments)
        if name in _REPLAY_QUERIES:
            return self.boot_report()
        if name in _WIRED_QUERIES:
            return self._project.snapshot()
        if name in QUERIES or name not in OPERATIONS:
            raise ProjectError(
                "unsupported_operation", f"Operation not wired yet: {name}."
            )
        self._replay_once()
        if name == "run_job":
            # Deferred/batch pumping plus idempotent fetch: admission
            # (and its revision gate) already happened at submit time.
            return self.run(command)
        if name == "resume_run":
            if "run_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "resume_run needs a run_id argument.",
                )
            return self.resume_survivor(
                arguments["run_id"],
                force=bool(arguments.get("force", False)),
            )
        if name == "discard_run":
            if "run_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "discard_run needs a run_id argument.",
                )
            return self.discard_survivor(arguments["run_id"])
        if name == "resume_all_retryable":
            return self.resume_all_retryable()
        if name in _CRUD_OPERATIONS:
            return self._submit_crud(name, arguments, command)
        if name == "place_cell":
            return self._submit_place_cell(arguments, command)
        if name == "python_execute":
            return self._submit_pyexec(arguments, command)
        if not self._solvers.get(name):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {name}."
            )
        scope_request = self._admit_block_scope(name, arguments)
        buf = io.StringIO()
        self._yaml.dump({"operation": name, "arguments": arguments}, buf)
        command_text = buf.getvalue()
        request_id = command.get("request_id") or uuid.uuid4().hex
        # COALESCE-I33: identical concurrent content on an unchanged
        # revision executes once. The guard holds the whole admission
        # section — lookup, ledger admit, register — so two identical
        # submits cannot both miss; drains and completion waits run
        # outside it. Force bypasses the lane both ways: a forced run
        # neither joins a live run nor registers as one.
        force = command.get("force") is True
        key = content_key(name, arguments)
        with self._coalescer.guard:
            head = self._project.snapshot()["current_revision"]
            hit = None if force else self._coalescer.lookup(key, head)
            if hit is not None:
                ack = self._project.log_coalesced_request(
                    command_text, str(request_id), hit["run_id"],
                    hit["snapshot_id"],
                )
                waiter = self._coalescer.attach(hit["run_id"], str(request_id))
            else:
                ack = self._pool.submit_request(
                    command_text,
                    str(request_id),
                    expected_revision=arguments.get("expected_revision"),
                )
                # SUBMIT-IMMEDIATE: the ack run_id is the execution id. A
                # replay of a completed run returns the stored completion
                # without re-executing; otherwise register the record (a
                # replay returns the same ack, so register it only once)
                # and drain this run inline.
                stored = self._stored_completion(ack["run_id"])
                if stored is not None:
                    return merge_ack_completion(ack, stored)
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
                waiter = None
                if not force:
                    self._coalescer.register(
                        key, ack["current_revision"], str(request_id),
                        ack["run_id"], ack["snapshot_id"],
                    )
        if hit is not None:
            return self._await_shared(ack, hit["run_id"], waiter)
        try:
            completion = self._pool.drain_ids([ack["run_id"]])[0]
        except BaseException:
            if not force:
                self._coalescer.discard(ack["run_id"])
            raise
        if not force:
            self._coalescer.complete(ack["run_id"], completion)
        return merge_ack_completion(ack, completion)

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
        if name == "write_settings":
            if "kind" not in arguments or "settings" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "write_settings needs kind and settings arguments.",
                )
            return self._project.write_settings(
                arguments["kind"],
                arguments["settings"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "create_entity":
            return self._project.create_entity(
                request_id,
                command_text,
                kind=arguments.get("kind", ""),
                components=arguments.get("components"),
                expected_revision=arguments.get("expected_revision"),
            )
        if name in ("set_component", "attach_component"):
            if (
                "entity" not in arguments
                or "component" not in arguments
                or "data" not in arguments
            ):
                raise ProjectError(
                    "invalid_command",
                    f"{name} needs entity, component, and data arguments.",
                )
            method = getattr(self._project, name)
            return method(
                arguments["entity"],
                arguments["component"],
                arguments["data"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "detach_component":
            if "entity" not in arguments or "component" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "detach_component needs entity and component arguments.",
                )
            return self._project.detach_component(
                arguments["entity"],
                arguments["component"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_entity":
            if "entity" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_entity needs an entity argument.",
                )
            return self._project.delete_entity(
                arguments["entity"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "place_wire":
            for key in ("segments", "layer", "endpoints"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"place_wire needs a {key} argument.",
                    )
            return self._project.place_wire(
                arguments["segments"],
                arguments["layer"],
                arguments["endpoints"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "place_junction":
            for key in ("xy", "layer"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"place_junction needs a {key} argument.",
                    )
            return self._project.place_junction(
                arguments["xy"],
                arguments["layer"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "connect_endpoint":
            for key in ("wire_id", "end", "ref"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"connect_endpoint needs a {key} argument.",
                    )
            return self._project.connect_endpoint(
                arguments["wire_id"],
                arguments["end"],
                arguments["ref"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "move_wire":
            for key in ("wire_id", "dx", "dy"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"move_wire needs a {key} argument.",
                    )
            return self._project.move_wire(
                arguments["wire_id"],
                arguments["dx"],
                arguments["dy"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "split_wire":
            for key in ("wire_id", "at"):
                if key not in arguments:
                    raise ProjectError(
                        "invalid_command",
                        f"split_wire needs a {key} argument.",
                    )
            return self._project.split_wire(
                arguments["wire_id"],
                arguments["at"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_wire":
            if "wire_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_wire needs a wire_id argument.",
                )
            return self._project.delete_wire(
                arguments["wire_id"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "delete_junction":
            if "junction_id" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "delete_junction needs a junction_id argument.",
                )
            return self._project.delete_junction(
                arguments["junction_id"],
                request_id,
                command_text,
                expected_revision=arguments.get("expected_revision"),
            )
        if name == "materialize_nets":
            if "pins" not in arguments:
                raise ProjectError(
                    "invalid_command",
                    "materialize_nets needs a pins argument.",
                )
            return self._project.materialize_nets(
                arguments["pins"],
                request_id,
                command_text,
                labels=arguments.get("labels"),
                ports=arguments.get("ports"),
                cell=arguments.get("cell", "top"),
                named_refs=arguments.get("named_refs"),
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

    def _submit_place_cell(self, arguments, command):
        """Place a catalogue cell immediately (no queue, no solver)."""
        if "cell" not in arguments:
            raise ProjectError(
                "invalid_command", "place_cell needs a cell argument."
            )
        request_id = str(command.get("request_id") or uuid.uuid4().hex)
        try:
            return self._cells.place_cell(
                self._project,
                arguments["cell"],
                request_id,
                expected_revision=arguments.get("expected_revision"),
                pdk=arguments.get("pdk"),
                instance_id=arguments.get("instance_id"),
                params=arguments.get("params"),
                connections=arguments.get("connections"),
            )
        except LibraryError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def _query_apig(self, name, arguments):
        """Route a catalogue/asset query to its Engine reader."""
        if name == "list_cells":
            return self.catalog_cells(pdk=arguments.get("pdk"))
        if name == "serve_asset":
            return self.serve_asset(
                arguments.get("pdk_id"),
                arguments.get("revision"),
                arguments.get("path"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "list_assets":
            return self.list_assets(
                arguments.get("pdk_id"),
                arguments.get("revision"),
                prefix=arguments.get("prefix"),
                engine_root=arguments.get("engine_root"),
            )
        raise ProjectError("unsupported_operation", f"Operation not wired yet: {name}.")

    def catalog_cells(self, pdk=None):
        """List versioned component cells, optionally for one PDK.

        The engine introspects cell libraries upstream and serves
        plain data (cell, PDK, ports, default params), so the
        frontend never imports gdsfactory.

        Args:
            pdk: Restrict to one PDK label; all entries when
                omitted.

        Returns:
            Listing with catalog_version and cells sorted by
                (pdk, cell).
        """
        return self._cells.list_cells(pdk=pdk)

    def register_cells(self, entries, source="static"):
        """Seed the component catalogue with static entries.

        Args:
            entries: Entry mappings with cell, pdk, pdk_revision,
                ports, and default params.
            source: Source label stamped on every entry.

        Returns:
            Mapping with the cell count now served.
        """
        self._cells.add_provider(static_provider(entries, source=source))
        return {"cells": len(self._cells.list_cells()["cells"])}

    def serve_asset(self, pdk_id=None, revision=None, path=None,
                    engine_root=None):
        """Serve one PDK file's bytes verbatim with hash identity.

        No conversion, no rendering: the sha256 is computed over
        the raw bytes, base64 is transport encoding only.

        Args:
            pdk_id: PDK id (either display spelling resolves).
            revision: PDK revision pin.
            path: Store-relative file path.
            engine_root: Explicit store root; ROCKETEDA_HOME
                resolution when omitted.

        Returns:
            Mapping with asset_version, pdk_id, display_id,
                revision, canonical path, size, sha256, and the
                verbatim bytes base64-encoded.

        Raises:
            ProjectError: invalid_command when pdk id, revision,
                or path is missing; invalid_reference for an
                unknown PDK, a missing file, or an escaping path.

        Caution: No size cap — bulk reads belong to list_assets
            plus selective serve_asset calls, never a blind loop.
        """
        if pdk_id is None or revision is None or path is None:
            raise ProjectError(
                "invalid_command",
                "serve_asset needs pdk_id, revision, and path arguments.",
            )
        try:
            return apig_assets.serve_asset(
                pdk_id, revision, path, engine_root=engine_root
            )
        except ContractError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def list_assets(self, pdk_id=None, revision=None, prefix=None,
                    engine_root=None):
        """List PDK file metadata with per-file hash identity.

        Args:
            pdk_id: PDK id (either display spelling resolves).
            revision: PDK revision pin.
            prefix: Optional store-relative prefix filter.
            engine_root: Explicit store root; ROCKETEDA_HOME
                resolution when omitted.

        Returns:
            Mapping with asset_version, pdk_id, display_id,
                revision, sorted file entries (path, size,
                sha256), symlink entries, and the file count.

        Raises:
            ProjectError: invalid_command when pdk id or revision
                is missing; invalid_reference for an unknown PDK
                or an escaping prefix.
        """
        if pdk_id is None or revision is None:
            raise ProjectError(
                "invalid_command",
                "list_assets needs pdk_id and revision arguments.",
            )
        try:
            return apig_assets.list_assets(
                pdk_id, revision, prefix=prefix, engine_root=engine_root
            )
        except ContractError as exc:
            raise ProjectError(exc.code, str(exc)) from exc

    def _stored_completion(self, run_id):
        """Stored completion for a finished run, without executing.

        In-memory verdicts answer first; across a reboot the
        ledger's run event answers instead. Runs that never
        finished (or never ran) answer None.
        """
        try:
            status = self._execution.status(run_id)
        except ExecutionError:
            status = None
        if (
            status is not None
            and status.get("state") in ("completed", "cancelled")
            and status.get("verdict") is not None
        ):
            pending = self._run_jobs.get(run_id, {})
            return {
                "run_id": run_id,
                "state": status["state"],
                "verdict": status["verdict"],
                "operation": pending.get("operation"),
            }
        return stored_completion_from_events(
            self._project.events_since(0), run_id
        )

    def _await_shared(self, ack, run_id, waiter):
        """Resolve a coalesced envelope to the shared completion.

        The waiter delivers the owner's completion; a run evicted
        just before attach (or discarded when its drain raised)
        falls back to the stored completion — the run event
        precedes eviction, so fetch cannot miss a finished run.
        """
        completion = None
        if waiter is not None:
            completion = self._coalescer.await_completion(waiter)
        if completion is None:
            completion = self._stored_completion(run_id)
        if completion is None:
            raise ExecutionError(
                "coalesced_run_lost",
                f"Shared run finished with no completion: {run_id}.",
            )
        return merge_ack_completion(ack, completion)

    def _resolve_pending(self, request_id):
        """Admitted (command, ack) for a queued request, registered.

        Reboot path: unknown execution records are registered and
        the run job stashed, so the pool runner finds both.
        """
        stored_command, ack = self._project.command_for(request_id)
        run_id = ack.get("run_id")
        if not self._execution.known(run_id):
            self._execution.dispatch(
                stored_command.get("operation"),
                {"cell": (stored_command.get("arguments") or {}).get("cell")},
                ack.get("snapshot_id", ""),
                run_id=run_id,
            )
        self._run_jobs.setdefault(
            run_id,
            {
                "operation": stored_command.get("operation"),
                "arguments": dict(stored_command.get("arguments") or {}),
                "snapshot_id": ack.get("snapshot_id", ""),
                "request_id": str(request_id),
            },
        )
        return stored_command, ack

    def _pool_execute(self, operation, arguments, snapshot_id, request_id,
                      run_id):
        """Execute one pooled run through its solver, contained."""
        if not self._solvers.get(operation):
            self._latest[operation] = run_id
            self._logs[run_id] = (
                f"unsupported_operation: No solver registered: {operation}."
            )
            verdict = self._execution.record_not_run(
                run_id, self._logs[run_id]
            )
            self._project.append_run_event(
                "run_failed", run_id, operation, verdict, request_id
            )
            return {
                "run_id": run_id,
                "state": "completed",
                "verdict": verdict,
                "operation": operation,
            }
        run_arguments = dict(arguments)
        run_arguments.pop("expected_revision", None)
        # REPLAY-SAFE: a kill after this mark reads as an
        # interruption at the next boot (AMBIGUOUS, counted toward
        # poison); a kill before it stays RETRYABLE.
        self._project.append_replay_event(
            "run_started",
            request_id,
            {
                "run_id": run_id,
                "content_key": content_key_for(operation, run_arguments),
                "operation": operation,
            },
        )
        return self._run_operation(
            operation,
            run_arguments,
            snapshot_id,
            request_id,
            run_id=run_id,
            contain=True,
        )

    def _run_batch(self, run_ids):
        """Pump a batch of admitted runs oldest-listed first.

        Finished runs contribute their stored completion without
        re-executing; the rest are admitted to the pool (pool_full
        refuses loudly past the bound) and drained in order. Every
        listed id lands in exactly one of completions/refused.
        """
        if not isinstance(run_ids, list) or not run_ids:
            raise ProjectError(
                "invalid_command",
                "run_job batch needs a non-empty run_ids list.",
            )
        completions = []
        refused = []
        seen = set()
        admitted = []
        for run_id in run_ids:
            if run_id in seen:
                refused.append({
                    "run_id": run_id,
                    "code": "duplicate_in_batch",
                    "message": f"Run listed twice in one batch: {run_id}.",
                })
                continue
            seen.add(run_id)
            stored = self._stored_completion(run_id)
            if stored is not None:
                completions.append(stored)
                continue
            pending = self._run_jobs.get(run_id)
            if pending is not None:
                request_id = pending["request_id"]
            else:
                request_id = request_for_run(
                    self._project.events_since(0), run_id
                )
            if request_id is None:
                refused.append({
                    "run_id": run_id,
                    "code": "unknown_request",
                    "message": f"No queued request: {run_id}.",
                })
                continue
            stored_command, ack = self._project.command_for(request_id)
            if not self._solvers.get(stored_command.get("operation")):
                refused.append({
                    "run_id": run_id,
                    "code": "unsupported_operation",
                    "message": (
                        "No solver registered: "
                        f"{stored_command.get('operation')}."
                    ),
                })
                continue
            self._resolve_pending(request_id)
            try:
                adopted = self._pool.adopt(
                    request_id, run_id, stored_command,
                    ack.get("snapshot_id", ""),
                )
            except ExecutionError as exc:
                refused.append({
                    "run_id": run_id,
                    "code": exc.code,
                    "message": str(exc),
                })
                continue
            if not adopted:
                stored = self._stored_completion(run_id)
                if stored is not None:
                    completions.append(stored)
                    continue
            admitted.append(run_id)
        if admitted:
            completions.extend(self._pool.drain_ids(admitted))
        return {
            "run_ids": list(run_ids),
            "completions": completions,
            "refused": refused,
        }

    def boot_report(self):
        """Report crash survivors without executing anything (boot report).

        Survivors are ledger admissions without a run event —
        typically a kill between admit and drain. Each carries its
        taxonomy kind (retryable, ambiguous, poison), quarantine
        state, and per-run Resume/Discard actions.

        Returns:
            Report with the session-ended message, the unfinished
                count, survivors in admit order, quarantined run
                ids, and unresolved entries.

        Caution: Report-only by construction: nothing executes
            here — every replay surface needs an explicit resume
            decision (resume_run, discard_run, resume_all_retryable).
        """
        return self._replay.boot()

    def resume_survivor(self, run_id, force=False):
        """Explicitly resume one crash survivor through its solver.

        Args:
            run_id: Survivor to resume.
            force: Required for quarantined (poison) runs; force
                bypasses quarantine only — the run still executes
                for real.

        Returns:
            Executor completion for the run.

        Raises:
            ExecutionError: unknown_survivor for an id with no
                unfinished run, already_completed for a finished
                run, already_decided for a run handled this
                session, poison_quarantined for a quarantined run
                resumed without force.

        Caution: This executes the run — the one replay surface
            that does, and only on this explicit call.
        """
        return self._replay.resume(run_id, force=force)

    def discard_survivor(self, run_id):
        """Explicitly discard one crash survivor, never executing it.

        Args:
            run_id: Survivor to discard.

        Returns:
            Discard record with run_id, discarded state, and the
                run's operation.

        Raises:
            ExecutionError: unknown_survivor for an id with no
                unfinished run, already_completed for a finished
                run, already_decided for a run handled this
                session.
        """
        return self._replay.discard(run_id)

    def resume_all_retryable(self):
        """Resume every RETRYABLE survivor, oldest first (gated).

        Ambiguous runs need individual review and poison runs need
        per-run force, so both are skipped loudly — never swept up.

        Returns:
            Batch with resumed run ids, their completions, and
                skipped entries (each with run_id, typed code, and
                user-facing message).

        Raises:
            ExecutionError: Propagates the first executor failure
                unchanged — earlier resumes stand, later ones never
                fire.

        Caution: This executes runs — only the RETRYABLE,
            non-quarantined survivors, and only on this call.
        """
        return self._replay.resume_all_retryable()

    def replay_pending(self):
        """Resume crash-surviving RETRYABLE admissions, oldest first.

        Explicit-call compat over the gated batch: same survivor
        set as the boot report, but only RETRYABLE runs execute —
        ambiguous and poison survivors are skipped loudly in the
        report instead of re-running.

        Returns:
            Report with replayed run ids (the resumed set, seq
                order), their completions, and skipped entries.
        """
        batch = self._replay.resume_all_retryable()
        return {
            "replayed": batch["resumed"],
            "completions": batch["completions"],
            "skipped": batch["skipped"],
        }

    def _replay_once(self):
        """Build the crash-survivor boot report once per Engine."""
        if self._replayed:
            return None
        self._replayed = True
        return self.boot_report()

    def _replay_execute(self, operation, arguments, snapshot_id, request_id,
                        run_id):
        """Registered pool execution for one explicit resume."""
        self._resolve_pending(request_id)
        return self._pool_execute(
            operation, arguments, snapshot_id, request_id, run_id
        )

    def _submit_pyexec(self, arguments, command):
        """Admit a python_execute request: gate, then open an approval.

        Shape validation runs before the revision gate so malformed
        requests fail before anything is persisted or queued; the
        gated submit then advances the revision and appends
        job_queued like every other operation. The ack run_id IS
        the execution id: approval admits it, run_job executes it.

        Args:
            arguments: python_execute arguments (mode plus lines
                or path, timeout_s, artifacts, expected_revision).
            command: Envelope carrying request_id.

        Returns:
            Admission mapping with the ack fields plus
                execution_id, approval_id, and pending_approval
                state. No run exists until the UI route approves.

        Raises:
            ProjectError: revision_conflict for a stale
                expected_revision, request_conflict for a reused
                envelope id with new text.
            ExecutionError: invalid_command/invalid_cell/empty_cell
                for malformed requests, path_escape/invalid_path/
                cell_unreadable for bad project files.
        """
        self._pyexec.validate_request(
            arguments.get("mode"),
            lines=arguments.get("lines"),
            path=arguments.get("path"),
            artifacts=arguments.get("artifacts", ()),
            timeout_s=arguments.get("timeout_s"),
        )
        buf = io.StringIO()
        self._yaml.dump(
            {"operation": "python_execute", "arguments": arguments}, buf)
        request_id = command.get("request_id") or uuid.uuid4().hex
        ack = self._project.submit(
            buf.getvalue(),
            str(request_id),
            expected_revision=arguments.get("expected_revision"),
        )
        handle = self._pyexec.request_execution(
            arguments["mode"],
            lines=arguments.get("lines"),
            path=arguments.get("path"),
            request_id=str(request_id),
            run_id=ack["run_id"],
            expected_revision=arguments.get("expected_revision"),
            artifacts=arguments.get("artifacts", ()),
            timeout_s=arguments.get("timeout_s"),
        )
        self._run_jobs.setdefault(
            ack["run_id"],
            {
                "operation": "python_execute",
                "arguments": dict(arguments),
                "snapshot_id": ack["snapshot_id"],
                "request_id": str(request_id),
            },
        )
        return {**ack, **handle, "state": "pending_approval"}

    def resolve_python_approval(self, approval_id, decision, actor=None):
        """Resolve a python_execute approval via the human UI route.

        Agent calls request approval; they never grant it — this
        method is the trusted UI route, and no MCP tool maps to it.

        Args:
            approval_id: Approval bound by the submit call.
            decision: `approved` to admit the queued run, `denied`
                to lapse the approval with no run.
            actor: Human actor the decision is attributed to; the
                engine actor when omitted.

        Returns:
            Resolution with approval_id, approval_state,
                execution_id, and the run_id once admitted.

        Raises:
            ExecutionError: approval_invalid/approval_denied/
                approval_expired/approval_forbidden per the
                approval ledger.

        Caution: Human route only — MCP agents must never call
            this; there is deliberately no MCP tool for it.
        """
        return self._pyexec.resolve_approval(
            approval_id, decision, via="ui",
            actor=actor if actor is not None else self._actor,
        )

    def python_console(self):
        """Read the python_execute console view.

        Returns:
            Console view with project_id, generation, env_digest,
                history cursor, and pending approvals.

        Caution: Read-only: reports approval queue state, never
            resolves anything.
        """
        return self._pyexec.console_view()

    def cancel_job(self, run_id=None):
        """Cancel a queued or running job through the job surface.

        A live python_execute worker tree is killed promptly;
        finished runs keep their terminal state, truthfully.

        Args:
            run_id: Admitted execution id to cancel.

        Returns:
            Mapping with run_id and state.

        Raises:
            ProjectError: invalid_command without a run_id.
            ExecutionError: unknown_run for an id never admitted.
        """
        if run_id is None:
            raise ProjectError(
                "invalid_command", "cancel_job needs a run_id argument."
            )
        return self._pyexec.cancel(run_id)

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
        target = arguments["target"]
        if (
            isinstance(target, dict)
            and target.get("scope", "project") == "project"
        ):
            # Project scope serves every operation and carries no
            # block: established callers (scenario harness, adapter
            # tests) address cells at project scope, so pass those
            # targets through untouched — only block scope engages.
            return None
        try:
            parsed = parse_target(target)
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

    def layer_stackup(self, pdk_id, revision=None, engine_root=None):
        """Serve one PDK's read-only layer stackup.

        The viewer/3D authority: ordered layers, metal/tech
        grouping, enabled set, colors, and Z heights parsed from
        the registered PDK's KLayout tech files (hash-verified
        through the PDK store).

        Args:
            pdk_id: Canonical display id (either spelling resolves).
            revision: Revision pin; the newest registered revision
                when omitted.
            engine_root: Explicit store root; resolved when omitted.

        Returns:
            Stackup record with layers, enabled set, groups, and
                Z completeness.

        Raises:
            ProjectError: invalid_command for a missing pdk_id.
            PdkError: unknown_pdk for a missing store/id/revision
                or .lyp deck, pdk_drift for a tampered file.
            LayerServingError: unknown_stackup for a PDK with no
                stackup mapping.
        """
        if not pdk_id:
            raise ProjectError(
                "invalid_command", "get_layer_stackup needs a pdk_id argument."
            )
        return get_stackup(pdk_id, revision=revision, engine_root=engine_root)

    def layer_rows(self, pdk_id, preset=None, overrides=None, active=None,
                   revision=None, engine_root=None):
        """Render viewer rows for one PDK's stackup.

        Row visibility defaults to the PDK flags; an explicit
        preset applies first, then per-layer overrides, then the
        active layer.

        Args:
            pdk_id: Canonical display id (either spelling resolves).
            preset: Built-in or user preset to apply; PDK defaults
                when omitted.
            overrides: Sparse {layer name: visible} wins over the
                preset map.
            active: Active layer override; the preset active when
                omitted.
            revision: Revision pin; the newest registered revision
                when omitted.
            engine_root: Explicit store root; resolved when omitted.

        Returns:
            Page with stackup_ref, preset, flip, active, and
                file-order rows.

        Raises:
            ProjectError: invalid_command for a missing pdk_id.
            PdkError: unknown_pdk for a missing store/id/revision.
            LayerServingError: unknown_stackup for an unmapped
                PDK, unknown_preset for a missing preset,
                invalid_preset for a stale user preset,
                invalid_visibility for bad overrides/active.
        """
        if not pdk_id:
            raise ProjectError(
                "invalid_command", "get_layer_rows needs a pdk_id argument."
            )
        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
        if preset is None:
            return viewer_rows(stackup, visibility=overrides, active=active)
        return viewer_rows_for_preset(
            self._layer_presets, stackup, preset,
            overrides=overrides, active=active,
        )

    def layer_presets(self):
        """List built-in plus user layer preset names.

        Returns:
            Mapping with preset name records (name + builtin),
                built-ins first in pinned order.
        """
        return {"presets": self._layer_presets.list_presets()}

    def layer_preset_save(self, pdk_id, name, layers, render_layers=None,
                          flip=False, active=None, overwrite=False,
                          revision=None, engine_root=None):
        """Save a user layer preset against one PDK's stackup.

        Missing layer names default to hidden; apply() resolves
        the full map.

        Args:
            pdk_id: Canonical display id (either spelling resolves).
            name: Preset name (built-in names are reserved).
            layers: Sparse {layer name: visible} map.
            render_layers: {toggle: bool} viewer aids; the default
                set when omitted.
            flip: View-from-bottom flag.
            active: Active layer name, or None.
            overwrite: Replace an existing user preset of the same
                name instead of conflicting.
            revision: Revision pin; the newest registered revision
                when omitted.
            engine_root: Explicit store root; resolved when omitted.

        Returns:
            Stored preset record (builtin False).

        Raises:
            ProjectError: invalid_command for a missing pdk_id.
            PdkError: unknown_pdk for a missing store/id/revision.
            LayerServingError: unknown_stackup for an unmapped
                PDK, invalid_preset for a bad name/shape,
                preset_conflict for a built-in name or an
                existing preset without overwrite.

        Caution: View state, not project state: presets live in
            Engine memory (no revision advance, no ledger event)
            and are lost on restart until a durable store lands.
        """
        if not pdk_id:
            raise ProjectError(
                "invalid_command", "save_layer_preset needs a pdk_id argument."
            )
        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
        return self._layer_presets.save(
            stackup, name, layers, render_layers=render_layers,
            flip=flip, active=active, overwrite=overwrite,
        )

    def layer_preset_delete(self, name):
        """Delete one user layer preset (built-ins are undeletable).

        Args:
            name: Preset name to delete.

        Returns:
            Deletion record with the deleted name.

        Raises:
            ProjectError: invalid_command for a missing name.
            LayerServingError: preset_conflict for a built-in
                name; unknown_preset for a missing user preset.

        Caution: In-memory only: deletes the Engine-memory preset,
            no revision advance, no ledger event.
        """
        if not name:
            raise ProjectError(
                "invalid_command", "delete_layer_preset needs a name argument."
            )
        return self._layer_presets.delete(name)

    def layer_preset_apply(self, pdk_id, name, revision=None, engine_root=None):
        """Explicitly apply one layer preset to a Stackup.

        Args:
            pdk_id: Canonical display id (either spelling resolves).
            name: Built-in or user preset name.
            revision: Revision pin; the newest registered revision
                when omitted.
            engine_root: Explicit store root; resolved when omitted.

        Returns:
            Full preset record with the complete layers map,
                renderLayers, flip, and active.

        Raises:
            ProjectError: invalid_command for a missing pdk_id
                or name.
            PdkError: unknown_pdk for a missing store/id/revision.
            LayerServingError: unknown_stackup for an unmapped
                PDK, unknown_preset for a missing preset,
                invalid_preset for a stale user preset.
        """
        if not pdk_id:
            raise ProjectError(
                "invalid_command", "apply_layer_preset needs a pdk_id argument."
            )
        if not name:
            raise ProjectError(
                "invalid_command", "apply_layer_preset needs a name argument."
            )
        stackup = get_stackup(pdk_id, revision=revision, engine_root=engine_root)
        return self._layer_presets.apply(stackup, name)

    def _query_layer(self, name, arguments):
        """Route a layer-serving query to its Engine reader."""
        if name == "get_layer_stackup":
            return self.layer_stackup(
                arguments.get("pdk_id"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "get_layer_rows":
            return self.layer_rows(
                arguments.get("pdk_id"),
                preset=arguments.get("preset"),
                overrides=arguments.get("overrides"),
                active=arguments.get("active"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "list_layer_presets":
            return self.layer_presets()
        if name == "save_layer_preset":
            return self.layer_preset_save(
                arguments.get("pdk_id"),
                arguments.get("name"),
                arguments.get("layers"),
                render_layers=arguments.get("render_layers"),
                flip=arguments.get("flip", False),
                active=arguments.get("active"),
                overwrite=arguments.get("overwrite", False),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
        if name == "delete_layer_preset":
            return self.layer_preset_delete(arguments.get("name"))
        if name == "apply_layer_preset":
            return self.layer_preset_apply(
                arguments.get("pdk_id"),
                arguments.get("name"),
                revision=arguments.get("revision"),
                engine_root=arguments.get("engine_root"),
            )
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

    def resolve_celllinks(self, blocks, known_cells, variant=None):
        """Resolve run/export cell-link records for block instances.

        CELL-LINK seam: resolves (cell, pinMap, variant) per block
        through interfaces.celllink, emitting only non-empty links.
        Editing stays free — unknown cells fail here, at run time.

        Args:
            blocks: Block mappings, each with an id and an optional
                CellLink component.
            known_cells: Available cell names the run may target.
            variant: Variant name applied to every block; None and
                REFERENCE resolve each stored base link.

        Returns:
            Emission records in input order, each with block, cell,
            pinMap, and variant keys.

        Raises:
            ContractError: invalid_block for a malformed block
                entry, unknown_variant for an undefined variant.
            CellLinkError: unknown_cell naming the block and cell
                when a resolved cell is unavailable to the run.
        """
        return resolve_celllink_run(blocks, known_cells, variant=variant)

    def _run_queued(self, command):
        """Execute admitted requests by id: deferred singles, fetch, batches.

        Submit already ran inline, so this is the explicit path:
        deferred execution for admissions drained elsewhere
        (crash survivors, staged backlog), idempotent fetch for
        finished runs, and ordered batch pumping.

        Request keys:
            run_id: Admitted run to execute or fetch.
            request_id: Envelope id admitted by an earlier submit
                (resolves to its run when run_id is absent).
            run_ids: Batch form — admitted runs to pump oldest
                listed first.

        Args:
            command: Envelope whose arguments carry run_id,
                request_id, or run_ids.

        Returns:
            Completion mapping with run_id, state, verdict, and
            operation for a single id (stored, never
            re-executed, when the run already finished); batch
            mapping with run_ids, completions, and refused for
            the batch form (every listed id lands in exactly
            one of the two lists).

        Raises:
            ProjectError: invalid_command when the arguments lack a
                run id or the batch list is malformed,
                unknown_request for an id never admitted,
                unsupported_operation when the admitted
                operation has no registered solver.
        """
        arguments = dict(command.get("arguments") or {})
        if arguments.get("run_ids") is not None:
            return self._run_batch(arguments.get("run_ids"))
        run_id = arguments.get("run_id")
        if run_id is not None:
            # Idempotent fetch: a finished run returns its stored
            # completion instead of executing again.
            stored = self._stored_completion(run_id)
            if stored is not None:
                return stored
            pending = self._run_jobs.get(run_id)
            if pending is None:
                # Reboot path: the admitting request survives in
                # the ledger even though this process never saw it.
                queued_request = request_for_run(
                    self._project.events_since(0), run_id
                )
                if queued_request is None:
                    raise ProjectError(
                        "unknown_request", f"No queued request: {run_id}."
                    ) from None
                stored_command, ack = self._project.command_for(
                    queued_request
                )
                pending = {
                    "operation": stored_command.get("operation"),
                    "arguments": dict(stored_command.get("arguments") or {}),
                    "snapshot_id": ack.get("snapshot_id", ""),
                    "request_id": str(queued_request),
                }
                self._run_jobs[run_id] = pending
            stored_operation = pending["operation"]
            run_arguments = dict(pending["arguments"])
            snapshot_id = pending["snapshot_id"]
            request_id = pending["request_id"]
        else:
            request_id = arguments.get("request_id")
            if request_id is None:
                raise ProjectError(
                    "invalid_command",
                    "run_job needs a run_id, request_id, or run_ids argument.",
                )
            stored_command, ack = self._project.command_for(request_id)
            stored_operation = stored_command.get("operation")
            run_arguments = dict(stored_command.get("arguments") or {})
            snapshot_id = ack.get("snapshot_id", "")
            request_id = str(request_id)
            run_id = ack.get("run_id")
            completion = self._stored_completion(run_id)
            if completion is not None:
                return completion
        if stored_operation == "python_execute":
            return self._run_pyexec(run_id, request_id)
        if not self._solvers.get(stored_operation):
            raise ProjectError(
                "unsupported_operation", f"No solver registered: {stored_operation}."
            )
        if not self._execution.known(run_id):
            # Reboot path: the ledger admitted this run, but this
            # process holds no execution record for it yet.
            self._execution.dispatch(
                stored_operation,
                {"cell": run_arguments.get("cell")},
                snapshot_id,
                run_id=run_id,
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

    def _run_pyexec(self, run_id, request_id):
        """Execute an admitted python_execute run (phase 2).

        Approval lapses propagate as approval errors — approval
        state is never folded into a verdict. Completion carries
        the NOT_RUN verdict (zero exit is never check PASS) and
        appends the run_failed ledger event the NOT_RUN shape
        owns; cancellation returns the cancelled state with no
        ledger event, like every cancelled job.

        Args:
            run_id: Admitted execution id (the submit ack id).
            request_id: Queued request this run discharges.

        Returns:
            Completion mapping with run_id, state, verdict, and
                operation.

        Raises:
            ExecutionError: unknown_run for an id never admitted,
                approval_pending/approval_denied/approval_expired
                when the approval lapses, approval_invalid for
                binding drift.

        Caution: Runs the approved worker now — read the verdict
            (always NOT_RUN) plus the execution record, never the
            exit path.
        """
        record = self._pyexec.run_job(run_id)
        self._latest["python_execute"] = run_id
        log = record.get("stdout", "")
        if record.get("stderr"):
            log += "\n--- stderr ---\n" + record["stderr"]
        self._logs[run_id] = log
        if record["state"] == "cancelled":
            return {
                "run_id": run_id,
                "state": "cancelled",
                "verdict": record["verdict"],
                "operation": "python_execute",
            }
        self._project.append_run_event(
            "run_failed", run_id, "python_execute", record["verdict"],
            request_id,
        )
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": record["verdict"],
            "operation": "python_execute",
        }

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
            CRUD/rewind/place_cell operations return the immediate
            mutation mapping instead (new revision + events +
            approval-UI fields).

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
                mutation or place_cell is malformed, or a rewind
                lacks a target or targets the live head,
                revision_conflict for a stale CRUD/rewind/
                place_cell expected_revision,
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
        self._replay_once()
        name = command.get("operation")
        if name == "run_job":
            return self._run_queued(command)
        if name in _CRUD_OPERATIONS or name == "place_cell":
            return self.submit(command)
        if name == "python_execute":
            raise ProjectError(
                "invalid_command",
                "python_execute needs submit, human approval, then "
                "run_job; direct run cannot approve.",
            )
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
