"""HDL-sim v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_hdl_test`` parse shape (``violations[]`` with
rule, severity, message, file/line, and optional sim_time) onto a
typed violations table, bound views, and findings. Pure function
of the parsed output: no I/O, no tool calls, deterministic ids
derived from the run id. A clean sim yields an empty table and no
findings.
"""

TASK = "run_hdl_test"

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


def _location(violation):
    """Render one file:line location string for a violation.

    Args:
        violation: v0 violation with optional file and line.

    Returns:
        Location text, or an empty string when unlocated.
    """
    file = violation.get("file") or ""
    line = violation.get("line")
    if file and line is not None:
        return f"{file}:{line}"
    return file or ""


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
    """Normalize one hdl-sim parse output to a v1 ResultBundle.

    Violation rows become a table dataset (rule, severity,
    message, location) plus a bound table view; every violation
    also becomes a finding with a capped message.

    Args:
        parsed: v0 parse mapping with ``violations[]``.
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
    table_id = f"{run_id}:dataset:violations"
    datasets = [
        {
            "id": table_id,
            "kind": "table",
            "row_count": len(violations),
            "columns": [
                {
                    "id": f"{table_id}:rule",
                    "name": "rule",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [v.get("rule", "") for v in violations],
                },
                {
                    "id": f"{table_id}:severity",
                    "name": "severity",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [v.get("severity", "") for v in violations],
                },
                {
                    "id": f"{table_id}:message",
                    "name": "message",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_cap(v.get("message", "")) for v in violations],
                },
                {
                    "id": f"{table_id}:location",
                    "name": "location",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_location(v) for v in violations],
                },
            ],
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:violations",
            "kind": "table",
            "dataset_id": table_id,
            "name": "violations",
        }
    ]
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "sim"),
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
        "measurements": [],
        "findings": findings,
        "artifacts": [],
        "logs": [],
        "gaps": [],
    }
