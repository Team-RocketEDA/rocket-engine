"""Formal-sby v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_formal`` parse shape (a measurements mapping with
mode, depth, scope, sby_status, property counts, failures, and
counterexamples, plus violations) onto a typed verdict table,
bound views, numeric measurements, and findings. Pure function of
the parsed output: no I/O, no tool calls, deterministic ids
derived from the run id. A FAIL always carries error findings;
scope text is preserved as table data, never prose.
"""

TASK = "run_formal"

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
    """Normalize one formal parse output to a v1 ResultBundle.

    Scope, sby status, and per-failure witnesses become a
    verdict table dataset plus a bound table view; property,
    assumption, and depth counts become measurements whose
    status mirrors the proof verdict; violations become
    findings with capped messages.

    Args:
        parsed: v0 parse mapping with ``measurements`` (a scope
            mapping) and ``violations[]``.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    measures = parsed.get("measurements") or {}
    violations = parsed.get("violations") or []
    scope = measures.get("scope", "unknown")
    sby_status = measures.get("sby_status", "unknown")
    verdict = "PASS" if sby_status == "PASS" and not violations else "FAIL"
    rows = [("scope", str(scope)), ("sby_status", str(sby_status))]
    for failure in measures.get("failures") or []:
        rows.append(
            (f"failure:{failure.get('property', '?')}",
             str(failure.get("kind", "assert")))
        )
    table_id = f"{run_id}:dataset:verdict"
    datasets = [
        {
            "id": table_id,
            "kind": "table",
            "row_count": len(rows),
            "columns": [
                {
                    "id": f"{table_id}:aspect",
                    "name": "aspect",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [aspect for aspect, _ in rows],
                },
                {
                    "id": f"{table_id}:value",
                    "name": "value",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [value for _, value in rows],
                },
            ],
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:verdict",
            "kind": "table",
            "dataset_id": table_id,
            "name": "verdict",
        }
    ]
    measurements = []
    for name in ("properties", "assumptions", "depth"):
        if measures.get(name) is not None:
            measurements.append(
                {
                    "name": name,
                    "value": _quantity(measures[name], "1"),
                    "status": verdict,
                }
            )
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "assert_fail"),
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
