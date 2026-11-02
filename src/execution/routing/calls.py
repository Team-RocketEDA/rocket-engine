"""Tier-2 call shapes, effects reports, and addressing."""

import io
import uuid

from ruamel.yaml import YAML

from ...stores import ecs
from ..errors import ExecutionError


#: Doc writes: the CRUD document verbs, newest revision wins by gate.
DOC_VERBS = ("apply_mutations", "delete_doc", "write_doc")

#: Cell add/place: catalogue instances landing as component docs.
CELL_VERBS = ("place_cell",)

#: Entity store verbs (ENGINE-ECS): components over projected docs.
ECS_VERBS = (
    "attach_component",
    "create_entity",
    "delete_entity",
    "detach_component",
    "set_component",
)

#: Wire/junction verbs (WIRE-PLACE): connectivity as durable data.
WIRE_VERBS = (
    "connect_endpoint",
    "delete_junction",
    "delete_wire",
    "materialize_nets",
    "move_wire",
    "place_junction",
    "place_wire",
    "split_wire",
)

#: Sibling project mutations sharing the identical admission path.
PROJECT_VERBS = ("create_project", "rewind", "write_settings")

#: Every console tier-2 operation: project-state mutations admitted
#: through the ledger. Reads, solver runs, and unknown names stay
#: tier-1 (dispatch and the vocabulary gate own those).
TIER_2_OPERATIONS = frozenset(
    list(DOC_VERBS) + list(CELL_VERBS) + list(ECS_VERBS)
    + list(WIRE_VERBS) + list(PROJECT_VERBS)
)

#: Console namespace verbs, sorted: one wrapper per name on both
#: ConsoleNamespace (host-side admission) and ConsoleTools
#: (worker-side recording).
CONSOLE_TOOL_VERBS = tuple(sorted(TIER_2_OPERATIONS))


def tier_for(operation):
    """Classify one operation into its console tier.

    Args:
        operation: Operation name to classify (any value tolerated).

    Returns:
        2 for project-state mutations routing through admission, 1
            for reads, solver runs, unknown names, and non-text.
    """
    if isinstance(operation, str) and operation in TIER_2_OPERATIONS:
        return 2
    return 1


def is_tier2(operation):
    """True when an operation is a tier-2 admitted mutation.

    Args:
        operation: Operation name to test (any value tolerated).

    Returns:
        True for tier-2 verbs, False for everything else.
    """
    return tier_for(operation) == 2


def admission_envelope(operation, arguments):
    """Render one admission identity text for a tier-2 call.

    The text carries the operation plus its arguments through the
    same YAML dumper the Engine uses, so identical calls admit with
    identical identity and resubmits replay instead of duplicating.

    Args:
        operation: Tier-2 operation name for the envelope.
        arguments: Operation arguments carried on the envelope.

    Returns:
        YAML command text identifying this exact call.

    Raises:
        ExecutionError: invalid_command for a non-text operation,
            non-mapping arguments, or values no YAML dumper spans.
    """
    if not isinstance(operation, str) or not operation:
        raise ExecutionError(
            "invalid_command",
            f"Envelope needs a text operation, got {operation!r}.",
        )
    if not isinstance(arguments, dict):
        raise ExecutionError(
            "invalid_command",
            f"Envelope needs mapping arguments, got {arguments!r}.",
        )
    # Fresh dumper per call: a failed ruamel dump poisons the
    # instance (it then emits empty text forever), which would
    # collapse distinct calls onto one identity.
    buf = io.StringIO()
    try:
        YAML(typ="safe").dump(
            {"operation": operation, "arguments": arguments}, buf
        )
    except Exception as exc:
        raise ExecutionError(
            "invalid_command",
            f"Envelope arguments do not serialize: {exc}.",
        ) from exc
    return buf.getvalue()


def stamp_tier2_call(operation, arguments, expected_revision,
                     request_id=None):
    """Bind live admission identity onto one recorded tier-2 call.

    Console replay stamps what the cell left open: a tier-2 call
    without a caller binding gains the live head revision, and a
    call without an envelope id gains a fresh one. Caller bindings
    win verbatim — a cell that pinned its own revision replays at
    that revision and fails loudly when it drifted. Tier-1 calls
    pass through untouched.

    Args:
        operation: Recorded operation name.
        arguments: Recorded arguments mapping.
        expected_revision: Live head revision to bind when the
            caller bound none.
        request_id: Envelope id to keep, or None for a fresh one
            on tier-2 calls.

    Returns:
        (arguments, request_id) pair: a new arguments mapping with
            the binding filled when it was missing, plus the kept
            or minted envelope id.

    Raises:
        ExecutionError: invalid_command for non-mapping arguments.
    """
    if not isinstance(arguments, dict):
        raise ExecutionError(
            "invalid_command",
            f"Stamp needs mapping arguments, got {arguments!r}.",
        )
    if not is_tier2(operation):
        return dict(arguments), request_id
    stamped = dict(arguments)
    if "expected_revision" not in stamped:
        stamped["expected_revision"] = expected_revision
    return stamped, request_id or uuid.uuid4().hex


