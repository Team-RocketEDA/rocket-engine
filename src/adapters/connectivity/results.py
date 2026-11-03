"""Connectivity v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_connectivity``/``run_erc`` parse shape
(``violations[]`` with rule, severity, message, and net plus a
measurements mapping with the net inventory and counts) onto a
typed findings table, a nets table, bound views, count
measurements, and findings. Pure function of the parsed output:
no I/O, no tool calls, deterministic ids derived from the run
id.
"""

TASK = "run_connectivity"

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
    """Normalize one connectivity parse output to a v1 ResultBundle.

    Finding rows become a table dataset (rule, severity, message,
    net) and the net inventory a second table; net and instance
    counts ride PASS measurements. Every violation also becomes a
    finding with a capped message.

    Args:
        parsed: v0 parse mapping with ``violations[]`` and a
            measurements mapping.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    violations = parsed.get("violations") or []
    measured = parsed.get("measurements") or {}
    nets = measured.get("nets") or []
    findings_id = f"{run_id}:dataset:findings"
    nets_id = f"{run_id}:dataset:nets"
    datasets = [
        {
            "id": findings_id,
            "kind": "table",
            "row_count": len(violations),
            "columns": [
                {
                    "id": f"{findings_id}:rule",
                    "name": "rule",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [v.get("rule", "") for v in violations],
                },
                {
                    "id": f"{findings_id}:severity",
                    "name": "severity",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [v.get("severity", "") for v in violations],
                },
                {
                    "id": f"{findings_id}:message",
                    "name": "message",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_cap(v.get("message", "")) for v in violations],
                },
                {
                    "id": f"{findings_id}:net",
                    "name": "net",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [str(v.get("net") or "") for v in violations],
                },
            ],
            "conditions": [],
        },
        {
            "id": nets_id,
            "kind": "table",
            "row_count": len(nets),
            "columns": [
                {
                    "id": f"{nets_id}:net",
                    "name": "net",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [str(net) for net in nets],
                },
            ],
            "conditions": [],
        },
    ]
    views = [
        {
            "id": f"{run_id}:view:findings",
            "kind": "table",
            "dataset_id": findings_id,
            "name": "connectivity findings",
        },
        {
            "id": f"{run_id}:view:nets",
            "kind": "table",
            "dataset_id": nets_id,
            "name": "net inventory",
        },
    ]
    measurements = []
    for name in ("net_count", "instance_count"):
        value = measured.get(name)
        if value is None:
            continue
        measurements.append(
            {
                "name": name,
                "value": _quantity(value, "1"),
                "status": "PASS",
            }
        )
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "connectivity"),
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
