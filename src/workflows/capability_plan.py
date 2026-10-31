"""Capability-aware stage planning: readiness from tool truth, not wiring.

`applicable_stages` plans against a caller-supplied backend set,
which reads ready whenever an operation is merely wired — M11
(`run_timing`) planned ready while `sta` was absent. This module
plans against a `report_capabilities` operations mapping instead:
a stage is ready only when every tool entrypoint it needs reports
ready, and a blocked stage carries which entrypoints block it plus
their reason, missing items, and remedy.
"""

from .stages import _SCRIPTED, STAGES

_FALLBACK_REMEDY = "Provision the missing tooling (see docs/provision-plan.md)."


def plan_from_capabilities(flow, operations):
    """Plan a flow against a capabilities report's operations mapping.

    Scripted entrypoints need no backend. A stage whose tool
    entrypoints all read ready in the report is ready; otherwise it
    stays required-but-blocked (never silently dropped) and names
    the blocking entrypoints with their report reason, missing
    items, and remedy. Entrypoints with no report row block loudly
    with a no-report reason instead of a tool-blind ready.

    Args:
        flow: Flow inventory to plan (digital/analog/photonic/mixed).
        operations: Per-operation readiness mapping as reported by
            `report_capabilities` (operation -> readiness plus
            reason/missing/remedy detail).

    Returns:
        Stage list with per-stage readiness (ready/blocked);
            blocked stages also carry blocked_by, reason, missing,
            and remedy keys.

    Raises:
        ValueError: Unknown flow name.
    """
    try:
        stages = STAGES[flow]
    except KeyError:
        raise ValueError(f"Unknown flow: {flow}.") from None
    planned = []
    for stage in stages:
        needed = [e for e in stage["entrypoints"] if e not in _SCRIPTED]
        blocking = [
            e for e in needed
            if operations.get(e, {}).get("readiness") != "ready"
        ]
        if not blocking:
            planned.append({**stage, "readiness": "ready"})
            continue
        reasons, missing, remedies = [], [], []
        for entry in blocking:
            row = operations.get(entry, {})
            if entry not in operations:
                reasons.append(
                    f"{entry}: no capability report on this machine."
                )
                missing.append(entry)
                continue
            reasons.append(f"{entry}: {row.get('reason', 'not ready.')}")
            missing.extend(row.get("missing") or [])
            remedy = row.get("remedy")
            if remedy and remedy not in remedies:
                remedies.append(remedy)
        planned.append({
            **stage,
            "readiness": "blocked",
            "blocked_by": blocking,
            "reason": "; ".join(reasons),
            "missing": sorted(set(missing)),
            "remedy": " ".join(remedies) if remedies else _FALLBACK_REMEDY,
        })
    return planned
