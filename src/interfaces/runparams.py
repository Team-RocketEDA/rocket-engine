"""Explicit run.request params schema (RUN-PARAMS).

Runs are explicit, always — no live-update path — so every knob a
run needs travels IN the run request, frozen into the run snapshot
like everything else. xschem keeps netlist knobs as live TCL vars;
the web split cannot do that without per-event round-trips, so they
become explicit `request` parameters: netlist type, flat/split
shape, the LVS-netlist flag, top-is-subckt, and deck opts
passthrough. Without this schema run reproducibility has a hole:
two identical-looking runs could differ by a knob nobody recorded.

Validated at submit (`Engine.submit` and `Engine.run` normalize
`arguments["request"]` through `validate_run_request` before the
command text is frozen), replayed byte-identically through
`freeze_run_request`, and read back through `parse_run_request`.
Unknown fields are rejected loudly, never ignored — and every
caller (IDE, MCP, console) sends the same shape because validation
lives in the engine, not the transports.
"""

import io

from ruamel.yaml import YAML

# Mirrors xschem's netlist_type TCL var: the netlist dialect the run
# netlists in. Canonical order is display order (error text, schema).
NETLIST_TYPES = ("spice", "spectre", "verilog", "vhdl")

# Canonical knob order: validation output, frozen text, and the
# schema all follow this order so replays compare byte-identically.
RUN_REQUEST_FIELDS = (
    "netlist_type",
    "flat_netlist",
    "lvs_netlist",
    "top_is_subckt",
    "deck_opts",
)

RUN_REQUEST_DEFAULTS = {
    "netlist_type": "spice",
    "flat_netlist": False,
    "lvs_netlist": False,
    "top_is_subckt": False,
    "deck_opts": {},
}

_BOOL_FLAGS = ("flat_netlist", "lvs_netlist", "top_is_subckt")

# Deck opts pass through to the solver deck untouched: flat scalar
# options only (a nested mapping would smuggle unvalidated shape
# into the tool call). None means "present but valueless".
_SCALAR_TYPES = (str, int, float, bool, type(None))

# Machine seam for api_spec/contract regen: the integrator injects
# this `request` property into solver-op schemas from here, the way
# expected_revision is injected from ProjectService.submit's arg
# text. additionalProperties False is the schema half of "unknown
# fields rejected, never ignored".
RUN_REQUEST_SCHEMA = {
    "type": "object",
    "description": (
        "Explicit run knobs (xschem live-var equivalents), frozen "
        "into the run snapshot. Unknown fields are rejected."
    ),
    "properties": {
        "netlist_type": {
            "type": "string",
            # Literal (not list(NETLIST_TYPES)): api_spec reads this
            # schema via AST without importing; tests pin equality.
            "enum": ["spice", "spectre", "verilog", "vhdl"],
            "default": "spice",
            "description": "Netlist dialect the run netlists in.",
        },
        "flat_netlist": {
            "type": "boolean",
            "default": False,
            "description": "Flatten the hierarchy (else split per cell).",
        },
        "lvs_netlist": {
            "type": "boolean",
            "default": False,
            "description": "Netlist for LVS comparison.",
        },
        "top_is_subckt": {
            "type": "boolean",
            "default": False,
            "description": "Emit the top cell as a subcircuit.",
        },
        "deck_opts": {
            "type": "object",
            "default": {},
            "description": "Solver deck options, flat scalar passthrough.",
        },
    },
    "additionalProperties": False,
}


