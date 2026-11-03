"""Magic-extraction v1 normalizer: v0 parse output to a ResultBundle.

Maps the ``run_extraction`` parse shape (device inventory with
name, nets, class, and w/l plus the device count) onto a typed
devices table, a bound view, a device-count measurement, and no
findings on clean extraction. Pure function of the parsed
output: no I/O, no tool calls, deterministic ids derived from
the run id.
"""

TASK = "run_extraction"

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


def _number(value):
    """Render one optional device dimension as table text.

    Args:
        value: Numeric dimension, or None when the device class
            carries none.

    Returns:
        Numeric text, or an empty string for a missing dimension.
    """
    if value is None:
        return ""
    return str(float(value))


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
    """Normalize one magic-extraction parse output to a ResultBundle.

    Device rows become a table dataset (name, class, nets, w, l)
    plus a bound table view; the device count rides a PASS
    measurement; violations (never present on clean extraction)
    become findings with capped messages.

    Args:
        parsed: v0 parse mapping with ``devices[]``,
            ``device_count``, and ``violations``.
        run_id: Run the bundle describes (anchors all ids).
        project_id: Project the run belongs to.
        target: v1 target mapping; project kind by default.
        tools: Tool ingredient mappings for provenance.
        provenance: Full provenance mapping when the caller has
            one; a deterministic placeholder otherwise.

    Returns:
        Schema-valid ResultBundle mapping.
    """
    devices = parsed.get("devices") or []
    violations = parsed.get("violations") or []
    table_id = f"{run_id}:dataset:devices"
    datasets = [
        {
            "id": table_id,
            "kind": "table",
            "row_count": len(devices),
            "columns": [
                {
                    "id": f"{table_id}:name",
                    "name": "name",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [d.get("name", "") for d in devices],
                },
                {
                    "id": f"{table_id}:class",
                    "name": "class",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [d.get("class", "") for d in devices],
                },
                {
                    "id": f"{table_id}:nets",
                    "name": "nets",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [
                        ",".join(d.get("nets") or []) for d in devices
                    ],
                },
                {
                    "id": f"{table_id}:w",
                    "name": "w",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_number(d.get("w")) for d in devices],
                },
                {
                    "id": f"{table_id}:l",
                    "name": "l",
                    "dtype": "utf8",
                    "unit": "1",
                    "data": [_number(d.get("l")) for d in devices],
                },
            ],
            "conditions": [],
        }
    ]
    views = [
        {
            "id": f"{run_id}:view:devices",
            "kind": "table",
            "dataset_id": table_id,
            "name": "extracted devices",
        }
    ]
    measurements = [
        {
            "name": "device_count",
            "value": _quantity(parsed.get("device_count", 0), "1"),
            "status": "PASS",
        }
    ]
    findings = [
        {
            "id": f"{run_id}:finding:{index}",
            "severity": _SEVERITY.get(v.get("severity"), "info"),
            "code": v.get("rule", "extraction"),
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
