"""Canvas registry tables: metrics, tool knobs, UI schema descriptor.

Every table here is evidence-backed: metric names and units come
from the shipped demo canvases (`waveform-generator/canvas.toml`,
`photonic_matmul/canvas.toml`) and the fuel constraint checks the
COMPILE slice migrates 1:1 (`rocket_fuel/examples/*/`). Adding a
metric or knob is a table edit here plus a test — never a silent
accept.
"""

#: Metric name -> (dimension, allowed units). Flat fuel names ride
#: alongside dotted canvas names so the migration probe reads 1:1.
KNOWN_METRICS = {
    "clock.frequency": ("frequency", ("Hz", "kHz", "MHz", "GHz")),
    "filter.cutoff": ("frequency", ("Hz", "kHz", "MHz", "GHz")),
    "ugbw_mhz": ("frequency", ("Hz", "kHz", "MHz", "GHz")),
    "supply.voltage": ("voltage", ("V", "mV")),
    "supply.current": ("current", ("A", "mA", "uA")),
    "power.dissipation": ("power", ("W", "mW", "uW")),
    "dc_gain_db": ("gain", ("dB",)),
    "gain.dc": ("gain", ("dB",)),
    "phase_margin_deg": ("phase", ("deg",)),
    "phase.margin": ("phase", ("deg",)),
    "dac.resolution": ("resolution", ("bit",)),
    "dac.dnl": ("mismatch", ("LSB",)),
    "dac.inl": ("mismatch", ("LSB",)),
    "sim.temperature": ("temperature", ("C", "K")),
    "drc.violations": ("count", ("count",)),
    "drc_violations": ("count", ("count",)),
}

#: Every unit any metric or quantity accepts (union for quantity
#: checks on spice knobs such as abstol/vntol/temperature).
KNOWN_UNITS = sorted(
    {unit for _, units in KNOWN_METRICS.values() for unit in units}
    | {"Ohm", "kOhm", "F", "pF", "fF", "s", "ms", "us", "ns", "ps"}
)

#: Comparison operators a target may state.
OPERATORS = ("lt", "le", "eq", "ge", "gt")

#: Authored HDL dialects, one per canvas (frozen contract enum).
HDL_LANGUAGES = ("verilog", "systemverilog", "vhdl", "amaranth")

#: Reference scopes (frozen contract PinnedRef/WorkingRef).
REF_SCOPES = ("project", "library", "pdk", "package", "engine")

#: Tool name -> knob name -> knob spec. Spec kinds: ref (a Pinned
#: or Working Ref), text (delegated file path or inline text),
#: hash (pinned sha256), number (plain float with optional
#: bounds), enum, string_list, boolean, quantity (value + unit).
TOOL_KNOBS = {
    "librelane": {
        "profile": {"kind": "ref"},
        "configuration": {"kind": "text"},
        "sha256": {"kind": "hash"},
        "density": {"kind": "number", "min_exclusive": 0, "max": 1},
        "effort": {"kind": "enum", "values": ("low", "standard", "high")},
        "corners": {"kind": "string_list"},
    },
    "ngspice": {
        "profile": {"kind": "ref"},
        "configuration": {"kind": "text"},
        "sha256": {"kind": "hash"},
        "temperature": {"kind": "quantity", "units": ("C", "K")},
        "reltol": {"kind": "number", "min_exclusive": 0},
        "abstol": {"kind": "quantity"},
        "vntol": {"kind": "quantity"},
        "method": {"kind": "enum", "values": ("trap", "gear")},
        "max_order": {"kind": "integer", "min": 1, "max": 6},
    },
    "xyce": {
        "profile": {"kind": "ref"},
        "configuration": {"kind": "text"},
        "sha256": {"kind": "hash"},
        "temperature": {"kind": "quantity", "units": ("C", "K")},
        "reltol": {"kind": "number", "min_exclusive": 0},
        "abstol": {"kind": "quantity"},
        "vntol": {"kind": "quantity"},
        "method": {"kind": "enum", "values": ("trap", "gear")},
        "max_order": {"kind": "integer", "min": 1, "max": 6},
    },
    "yosys": {
        "profile": {"kind": "ref"},
        "configuration": {"kind": "text"},
        "sha256": {"kind": "hash"},
        "flatten": {"kind": "boolean"},
        "optimization": {
            "kind": "enum", "values": ("area", "delay", "balanced")
        },
    },
    "openroad": {
        "profile": {"kind": "ref"},
        "configuration": {"kind": "text"},
        "sha256": {"kind": "hash"},
        "density": {"kind": "number", "min_exclusive": 0, "max": 1},
        "effort": {"kind": "enum", "values": ("low", "standard", "high")},
    },
}

