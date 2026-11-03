"""Digital-flow v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_digital_flow`` parse shape (per-stage gate table
with id/label/status/evidence plus top-level gds/netlist/spef
paths, drc_total, and lvs_match) onto a typed stages table, a
deliverables table, bound views, measurements, and findings.
Pure function of the parsed output: no I/O, no tool calls,
deterministic ids derived from the run id. File paths ride the
deliverables table as evidence; no bundle artifact is fabricated
without a recorded digest.
"""

TASK = "run_digital_flow"

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
    """Normalize one digital-flow parse output to a v1 ResultBundle.

    Stage gates become a table dataset (id, label, status) plus
    a deliverables table (gds/netlist/spef paths); drc_total and
    lvs_match ride measurements with PASS/FAIL status; failed
    gates become findings with capped messages.

    Args:
        parsed: v0 parse mapping with ``stages[]``,
            ``violations[]``, deliverable paths, ``drc_total``,
            and ``lvs_match``.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    stages = parsed.get("stages") or []
    violations = parsed.get("violations") or []
    stages_id = f"{run_id}:dataset:stages"
    files_id = f"{run_id}:dataset:deliverables"
    deliverables = [
        (name, parsed.get(name))
        for name in ("gds", "netlist", "spef")
        if parsed.get(name)
    ]
    datasets = [
        {
            "id": stages_id,
            "kind": "table",
            "row_count": len(stages),
            "columns": [
                {
                    "id": f"{stages_id}:id",
                    "name": "id",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [s.get("id", "") for s in stages],
                },
                {
                    "id": f"{stages_id}:label",
                    "name": "label",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [s.get("label", "") for s in stages],
                },
                {
                    "id": f"{stages_id}:status",
                    "name": "status",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [s.get("status", "") for s in stages],
                },
            ],
            "conditions": [],
        },
        {
            "id": files_id,
            "kind": "table",
            "row_count": len(deliverables),
            "columns": [
                {
                    "id": f"{files_id}:artifact",
                    "name": "artifact",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [name for name, _ in deliverables],
                },
                {
                    "id": f"{files_id}:path",
                    "name": "path",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [str(path) for _, path in deliverables],
                },
            ],
            "conditions": [],
        },
    ]
    views = [
        {
            "id": f"{run_id}:view:stages",
            "kind": "table",
            "dataset_id": stages_id,
            "name": "stage gates",
        },
        {
            "id": f"{run_id}:view:deliverables",
            "kind": "table",
            "dataset_id": files_id,
            "name": "deliverables",
        },
    ]
    measurements = []
    drc_total = parsed.get("drc_total")
    if drc_total is not None:
        measurements.append(
            {
                "name": "drc_total",
                "value": _quantity(drc_total, "1"),
                "status": "PASS" if drc_total == 0 else "FAIL",
            }
        )
    if parsed.get("lvs_match") is not None:
        match = bool(parsed.get("lvs_match"))
        measurements.append(
            {
                "name": "lvs_match",
                "value": _quantity(1.0 if match else 0.0, "1"),
                "status": "PASS" if match else "FAIL",
            }
        )
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "digital_flow_gate"),
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
