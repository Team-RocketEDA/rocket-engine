"""Technology-profile bindings with explicit capability states.

Bindings map project layer identities to process purposes and
report each mapping as supported, missing, or incompatible. A
missing binding never reinterprets geometry: drawing and saving
keep working and only process operations report the gap.
"""

import copy

STATES = ("supported", "missing", "incompatible")


def bind_layers(catalog, profile_layers, source="profile",
                version="unknown"):
    """Bind catalog layers against a profile vocabulary.

    Args:
        catalog: LayerCatalog to bind.
        profile_layers: Mapping of profile name to layer-name
            lists, or a plain list of known layer names.
        source: Provenance label for the profile source.
        version: Profile version pinned into the report.

    Returns:
        Binding report with profile pin, catalog revision,
            and one entry per layer (state, purpose, source).
    """
    if isinstance(profile_layers, dict):
        profile = catalog.profile or {}
        known = profile_layers.get(profile.get("name", ""), [])
    else:
        known = list(profile_layers)
    entries = []
    for layer in catalog.list_layers():
        if layer["name"] in known:
            state = "supported"
        elif layer["name"].startswith("custom"):
            state = "missing"
        else:
            state = "missing"
        entries.append({
            "capability": state,
            "layer": layer["lid"],
            "name": layer["name"],
            "purpose": layer["purpose"],
            "source": source,
            "state": state,
            "version": version,
        })
    profile = catalog.profile or {}
    return {
        "catalog_revision": catalog.revision,
        "entries": entries,
        "profile": profile.get("name", "unresolved"),
        "profile_version": profile.get("version", version),
    }


def check_operation(report, layer_lid, operation):
    """Check whether one process operation may consume a layer.

    Args:
        report: Binding report from bind_layers.
        layer_lid: Stable layer id the operation needs.
        operation: Process operation name (export_gds, drc,
            extraction, or a recipe step).

    Returns:
        Verdict mapping with state (supported, unsupported,
            or incomplete), layer, operation, and reason. Draw
        and save paths ignore this verdict; only the named
        process operation is gated by it.

    Raises:
        ValueError: For a layer with no binding entry.
    """
    for entry in report["entries"]:
        if entry["layer"] == layer_lid:
            if entry["state"] == "supported":
                return {
                    "layer": layer_lid,
                    "operation": operation,
                    "reason": "Binding covers the operation.",
                    "state": "supported",
                }
            return {
                "layer": layer_lid,
                "operation": operation,
                "reason": (
                    f"No {operation} mapping for layer "
                    f"{entry['name']!r}; geometry is intact."
                ),
                "state": "unsupported",
            }
    raise ValueError(f"No binding entry for layer: {layer_lid!r}.")


def binding_for(report, layer_lid):
    """Return one layer entry from a binding report.

    Args:
        report: Binding report from bind_layers.
        layer_lid: Stable layer id to look up.

    Returns:
        Deep copy of the binding entry.

    Raises:
        ValueError: For a layer with no binding entry.
    """
    for entry in report["entries"]:
        if entry["layer"] == layer_lid:
            return copy.deepcopy(entry)
    raise ValueError(f"No binding entry for layer: {layer_lid!r}.")
