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
