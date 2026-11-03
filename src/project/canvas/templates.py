"""Per-PDK canvas templates plus the creation generator."""

_SUPPORTED = ("sky130A", "sky130GF", "gf180", "ihp", "asap7", "lxt",
              "cspdk", "ubc", "vtt")


def supported_pdks():
    """List PDK ids with a shipped canvas template.

    Returns:
        Sorted PDK ids the generator accepts.
    """
    return sorted(_SUPPORTED)


def generate(pdk_id):
    """Generate a filled canvas document for one PDK.

    Args:
        pdk_id: PDK id the template is generated for.

    Returns:
        Canvas mapping that validates clean via validate_canvas.

    Raises:
        ValueError: For an unsupported PDK id.
    """
    if pdk_id not in _SUPPORTED:
        raise ValueError(f"Unsupported PDK for canvas template: {pdk_id!r}.")
    return {
        "schema": "rocketeda/canvas/v1",
        "pdks": [{"scope": "pdk", "id": "sky130A"
                  if pdk_id in ("sky130A", "sky130GF") else pdk_id,
                  "revision": "pinned-rev"}],
        "targets": [
            {"metric": "clock.frequency", "operator": "ge",
             "limit": {"value": 100, "unit": "MHz"}},
            {"metric": "drc.violations", "operator": "le",
             "limit": {"value": 0, "unit": "count"}},
        ],
        "tools": {"yosys": {"flatten": True},
                  "ngspice": {"reltol": 0.001},
                  "librelane": {"density": 0.6, "effort": "standard",
                                "corners": ["tt"]}},
        "hdl": {"language": "verilog", "top": "top"},
    }
