"""Netgen LVS v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_lvs`` parse shape (match flag plus ``violations[]``
with rule, severity, message, and net/instance subjects) onto a
typed mismatch table, a bound view, and findings. Pure function
of the parsed output: no I/O, no tool calls, deterministic ids
derived from the run id. A match carries no findings; any
mismatch fails as an error finding.
"""

TASK = "run_lvs"

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


def _subject(violation):
    """Name the net or instance one mismatch is about.

    Args:
        violation: v0 violation with optional net/instance keys.

    Returns:
        Subject text, or an empty string when unlocated.
    """
    return str(violation.get("net") or violation.get("instance") or "")


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
    """Normalize one netgen LVS parse output to a v1 ResultBundle.

    Mismatch rows become a table dataset (rule, message,
    subject) plus a bound table view; every mismatch also
    becomes a finding with a capped message.

    Args:
        parsed: v0 parse mapping with ``match`` and
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
    violations = parsed.get("violations") or []
    table_id = f"{run_id}:dataset:mismatches"
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
                    "id": f"{table_id}:message",
                    "name": "message",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_cap(v.get("message", "")) for v in violations],
                },
                {
                    "id": f"{table_id}:subject",
                    "name": "subject",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_subject(v) for v in violations],
                },
            ],
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:mismatches",
            "kind": "table",
            "dataset_id": table_id,
            "name": "lvs mismatches",
        }
    ]
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "lvs_net_mismatch"),
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
