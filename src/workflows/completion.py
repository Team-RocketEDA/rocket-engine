"""Design-completion gate: stage plans plus fully-verified claims (I27).

`plan_checks_report` wires the stage inventory to caller backends so
required-but-blocked stages surface instead of vanishing; every
planned stage stays required and reports ready or blocked with its
missing operations. `design_completion_report` layers the latest
check verdicts over that plan: any blocked, unverified, or failing
stage becomes a named blocker (mixed M14 cites run_thermal, and the
vocab-only run_thermal operation appears as its own blocker), the
report refuses the fully-verified claim while any stand, and only
an all-satisfied plan claims with per-operation evidence run ids.
"""

from .stages import applicable_stages

# Scripted entrypoints need no backend (mirrors stages._SCRIPTED).
_SCRIPTED = frozenset({"project scripting", "get_capabilities", "ip_instantiate"})


def _tool_ops(stage):
    """Tool entrypoints one stage needs (scripted entries excluded)."""
    return [e for e in stage["entrypoints"] if e not in _SCRIPTED]


def _missing_ops(stage, available):
    """Tool entrypoints one stage needs but no backend serves."""
    return [e for e in _tool_ops(stage) if e not in available]


def _check_status(record):
    """Verdict status for one check record (None when never ran)."""
    if record is None:
        return None
    if not isinstance(record, dict):
        return "unknown"
    status = record.get("status")
    if status is None:
        verdict = record.get("verdict")
        if isinstance(verdict, dict):
            status = verdict.get("status")
    return status if status is not None else "unknown"


def _run_id(record):
    """String run id for one check record (None when absent)."""
    if isinstance(record, dict) and isinstance(record.get("run_id"), str):
        return record["run_id"]
    return None


def plan_checks_report(flow, available_backends):
    """Plan one flow against installed backends with named blockers.

    Thin report over `applicable_stages`: every planned stage keeps
    its required flag and gains its readiness plus the exact missing
    operations, so a caller can name required-but-blocked stages
    (mixed M14 cites run_thermal) instead of silently dropping them.

    Args:
        flow: Flow inventory to plan (digital/analog/photonic/mixed).
        available_backends: Installed backend entrypoint names.

    Returns:
        Mapping with the flow, per-stage plans (each carrying
            readiness plus missing_operations), blocked_stages and
            ready_stages id lists in stage order, and the sorted
            unique missing_operations across blocked stages.

    Raises:
        ValueError: Unknown flow name.
    """
    available = set() if available_backends is None else set(available_backends)
    planned = applicable_stages(flow, available)
    stages = []
    for stage in planned:
        stages.append({**stage, "missing_operations": _missing_ops(stage, available)})
    blocked = [s["id"] for s in stages if s["readiness"] == "blocked"]
    ready = [s["id"] for s in stages if s["readiness"] == "ready"]
    missing = sorted({op for stage in stages for op in stage["missing_operations"]})
    return {
        "flow": flow,
        "stages": stages,
        "blocked_stages": blocked,
        "ready_stages": ready,
        "missing_operations": missing,
    }


def design_completion_report(flow, available_backends, checks, current_revision=None):
    """Judge one flow's completion: blockers stand or evidence claims.

    Combines the stage plan with the latest check verdicts. A stage
    whose backends are missing blocks as blocked_stage; a ready tool
    stage whose operation never ran blocks as unverified_stage; a
    ready stage whose latest verdict is not PASS blocks as
    failing_check with its run id. Missing operations additionally
    appear as missing_operation blockers so vocab-only names such as
    run_thermal never vanish silently. Scripted-only stages need no
    solver evidence and never block. While any blocker stands the
    report refuses the claim (fully_verified False, claim None);
    only a blocker-free plan claims fully verified with evidence.

    Args:
        flow: Flow inventory to judge (digital/analog/photonic/mixed).
        available_backends: Installed backend entrypoint names.
        checks: Mapping of operation to its latest check record
            (the checks value from Engine.check_results: each with
            status plus run_id); absent operations read never_run.
        current_revision: Project revision to echo; None when unknown.

    Returns:
        Mapping with the flow, fully_verified flag, claim (fully
            verified) or refusal text, blockers in stage order with
            missing-operation entries after, sorted unique
            missing_operations, evidence mapping each PASS operation
            to its run id, per-stage plans carrying stage_status plus
            run_ids, and the echoed current_revision.

    Raises:
        ValueError: Unknown flow name.
    """
    available = set() if available_backends is None else set(available_backends)
    seen = dict(checks) if checks is not None else {}
    plan = plan_checks_report(flow, available)
    blockers = []
    stages_out = []
    for stage in plan["stages"]:
        tool_ops = _tool_ops(stage)
        missing = stage["missing_operations"]
        if missing:
            blockers.append(
                {
                    "kind": "blocked_stage",
                    "stage": stage["id"],
                    "step": stage["step"],
                    "missing_operations": list(missing),
                    "required": stage["required"],
                }
            )
            stages_out.append({**stage, "stage_status": "blocked", "run_ids": {}})
            continue
        if not tool_ops:
            stages_out.append({**stage, "stage_status": "verified", "run_ids": {}})
            continue
        run_ids = {}
        failing = []
        unverified = []
        for op in tool_ops:
            record = seen.get(op)
            if op not in seen:
                unverified.append(
                    {
                        "kind": "unverified_stage",
                        "stage": stage["id"],
                        "step": stage["step"],
                        "operation": op,
                        "status": "never_run",
                    }
                )
                continue
            status = _check_status(record)
            rid = _run_id(record)
            if rid is not None:
                run_ids[op] = rid
            if status == "PASS":
                continue
            failing.append(
                {
                    "kind": "failing_check",
                    "stage": stage["id"],
                    "step": stage["step"],
                    "operation": op,
                    "status": status,
                    "run_id": rid,
                }
            )
        blockers.extend(failing)
        blockers.extend(unverified)
        if failing:
            stage_status = "failing"
        elif unverified:
            stage_status = "unverified"
        else:
            stage_status = "verified"
        stages_out.append({**stage, "stage_status": stage_status, "run_ids": run_ids})
    for op in plan["missing_operations"]:
        stages_needing = sorted(
            s["id"] for s in plan["stages"] if op in s["missing_operations"]
        )
        blockers.append(
            {"kind": "missing_operation", "operation": op, "stages": stages_needing}
        )
    evidence = {}
    for op in sorted(available):
        record = seen.get(op)
        if _check_status(record) == "PASS":
            rid = _run_id(record)
            if rid is not None:
                evidence[op] = rid
    fully_verified = not blockers
    return {
        "flow": flow,
        "fully_verified": fully_verified,
        "claim": "fully verified" if fully_verified else None,
        "refusal": None
        if fully_verified
        else f"{len(blockers)} blocker(s) stand; not fully verified.",
        "blockers": blockers,
        "missing_operations": plan["missing_operations"],
        "evidence": evidence,
        "stages": stages_out,
        "current_revision": current_revision,
    }
