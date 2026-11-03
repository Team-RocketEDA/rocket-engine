"""Magic DRC v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_drc`` magic parse shape (``violations[]`` with
rule, lambda-unit area, and bbox) onto a typed rule table, a
bound view, and findings. Pure function of the parsed output: no
I/O, no tool calls, deterministic ids derived from the run id.
Magic reports no severity or message per box (see ESCAPE-HARDEN),
so every box fails as an error finding naming its rule.
"""

TASK = "run_drc"

_DIAG_CAP = 240


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


def _bbox_text(bbox):
    """Render one lambda-unit bbox as comma-joined coordinates.

    Args:
        bbox: Coordinate list from the v0 violation, if any.

    Returns:
        Comma-joined coordinate text, or an empty string when the
            violation carries no bbox.
    """
    if not bbox:
        return ""
    return ",".join(str(c) for c in bbox)


def _message(violation):
    """Render one violation message from its rule, area, and bbox.

    Args:
        violation: v0 violation with rule, area, and bbox.

    Returns:
        Capped message naming the rule and its geometry.
    """
    rule = violation.get("rule", "drc")
    area = violation.get("area")
    bbox = _bbox_text(violation.get("bbox"))
    text = f"{rule} at [{bbox}] area {area}"
    return _cap(text)


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
    """Normalize one magic DRC parse output to a v1 ResultBundle.

    Rule boxes become a table dataset (rule, area, bbox) plus a
    bound table view; every box also becomes an error finding
    naming its rule.

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
                    "id": f"{table_id}:area",
                    "name": "area",
                    "dtype": "float64",
                    "unit": "1",
                    "data": [float(v.get("area", 0)) for v in violations],
                },
                {
                    "id": f"{table_id}:bbox",
                    "name": "bbox",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_bbox_text(v.get("bbox")) for v in violations],
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
            "name": "drc violations",
        }
    ]
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": "error",
            "code": v.get("rule", "drc") or "drc",
            "message": _message(v),
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