class RunParamsError(Exception):
    """Run.request violation with a stable machine code.

    Args:
        code: Stable machine-readable error code
            (unknown_run_param, invalid_run_param,
            invalid_run_request).
        message: Human-readable detail naming the field.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


def _check_deck_opts(opts):
    """Validate deck opts: string keys, flat scalar values."""
    if not isinstance(opts, dict):
        raise RunParamsError(
            "invalid_run_param",
            f"deck_opts must be a mapping, got {opts!r}.",
            fields=["deck_opts"],
        )
    for key, value in opts.items():
        if not isinstance(key, str) or not key:
            raise RunParamsError(
                "invalid_run_param",
                f"deck_opts keys must be non-empty strings, got {key!r}.",
                fields=["deck_opts"],
            )
        if not isinstance(value, _SCALAR_TYPES):
            raise RunParamsError(
                "invalid_run_param",
                f"deck_opts.{key} must be a scalar, got {value!r}.",
                fields=["deck_opts"],
            )
    return dict(opts)


def validate_run_request(params):
    """Validate and normalize one run.request mapping.

    Missing input (None) and `{}` both mean "all defaults": the
    frozen snapshot always shows every knob explicitly, so old
    callers that send no `request` still record what they ran with.

    Args:
        params: Caller-supplied `request` mapping, or None when
            the caller sent no `request` key.

    Returns:
        Normalized mapping with every knob present in canonical
        field order: caller values where given, schema defaults
        elsewhere. A fresh mapping — the caller's dict is never
        mutated.

    Raises:
        RunParamsError: unknown_run_param naming every unknown
            field, invalid_run_param naming the mistyped field
            (netlist_type outside the enum, a non-bool flag, a
            malformed deck_opts), invalid_run_request for a
            non-mapping `request`.
    """
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise RunParamsError(
            "invalid_run_request",
            f"request must be a mapping, got {params!r}.",
        )
    unknown = sorted(key for key in params if key not in RUN_REQUEST_FIELDS)
    if unknown:
        raise RunParamsError(
            "unknown_run_param",
            f"Unknown run.request field(s): {', '.join(map(repr, unknown))}; "
            f"known fields: {', '.join(RUN_REQUEST_FIELDS)}.",
            fields=unknown,
        )
    kind = params.get("netlist_type", RUN_REQUEST_DEFAULTS["netlist_type"])
    if kind not in NETLIST_TYPES:
        raise RunParamsError(
            "invalid_run_param",
            f"netlist_type must be one of {', '.join(NETLIST_TYPES)}, "
            f"got {kind!r}.",
            fields=["netlist_type"],
        )
    normalized = {"netlist_type": kind}
    for flag in _BOOL_FLAGS:
        value = params.get(flag, False)
        if not isinstance(value, bool):
            raise RunParamsError(
                "invalid_run_param",
                f"{flag} must be a boolean, got {value!r}.",
                fields=[flag],
            )
        normalized[flag] = value
    normalized["deck_opts"] = _check_deck_opts(
        params.get("deck_opts", RUN_REQUEST_DEFAULTS["deck_opts"])
    )
    return normalized


def freeze_run_request(validated):
    """Render validated knobs as canonical inputs.yaml text.

    Key order is canonical (schema field order, deck opts sorted),
    so the same logical request replays byte-identically whatever
    key order the caller sent.

    Args:
        validated: Normalized mapping from `validate_run_request`.

    Returns:
        Deterministic YAML text (`request:` mapping) for the run
        snapshot: same knobs in, same bytes out.
    """
    ordered = {field: validated[field] for field in RUN_REQUEST_FIELDS}
    ordered["deck_opts"] = {
        key: ordered["deck_opts"][key] for key in sorted(ordered["deck_opts"])
    }
    buf = io.StringIO()
    YAML(typ="safe").dump({"request": ordered}, buf)
    return buf.getvalue()


def parse_run_request(text):
    """Read frozen inputs.yaml text back into validated knobs.

    Args:
        text: YAML text holding a top-level `request:` mapping, as
            rendered by `freeze_run_request`.

    Returns:
        Validated mapping (see `validate_run_request`).

    Raises:
        RunParamsError: invalid_run_request for unparsable text or
            a missing/non-mapping `request`, else whatever
            `validate_run_request` raises for the stored knobs.
    """
    try:
        data = YAML(typ="safe").load(text)
    except Exception as exc:
        raise RunParamsError(
            "invalid_run_request", f"Cannot parse inputs.yaml: {exc}."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("request"), dict):
        raise RunParamsError(
            "invalid_run_request",
            "inputs.yaml must hold a top-level request mapping.",
        )
    return validate_run_request(data["request"])
