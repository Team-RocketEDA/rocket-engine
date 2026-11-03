"""Canvas compiler: canvas to SDC, decks, fragments."""

import math

from .schema import KNOWN_METRICS
from .validate import CanvasError


def _targets(doc):
    """Return the target list of a canvas mapping.

    Args:
        doc: Canvas mapping with a targets list.

    Returns:
        Target list (empty when absent).
    """
    targets = doc.get("targets") or []
    return targets if isinstance(targets, list) else []


def _limit_mhz(target):
    """Convert one clock target limit to MHz.

    Args:
        target: Target mapping with a limit value/unit.

    Returns:
        Frequency in MHz.
    """
    limit = target.get("limit") or {}
    value = float(limit.get("value", 0))
    unit = limit.get("unit", "MHz")
    scale = {"Hz": 1e-6, "kHz": 1e-3, "MHz": 1.0, "GHz": 1e3}
    return value * scale.get(unit, 1.0)


def compile_sdc(doc):
    """Compile a digital canvas to SDC tool-native text.

    Args:
        doc: Validated canvas mapping with clock targets.

    Returns:
        SDC text with create_clock plus operating conditions.

    Raises:
        CanvasError: bad_target when no clock target exists.
    """
    clocks = [t for t in _targets(doc)
              if t.get("metric") in ("clock.frequency", "filter.cutoff")]
    if not clocks:
        raise CanvasError("bad_target",
                          "canvas.targets: no clock target for SDC.")
    mhz = _limit_mhz(clocks[0])
    if not math.isfinite(mhz) or mhz <= 0:
        raise CanvasError("bad_limit",
                          "canvas.targets: clock limit must be positive.")
    period_ns = 1000.0 / mhz
    lines = [f"create_clock -name clk -period {period_ns:.4f} "
             "[get_ports clk]",
             "set_clock_uncertainty 0.050 [get_clocks clk]",
             "set_input_delay 0.200 -clock clk [all_inputs]",
             "set_output_delay 0.200 -clock clk [all_outputs]"]
    return "\n".join(lines) + "\n"


def compile_spice_bounds(doc):
    """Compile an analog canvas to run_spice measurement bounds.

    Args:
        doc: Validated canvas mapping with analog targets.

    Returns:
        Bounds mapping of metric to {min, max} floats.
    """
    bounds = {}
    for target in _targets(doc):
        metric = target.get("metric")
        if metric in ("clock.frequency", "filter.cutoff"):
            continue
        operator = target.get("operator", "ge")
        value = float((target.get("limit") or {}).get("value", 0))
        entry = bounds.setdefault(metric, {})
        if operator in ("ge", "gt", "eq"):
            entry["min"] = value
        if operator in ("le", "lt", "eq"):
            entry["max"] = value
    return bounds


def compile_librelane(doc):
    """Compile canvas librelane knobs to a config fragment.

    Args:
        doc: Canvas mapping with tools.librelane knobs.

    Returns:
        Fragment mapping with density, effort, corners.
    """
    knobs = (doc.get("tools") or {}).get("librelane") or {}
    frag = {}
    if knobs.get("density") is not None:
        frag["density"] = float(knobs["density"])
    if knobs.get("effort") is not None:
        frag["effort"] = str(knobs["effort"])
    if knobs.get("corners") is not None:
        frag["corners"] = list(knobs["corners"])
    return frag
