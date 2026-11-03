"""Editable testbench source templates (TESTBENCH-COMPONENT).

Three saved source kinds — SPICE analysis (including transient),
inherited HDL, and cocotb — rendered from the materialized
target interface plus the explicit harness binding. Rendering
never guesses resets, power pins, or parameters: only
materialized pins appear, and an empty interface renders an
explicit no-pin scaffold. Sources are editable text the project
saves; regeneration renders a candidate the client adopts
explicitly, never an overwrite.
"""

from ...interfaces.errors import ContractError
from ...interfaces.refs import digest_mapping

#: Template source format version pinned into every provenance.
TEMPLATE_VERSION = 1

#: Renderable testbench kinds.
TEMPLATE_KINDS = ("spice", "hdl", "cocotb")

#: Saved source extension per kind.
TEMPLATE_EXTENSIONS = {"spice": "spice", "hdl": "sv", "cocotb": "py"}

#: Kind descriptions served by describe_template.
_KIND_DESCRIPTIONS = {
    "spice": "SPICE analysis scaffold (includes transient).",
    "hdl": "Inherited HDL testbench wrapper.",
    "cocotb": "cocotb Python test scaffold.",
}


def describe_template(kind):
    """Describe one template kind without rendering.

    Args:
        kind: Template kind (spice, hdl, or cocotb).

    Returns:
        Kind record with kind, extension, description, and
            template version.

    Raises:
        ContractError: invalid_kind for an unknown kind.
    """
    if kind not in TEMPLATE_KINDS:
        raise ContractError(
            "invalid_kind", f"Unknown testbench kind: {kind!r}.")
    return {
        "kind": kind,
        "extension": TEMPLATE_EXTENSIONS[kind],
        "description": _KIND_DESCRIPTIONS[kind],
        "template_version": TEMPLATE_VERSION,
    }


def _pin_lines(interface):
    """Render one comment line per materialized pin.

    Args:
        interface: Materialized interface with a pins list.

    Returns:
        Comment lines naming each materialized pin, or an
            explicit no-pin line when the interface is empty.
    """
    pins = interface.get("pins") or []
    if not pins:
        return ["* no materialized pins: scaffold only"]
    return [f"* pin: {pin.get('name')}" for pin in pins]


def _harness_lines(harness):
    """Render explicit harness binding lines.

    Args:
        harness: Explicit harness binding (stimulus, load,
            power assumptions).

    Returns:
        Comment lines for each binding entry, sorted by key.
    """
    return [
        f"* harness {key}: {harness[key]}"
        for key in sorted(harness or {})
    ]


def render(kind, interface, harness):
    """Render one editable testbench source from its inputs.

    Only materialized interface pins appear; harness entries
    render verbatim from the explicit binding. No resets, power
    pins, or parameters are guessed.

    Args:
        kind: Template kind (spice, hdl, or cocotb).
        interface: Materialized target interface with pins.
        harness: Explicit harness binding mapping.

    Returns:
        Rendered source with source text, digest, and
            provenance (kind, template version, digest).

    Raises:
        ContractError: invalid_kind for an unknown kind.
    """
    describe_template(kind)
    pins = interface.get("pins") if isinstance(interface, dict) else None
    if pins is None:
        raise ContractError(
            "invalid_template", "Interface needs a pins list.")
    lines = _pin_lines(interface) + _harness_lines(harness or {})
    if kind == "spice":
        body = ["* testbench (transient)", ".tran 1n 10n"]
    elif kind == "hdl":
        body = ["// inherited testbench", "module tb;"]
        body += [f"// {line[2:]}" for line in lines]
        lines = []
        body.append("endmodule")
    else:
        body = ["# cocotb testbench", "import cocotb"]
        body += [f"# {line[2:]}" for line in lines]
        lines = []
    source = "\n".join(body + lines) + "\n"
    provenance = {
        "kind": kind,
        "template_version": TEMPLATE_VERSION,
        "digest": digest_mapping({"kind": kind, "source": source}),
    }
    return {
        "source": source, "digest": provenance["digest"],
        "provenance": provenance,
    }
