"""Synth-yosys v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_synth`` parse shape (per-family ``cells`` counts,
cell/wire/area measurements, and synth_error plus warning
violations) onto a cell-family table dataset, bound views,
measurements, and findings. Pure function of the parsed output:
no I/O, no tool calls, deterministic ids derived from the run
id. Canonical units live on ``measurements[]``.
"""

TASK = "run_synth"

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
    """Normalize one synth parse output to a v1 ResultBundle.

    Per-family cell counts become a table dataset plus a bound
    table view; cell/wire/area counts become measurements with a
    PASS status; violations become findings with capped messages.

    Args:
        parsed: v0 parse mapping with ``cells``, ``cell_count``,
            ``wire_count``, ``area``, ``measurements[]``, and
            ``violations[]``.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    cells = parsed.get("cells") or {}
    families = sorted(cells)
    violations = parsed.get("violations") or []
    table_id = f"{run_id}:dataset:cells"
    datasets = [
        {
            "id": table_id,
            "kind": "table",
            "row_count": len(families),
            "columns": [
                {
                    "id": f"{table_id}:family",
                    "name": "family",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": list(families),
                },
                {
                    "id": f"{table_id}:count",
                    "name": "count",
                    "dtype": "float64",
                    "unit": "1",
                    "data": [float(cells[f]) for f in families],
                },
            ],
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:cells",
            "kind": "table",
            "dataset_id": table_id,
            "name": "cell counts",
        }
    ]
    measurements = []
    for item in parsed.get("measurements") or []:
        entry = {
            "name": item["name"],
            "value": _quantity(item["value"], item.get("unit", "")),
            "status": "PASS",
        }
        measurements.append(entry)
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "synth_error"),
            "message": _cap(v.get("message", "")),
        }
        for index, v in enumerate(violations)
    ]
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
        "convergence": "not_applicable",
        "provenance": _provenance(project_id, run_id, tools, provenance),
        "datasets": datasets,
        "views": views,
        "measurements": measurements,
        "findings": findings,
        "artifacts": [],
        "logs": [],
        "gaps": [],
    }
