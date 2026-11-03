"""Ngspice v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_spice`` parse shape (``measurements[]`` with value,
unit, target, margin, and pass/fail status plus ``sim_fail``
violations) onto typed v1 datasets, views, measurements, and
findings. Pure function of the parsed output: no I/O, no tool
calls, deterministic ids derived from the run id.
"""

TASK = "run_spice"

_DIAG_CAP = 240

_SEVERITY = {"error": "error", "warning": "warning"}


def _cap(text):
    """Cap one diagnostic string at the bundle prose limit.

    Args:
        text: Raw diagnostic text, possibly unbounded tool prose.

    Returns:
        The text unchanged when short, else truncated with an
            ellipsis marker.
    """
    text = text if isinstance(text, str) else str(text)
    if len(text) <= _DIAG_CAP:
        return text
    return text[: _DIAG_CAP - 3] + "..."


def _quantity(value, unit):
    """Build one v1 Quantity, mapping unitless to dimensionless.

    Args:
        value: Numeric value.
        unit: Unit string, possibly empty for unitless measures.

    Returns:
        Quantity mapping with an explicit unit.
    """
    return {"value": float(value), "unit": unit if unit else "1"}


def _limit(item):
    """Pick the binding target bound for one measurement.

    Args:
        item: v0 measurement with a ``target`` min/max mapping.

    Returns:
        The bound closest to the measured value (the margin
            binding bound), or None when the target is empty.
    """
    target = item.get("target") or {}
    scored = []
    if target.get("min") is not None:
        scored.append((float(item["value"]) - float(target["min"]),
                        float(target["min"])))
    if target.get("max") is not None:
        scored.append((float(target["max"]) - float(item["value"]),
                        float(target["max"])))
    if not scored:
        return None
    return min(scored)[1]


def _provenance(project_id, run_id, tools, provenance):
    """Build ResultProvenance, defaulting to a placeholder closure.

    Args:
        project_id: Project the run belongs to.
        run_id: Run the bundle describes.
        tools: Tool ingredient mappings (id, version, digest?).
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Provenance mapping valid against the v1 schema.
    """
    if provenance is not None:
        return provenance
    ref = {"scope": "project", "id": project_id, "revision": "r1"}
    return {
        "snapshot": dict(ref),
        "input_lock": dict(ref),
        "closure_hash": "0" * 64,
        "tools": [
            {
                "id": item["id"],
                "version": item.get("version", ""),
                "digest": item.get("digest", "0" * 64),
            }
            for item in tools
        ],
        "parents": [],
    }


def normalize(parsed, *, run_id, project_id="project", target=None,
              tools=(), provenance=None):
    """Normalize one ngspice parse output to a v1 ResultBundle.

    Measurement rows become a table dataset (names, values,
    margins, statuses; canonical units live on ``measurements[]``)
    plus a bound table view; violations become findings with
    capped messages. PASS measurements keep value, target,
    margin, and status.

    Args:
        parsed: v0 parse mapping with ``violations[]`` and
            ``measurements[]``.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    measurements_in = parsed.get("measurements") or []
    violations = parsed.get("violations") or []
    table_id = f"{run_id}:dataset:measurements"
    columns = [
        {
            "id": f"{table_id}:name",
            "name": "name",
            "dtype": "utf8",
            "unit": "1",
            "data": [item["name"] for item in measurements_in],
        },
        {
            "id": f"{table_id}:value",
            "name": "value",
            "dtype": "float64",
            "unit": "1",
            "data": [float(item["value"]) for item in measurements_in],
        },
        {
            "id": f"{table_id}:margin",
            "name": "margin",
            "dtype": "float64",
            "unit": "1",
            "data": [float(item["margin"]) for item in measurements_in],
        },
        {
            "id": f"{table_id}:status",
            "name": "status",
            "dtype": "utf8",
            "unit": "1",
            "data": [item["status"] for item in measurements_in],
        },
    ]
    datasets = [
        {
            "id": table_id,
            "kind": "table",
            "row_count": len(measurements_in),
            "columns": columns,
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:measurements",
            "kind": "table",
            "dataset_id": table_id,
            "name": "measurements",
        }
    ]
    measurements = []
    for item in measurements_in:
        entry = {
            "name": item["name"],
            "value": _quantity(item["value"], item.get("unit", "")),
            "margin": _quantity(item["margin"], item.get("unit", "")),
            "status": "PASS" if item["status"] == "pass" else "FAIL",
        }
        bound = _limit(item)
        if bound is not None:
            entry["limit"] = _quantity(bound, item.get("unit", ""))
        measurements.append(entry)
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "sim_fail"),
            "message": _cap(v.get("message", "")),
        }
        for index, v in enumerate(violations)
    ]
    converged = not any(v.get("rule") == "sim_fail" for v in violations)
    return {
        "schema": "rocketeda/results/v1",
        "ref": {"scope": "project", "id": run_id, "revision": "r1"},
        "run_id": run_id,
        "task": TASK,
        "target": dict(target)
        if target is not None
        else {"project_id": project_id, "kind": "project"},
        "state": "complete",
        "freshness": "current",
        "convergence": "converged" if converged else "not_converged",
        "provenance": _provenance(project_id, run_id, tools, provenance),
        "datasets": datasets,
        "views": views,
        "measurements": measurements,
        "findings": findings,
        "artifacts": [],
        "logs": [],
        "gaps": [],
    }