def tool_call(operation, arguments):
    """Build one canonical worker-side op-call record.

    Args:
        operation: Operation name for the record.
        arguments: Op arguments copied onto the record.

    Returns:
        Op-call mapping with operation plus a copy of arguments —
            the prelude JSONL shape, host replayable.

    Raises:
        ExecutionError: invalid_command for a non-text operation
            or non-mapping arguments.
    """
    if not isinstance(operation, str) or not operation:
        raise ExecutionError(
            "invalid_command",
            f"Op call needs a text operation, got {operation!r}.",
        )
    if not isinstance(arguments, dict):
        raise ExecutionError(
            "invalid_command",
            f"Op call needs mapping arguments, got {arguments!r}.",
        )
    return {"operation": operation, "arguments": dict(arguments)}


def collect_run_ids(op_results):
    """Lift child run ids off replayed op results.

    Args:
        op_results: Per-op replay outcomes (ok plus result, or ok
            False plus error); None reads as no results.

    Returns:
        Run ids in replay order: one per ok result carrying a text
            run_id, everything else skipped.
    """
    run_ids = []
    for item in op_results or []:
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        result = item.get("result")
        if isinstance(result, dict) and isinstance(
            result.get("run_id"), str
        ):
            run_ids.append(result["run_id"])
    return run_ids


def build_effects_report(ops, op_results, ops_skipped=0, replayed=True):
    """Pack replayed ops as the shared effects shape.

    Args:
        ops: Recorded op calls in replay order.
        op_results: Per-op replay outcomes aligned with ops.
        ops_skipped: Harvest lines dropped as malformed.
        replayed: True once a dispatcher replayed the calls; an
            unreplayed bundle is ok only when it holds no ops.

    Returns:
        Effects mapping with ops, per-op results, the ok flag,
            the skip count, child run ids, and the replayed flag.
    """
    results = list(op_results or [])
    calls = list(ops or [])
    if replayed:
        ops_ok = all(item.get("ok") for item in results)
    else:
        ops_ok = not calls
    return {
        "ops": calls,
        "op_results": results,
        "ops_ok": ops_ok,
        "ops_skipped": ops_skipped,
        "run_ids": collect_run_ids(results),
        "replayed": bool(replayed),
    }


def report_completions(run_ids, fetch):
    """Report stored completions for run ids without executing.

    A read-only batch read-back: every id resolves through fetch
    (a stored-completion reader such as the job surface), unknown
    ids land in refused with their code, and ids listed twice are
    refused as duplicates — nothing runs, nothing advances, and a
    second report over the same ids reads the same values.

    Args:
        run_ids: Non-empty list of run ids to report.
        fetch: Callable mapping one run id to its stored
            completion; per-id failures land in refused.

    Returns:
        Report mapping with the asked run ids, their completions
            in order, and refused entries (run_id, code, message).

    Raises:
        ExecutionError: invalid_command for an empty or
            non-list run_ids, a non-text id, or a non-callable
            fetch.
    """
    if not isinstance(run_ids, list) or not run_ids:
        raise ExecutionError(
            "invalid_command",
            "report_completions needs a non-empty run_ids list.",
        )
    for run_id in run_ids:
        if not isinstance(run_id, str) or not run_id:
            raise ExecutionError(
                "invalid_command",
                f"Run id must be non-empty text, got {run_id!r}.",
            )
    if not callable(fetch):
        raise ExecutionError(
            "invalid_command", "report_completions needs a fetch reader."
        )
    completions = []
    refused = []
    seen = set()
    for run_id in run_ids:
        if run_id in seen:
            refused.append({
                "run_id": run_id,
                "code": "duplicate_in_batch",
                "message": f"Run listed twice in one report: {run_id}.",
            })
            continue
        seen.add(run_id)
        try:
            completions.append(fetch(run_id))
        except Exception as exc:  # per-id truth: record, never raise
            refused.append({
                "run_id": run_id,
                "code": getattr(exc, "code", None) or "internal_error",
                "message": str(exc),
            })
    return {"run_ids": list(run_ids), "completions": completions,
            "refused": refused}


def entity_doc_path(entity):
    """Derive the one doc path storing an entity.

    Shared ENGINE-ECS addressing: this wrapper names the same
    function the store and the wired verbs use, so console paths
    cannot drift onto a second projection.

    Args:
        entity: Entity id to project.

    Returns:
        Canonical entities path for the id.

    Raises:
        EcsError: invalid_entity for a malformed id (propagated
            unchanged from the shared substrate).
    """
    return ecs.entity_doc_path(entity)


def parse_address(address):
    """Split one canonical entity.component address.

    Shared ENGINE-ECS addressing, same function as the store.

    Args:
        address: Address text with exactly one dot.

    Returns:
        (entity, component) pair, both validated.

    Raises:
        EcsError: invalid_address for a malformed address
            (propagated unchanged from the shared substrate).
    """
    return ecs.parse_address(address)


def format_address(entity, component):
    """Render one canonical entity.component address.

    Shared ENGINE-ECS addressing, same function as the store.

    Args:
        entity: Entity id part.
        component: Component name part.

    Returns:
        Canonical address text.

    Raises:
        EcsError: invalid_entity or invalid_component for
            malformed parts (propagated unchanged).
    """
    return ecs.format_address(entity, component)
