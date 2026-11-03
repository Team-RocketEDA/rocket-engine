"""Target+canvas gating over a flow plan (WIRE-DECLARED-OPS MC-25).

`plan_checks_report` plans a flow against backends only; this
module scopes that plan to a v1 target and canvas without
changing readiness. Every stage names its deck tools (joined
through the stages DECKS table), the canvas tool settings for
those tools, and the project-top metric budgets it must
satisfy — cost (settings) and evidence travel with the plan.
Constraints naming a `target` stay plan-level (`scoped_targets`)
for the run to scope; only project-top budgets gate stages.
"""

from .stages import DECKS


def _target_or_raise(target):
    """Clean one v1 target to its kind plus project scope.

    Args:
        target: Target mapping with a non-empty kind.

    Returns:
        Cleaned target with kind plus project_id/cell when given.

    Raises:
        ValueError: Non-mapping target or a missing kind.
    """
    if not isinstance(target, dict) or not isinstance(
        target.get("kind"), str
    ) or not target["kind"]:
        raise ValueError(f"Plan target needs a kind: {target!r}.")
    clean = {"kind": target["kind"]}
    for key in ("project_id", "cell"):
        if target.get(key) is not None:
            clean[key] = target[key]
    return clean


def _canvas_or_raise(canvas):
    """Clean one canvas to metric budgets plus tool settings.

    Args:
        canvas: Canvas mapping with optional `targets`
            (MetricConstraint list) and `tools` (tool settings);
            None means an empty canvas.

    Returns:
        (budgets, scoped, tools): project-top budget mappings,
            target-scoped (metric, target) pairs, and the tool
            settings mapping.

    Raises:
        ValueError: Non-mapping canvas, a non-list targets, or
            a non-mapping tools.
    """
    if canvas is None:
        return [], [], {}
    if not isinstance(canvas, dict):
        raise ValueError(f"Plan canvas must be a mapping: {canvas!r}.")
    targets = canvas.get("targets", [])
    tools = canvas.get("tools", {})
    if not isinstance(targets, list) or any(
        not isinstance(item, dict) or not item.get("metric")
        for item in targets
    ):
        raise ValueError(f"Plan canvas targets malformed: {targets!r}.")
    if not isinstance(tools, dict):
        raise ValueError(f"Plan canvas tools malformed: {tools!r}.")
    budgets = [
        {"metric": item["metric"], "operator": item.get("operator"),
         "limit": item.get("limit")}
        for item in targets
        if item.get("target") is None
    ]
    scoped = [
        {"metric": item["metric"], "target": item["target"]}
        for item in targets
        if item.get("target") is not None
    ]
    return budgets, scoped, dict(tools)


def _stage_tools(stage):
    """Sorted deck-tool names serving one stage's entrypoints.

    Args:
        stage: Planned stage with entrypoints.

    Returns:
        Sorted tool names from the DECKS table (scripted and
            uncovered entrypoints contribute none).
    """
    tools = set()
    for entrypoint in stage.get("entrypoints", []):
        for cite in DECKS.get(entrypoint, []):
            tools.add(cite["tool"])
    return sorted(tools)


def gate_plan_for_target(plan, target, canvas=None):
    """Scope one flow plan to a target and canvas.

    Readiness is untouched — the gate only joins cost and
    evidence: per-stage deck tools, the canvas tool settings for
    those tools, and the project-top metric budgets every stage
    must satisfy.

    Args:
        plan: Flow plan mapping with flow plus stages (as from
            plan_checks_report).
        target: v1 target the plan serves (kind required).
        canvas: Canvas mapping with targets/tools; None means an
            empty canvas.

    Returns:
        Plan mapping plus target, canvas_metrics, canvas_tools,
            scoped_targets, and per-stage target_kind, tools,
            canvas_tools, and budgets.

    Raises:
        ValueError: Bad target or canvas shape.
    """
    clean_target = _target_or_raise(target)
    budgets, scoped, tools = _canvas_or_raise(canvas)
    stages = []
    for stage in plan.get("stages", []):
        stage_tools = _stage_tools(stage)
        stages.append({
            **stage,
            "target_kind": clean_target["kind"],
            "tools": stage_tools,
            "canvas_tools": {tool: tools[tool] for tool in stage_tools
                             if tool in tools},
            "budgets": [dict(budget) for budget in budgets],
        })
    return {
        **plan,
        "target": clean_target,
        "canvas_metrics": [b["metric"] for b in budgets]
        + [s["metric"] for s in scoped],
        "canvas_tools": sorted(tools),
        "scoped_targets": scoped,
        "stages": stages,
    }