#: Knobs any unlisted tool accepts (the generic ToolSetting: a
#: profile plus an optional delegated configuration).
GENERIC_TOOL_KNOBS = ("profile", "configuration", "sha256")

_CANVAS_VERSION = "rocketeda/canvas/v1"


def ui_schema():
    """Describe every canvas section for rendering and editing.

    The UI renders and edits every section from this descriptor
    alone — no section, metric, or knob exists that is not
    listed here.

    Returns:
        Descriptor with the canvas version and one entry per
            section (name, description, fields or item shape).
    """
    metric_field = {
        "name": "metric",
        "type": "enum",
        "required": True,
        "values": sorted(KNOWN_METRICS),
    }
    sections = [
        {
            "name": "schema",
            "description": "Canvas version pin.",
            "fields": [
                {
                    "name": "schema",
                    "type": "const",
                    "required": True,
                    "values": [_CANVAS_VERSION],
                }
            ],
        },
        {
            "name": "hdl",
            "description": "One authored HDL dialect per canvas; "
            "omit the section when there is no authored digital "
            "content (photonic-only).",
            "fields": [
                {
                    "name": "language",
                    "type": "enum",
                    "required": True,
                    "values": list(HDL_LANGUAGES),
                },
                {
                    "name": "top",
                    "type": "string",
                    "required": False,
                },
            ],
        },
        {
            "name": "technology",
            "description": "Sealed technology reference (PDK pin).",
            "fields": [
                {"name": "scope", "type": "enum", "required": True,
                 "values": list(REF_SCOPES)},
                {"name": "id", "type": "string", "required": True},
                {"name": "revision", "type": "string", "required": True},
            ],
        },
        {
            "name": "pdks",
            "description": "Pinned PDK references the intent builds on.",
            "item": {
                "type": "ref",
                "fields": [
                    {"name": "scope", "type": "enum",
                     "required": True, "values": list(REF_SCOPES)},
                    {"name": "id", "type": "string", "required": True},
                    {"name": "revision", "type": "string",
                     "required": True},
                ],
            },
        },
        {
            "name": "targets",
            "description": "Design targets: one metric, one "
            "operator, one limit with units.",
            "item": {
                "type": "target",
                "fields": [
                    metric_field,
                    {
                        "name": "operator",
                        "type": "enum",
                        "required": True,
                        "values": list(OPERATORS),
                    },
                    {
                        "name": "limit",
                        "type": "quantity",
                        "required": True,
                    },
                    {
                        "name": "required",
                        "type": "boolean",
                        "required": False,
                    },
                ],
            },
        },
        {
            "name": "tools",
            "description": "Per-tool knobs: inline values or one "
            "delegated configuration file, never both.",
            "tools": {
                name: {
                    "knobs": sorted(spec),
                    "spec": {
                        knob: dict(details)
                        for knob, details in spec.items()
                    },
                }
                for name, spec in TOOL_KNOBS.items()
            },
        },
        {
            "name": "references",
            "description": "Project-relative content refs hashed "
            "into the run closure.",
            "item": {
                "type": "reference",
                "fields": [
                    {"name": "path", "type": "string",
                     "required": True},
                    {"name": "sha256", "type": "hash",
                     "required": False},
                ],
            },
        },
    ]
    return {"canvas": _CANVAS_VERSION, "sections": sections}


CANVAS_SCHEMA = ui_schema()
