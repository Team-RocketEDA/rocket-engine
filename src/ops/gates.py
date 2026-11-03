"""Engine ops mixin: Solver selection, target/constraint admission and block scope."""

from ..execution.block_runs_scope import (BlockScopeError, check_operation_scope, parse_target, resolve_block, snapshot_closure)
from ..interfaces.runparams import RunParamsError, validate_run_request
from ..project.errors import ProjectError


class _GateMixin:
    """Solver selection, target/constraint admission and block scope."""

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


#: (operation, deck tool) -> prerequisite operations that must each
#: hold at least one PASS verdict in this project. Declared by engine
#: maintainers here — never by caller arguments. Hard deps are
#: structural (LVS after extraction) and never forceable.
HARD_DEPS = {
    ("run_lvs", "netgen"): ("run_extraction",),
    ("run_post_layout", "ngspice"): ("run_spice",),
    ("run_timing", "opensta"): ("run_synth",),
    ("run_digital_flow", "librelane"): ("run_syntax",),
    ("run_formal", "sby"): ("run_synth",),
}

#: operation -> gate operations whose latest verdict must be PASS.
#: `force=True` on the command bypasses these (and only these).
VERDICT_GATES = {
    "run_post_layout": ("run_spice",),
    "run_timing": ("run_synth",),
    "run_formal": ("run_synth",),
}

_PASS = "PASS"

_COMPLETION_EVENTS = ("run_completed", "run_failed")


def hard_dependencies(operation, deck_tool=None, caller_depends_on=None):
    """Prerequisite operations for one solver lane.

    Args:
        operation: Solver operation about to be admitted.
        deck_tool: Deck tool qualifier, or None for any deck.
        caller_depends_on: Accepted and ignored — callers never
            shape the gate table.

    Returns:
        Prerequisite operation names (possibly empty).
    """
    return HARD_DEPS.get((operation, deck_tool), ()) or HARD_DEPS.get(
        (operation, None), ()
    )


def _completions(project):
    """(seq, operation, status) triples from the durable ledger."""
    try:
        events = project.events_since(0)
    except Exception:
        return []
    out = []
    for event in events or []:
        if event.get("event") not in _COMPLETION_EVENTS:
            continue
        data = event.get("data") or {}
        operation = data.get("operation")
        verdict = data.get("verdict") or {}
        if operation is None:
            continue
        out.append((event.get("seq", 0), operation, verdict.get("status")))
    return out


def check_submit_gates(operation, arguments, project, force=False):
    """Refuse an illegal solver sequence before admission.

    Args:
        operation: Solver operation about to be admitted.
        arguments: Submit arguments (deck tool read from
            `deck.tool` when it is a mapping).
        project: Project port with `events_since(cursor)`.
        force: Bypass verdict gates only; hard deps still refuse.

    Returns:
        None when every gate holds.

    Raises:
        ProjectError: unmet_dependency naming the unmet gate —
            for an unmet hard dep (never forceable) or a
            non-PASS latest verdict (forceable).
    """
    deck = (arguments or {}).get("deck")
    deck_tool = deck.get("tool") if isinstance(deck, dict) else None
    completions = _completions(project)

    for prereq in hard_dependencies(operation, deck_tool):
        if any(op == prereq and status == _PASS for _, op, status in completions):
            continue
        raise ProjectError(
            "unmet_dependency",
            f"{operation} needs {prereq} PASS before dispatch "
            f"(gate: {prereq}).",
            fields=[{"gate": prereq}],
        )

    if force:
        return None
    latest = {}
    for seq, op, status in completions:
        if seq >= latest.get(op, (-1, None))[0]:
            latest[op] = (seq, status)
    for gate in VERDICT_GATES.get(operation, ()):
        if latest.get(gate, (None, None))[1] != _PASS:
            raise ProjectError(
                "unmet_dependency",
                f"{operation} needs latest {gate} PASS before dispatch "
                f"(gate: {gate}); resubmit with force to bypass.",
                fields=[{"gate": gate}],
            )
    return None
