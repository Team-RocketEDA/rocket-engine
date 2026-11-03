"""Raw-IR netlist emitters (CONNECT-GRAPH): SPICE, Verilog, VHDL.

`to_raw_ir` resolves one language-neutral record from extracted
structs — pins to canonical net names through `Connectivity.net_name`
plus the 4-level format chain — and each printer only arranges raw
lines and runs its small textual post-pass. Emitters never walk the
graph: they accept raw-IR mappings only. Bus expansion and line
joinery each live in exactly one shared helper.

Format chain, first non-empty template wins:

- instance_custom: instance `custom[language]`.
- symbol_custom: symbol `custom[language]`.
- instance_format: instance `format[language]`.
- symbol_format: symbol `format[language]`.

Templates substitute {name}, {symbol}, {cell}, {pins[PIN]},
{pin_nets} (pin-order nets, space-joined), and {generics[KEY]}.
Custom lines emit verbatim after substitution; format lines also run
the language post-pass. An instance with no template at any level is
skipped silently; a present-but-broken template raises loudly.
"""

import re

from .connectgraph import ConnectGraphError

RAW_IR_VERSION = 1

LANGUAGES = ("spice", "verilog", "vhdl")

FORMAT_LEVELS = (
    "instance_custom",
    "symbol_custom",
    "instance_format",
    "symbol_format",
)

_VHDL_DIRECTIONS = {"input": "in", "output": "out", "inout": "inout"}
_BUS_RE = re.compile(r"^(?P<base>.+)\[(?P<bit>\d+)\]$")
_SPICE_WIDTH = 80


def resolve_format(instance, symbol, language):
    """Resolve one instance template through the 4-level chain.

    Args:
        instance: Instance mapping with custom/format mappings.
        symbol: Symbol mapping with custom/format mappings.
        language: One of spice, verilog, vhdl.

    Returns:
        (level, template) with level from FORMAT_LEVELS, or
        (None, None) when no level carries a template.
    """
    candidates = (
        ("instance_custom", (instance.get("custom") or {}).get(language)),
        ("symbol_custom", (symbol.get("custom") or {}).get(language)),
        ("instance_format", (instance.get("format") or {}).get(language)),
        ("symbol_format", (symbol.get("format") or {}).get(language)),
    )
    for level, template in candidates:
        if template:
            return (level, template)
    return (None, None)


def to_raw_ir(structs):
    """Build the language-neutral raw IR from extracted structs.

    Args:
        structs: NetlistStructs from prepare_netlist_structs.

    Returns:
        Plain-data mapping (JSON-safe) with cell, nets, ports,
        instances carrying per-language lines, and skipped names.

    Raises:
        ConnectGraphError: Broken template at a resolved level.
    """
    connectivity = structs.connectivity
    nets = [{"id": net.id, "name": connectivity.net_name(net.id)} for net in connectivity.nets]
    nets.sort(key=lambda n: n["name"])
    instances = []
    skipped = []
    for resolved in structs.instances:
        symbol = structs.symbols[resolved.symbol]
        pin_nets = {
            pin: connectivity.net_name(net_id) for pin, net_id in resolved.pins
        }
        namespace = {
            "name": resolved.name,
            "symbol": resolved.symbol,
            "cell": structs.cell,
            "pins": pin_nets,
            "pin_nets": " ".join(
                pin_nets[pin] for pin, _ in resolved.pins
            ),
            "generics": dict(resolved.generics),
        }
        lines = {}
        resolutions = {}
        view = {"custom": resolved.custom, "format": resolved.format}
        for language in LANGUAGES:
            level, template = resolve_format(view, symbol, language)
            if level is None:
                continue
            try:
                lines[language] = [template.format(**namespace)]
            except (KeyError, IndexError, ValueError) as exc:
                raise ConnectGraphError(
                    f"Instance {resolved.name}: broken {language} template "
                    f"at {level}: {exc}."
                ) from exc
            resolutions[language] = level
        if not resolutions:
            skipped.append(resolved.name)
            continue
        instances.append(
            {
                "name": resolved.name,
                "symbol": resolved.symbol,
                "pins": [
                    {"pin": pin, "net": connectivity.net_name(net_id)}
                    for pin, net_id in resolved.pins
                ],
                "generics": dict(resolved.generics),
                "levels": resolutions,
                "lines": lines,
            }
        )
    instances.sort(key=lambda i: i["name"])
    return {
        "tool": "connectgraph",
        "raw_ir_version": RAW_IR_VERSION,
        "cell": structs.cell,
        "nets": nets,
        "ports": [dict(p) for p in structs.ports],
        "instances": instances,
        "skipped": sorted(skipped),
    }


def emit_netlists(raw_ir, languages=None):
    """Emit netlists for the requested languages.

    Args:
        raw_ir: Raw-IR mapping from to_raw_ir.
        languages: Subset of spice/verilog/vhdl; all when omitted.

    Returns:
        Mapping of language to netlist text.

    Raises:
        ConnectGraphError: Unknown language requested.
    """
    wanted = list(LANGUAGES) if languages is None else list(languages)
    unknown = [language for language in wanted if language not in LANGUAGES]
    if unknown:
        raise ConnectGraphError(f"Unknown netlist language(s): {', '.join(unknown)}.")
    printers = {"spice": emit_spice, "verilog": emit_verilog, "vhdl": emit_vhdl}
    return {language: printers[language](raw_ir) for language in wanted}


def emit_spice(raw_ir):
    """Print the SPICE netlist: subckt frame plus raw instance lines.

    Args:
        raw_ir: Raw-IR mapping from to_raw_ir.

    Returns:
        Byte-stable SPICE netlist text ending in one newline.
    """
    _check_raw_ir(raw_ir)
    ports = " ".join(p["name"] for p in raw_ir["ports"])
    header = f".subckt {raw_ir['cell']}" + (f" {ports}" if ports else "")
    body = []
    for instance in raw_ir["instances"]:
        for line in instance["lines"].get("spice", []):
            if instance["levels"]["spice"] in ("instance_format", "symbol_format"):
                body.extend(_wrap_continuation(line, _SPICE_WIDTH, "+"))
            else:
                body.append(line)
    return _join_block(
        f"* {raw_ir['cell']} - generated by connectgraph raw IR (do not edit)",
        [header, *body, f".ends {raw_ir['cell']}"],
    )


def emit_verilog(raw_ir):
    """Print the Verilog netlist: module frame plus raw instances.

    Args:
        raw_ir: Raw-IR mapping from to_raw_ir.

    Returns:
        Byte-stable Verilog netlist text ending in one newline.
    """
    _check_raw_ir(raw_ir)
    decls = _verilog_port_decls(raw_ir["ports"])
    header = f"module {raw_ir['cell']} ({', '.join(decls)});"
    wires = _bus_declarations(
        [n["name"] for n in raw_ir["nets"]],
        {p["name"] for p in raw_ir["ports"]},
        scalar="wire {name};",
        vector="wire [{hi}:{lo}] {base};",
    )
    body = []
    for instance in raw_ir["instances"]:
        body.extend(instance["lines"].get("verilog", []))
    return _join_block(
        f"// {raw_ir['cell']} - generated by connectgraph raw IR (do not edit)",
        [header, *wires, *body, "endmodule"],
    )


def emit_vhdl(raw_ir):
    """Print the VHDL netlist: entity plus raw port-map instances.

    Args:
        raw_ir: Raw-IR mapping from to_raw_ir.

    Returns:
        Byte-stable VHDL netlist text ending in one newline.
    """
    _check_raw_ir(raw_ir)
    ports = "; ".join(
        f"{p['name']} : {_VHDL_DIRECTIONS[p['direction']]} std_logic"
        for p in raw_ir["ports"]
    )
    signals = _bus_declarations(
        [n["name"] for n in raw_ir["nets"]],
        {p["name"] for p in raw_ir["ports"]},
        scalar="signal {name} : std_logic;",
        vector="signal {base} : std_logic_vector({hi} downto {lo});",
    )
    body = []
    for instance in raw_ir["instances"]:
        body.extend(instance["lines"].get("vhdl", []))
    return _join_block(
        f"-- {raw_ir['cell']} - generated by connectgraph raw IR (do not edit)",
        [
            "library ieee;",
            "use ieee.std_logic_1164.all;",
            f"entity {raw_ir['cell']} is",
            f"port ({ports});" if ports else "port ();",
            f"end entity {raw_ir['cell']};",
            f"architecture raw of {raw_ir['cell']} is",
            *signals,
            "begin",
            *body,
            f"end architecture raw;",
        ],
    )


def _check_raw_ir(raw_ir):
    if (
        not isinstance(raw_ir, dict)
        or raw_ir.get("raw_ir_version") != RAW_IR_VERSION
        or not isinstance(raw_ir.get("instances"), list)
    ):
        raise ConnectGraphError(
            "Emitters accept raw-IR mappings from to_raw_ir only."
        )


def _join_block(comment, lines):
    return comment + "\n" + "\n".join(lines) + "\n"


def _wrap_continuation(line, width, marker):
    """Wrap one line with continuation markers (the line joinery)."""
    if len(line) <= width:
        return [line]
    words = line.split(" ")
    chunks = [words[0]]
    for word in words[1:]:
        if len(chunks[-1]) + 1 + len(word) > width and chunks[-1]:
            chunks.append(marker + word)
        else:
            chunks[-1] = chunks[-1] + " " + word if chunks[-1] else word
    fixed = []
    for chunk in chunks[1:]:
        fixed.append(chunk if chunk.startswith(marker) else marker + chunk)
    return [chunks[0], *fixed]


def _bus_groups(names, ports):
    """Expand bus-bit names into one declaration group each.

    Scalars yield ("scalar", name); bits base[i] fold into one
    ("vector", base, lo, hi). Groups fully covered by ports are
    dropped — the port header already declares them.
    """
    bits = {}
    scalars = set()
    for name in names:
        match = _BUS_RE.match(name)
        if match:
            bits.setdefault(match.group("base"), []).append(
                (int(match.group("bit")), name)
            )
        else:
            scalars.add(name)
    groups = []
    for base in sorted(set(bits) | scalars):
        if base in scalars and base not in bits:
            if base not in ports:
                groups.append(("scalar", base))
            continue
        member_names = [name for _, name in bits.get(base, [])]
        if member_names and all(name in ports for name in member_names):
            continue
        lo = min(bit for bit, _ in bits[base])
        hi = max(bit for bit, _ in bits[base])
        groups.append(("vector", base, lo, hi))
    return groups


def _bus_declarations(names, ports, scalar, vector):
    """Declare nets once: scalars flat, bus bits as one vector."""
    declarations = []
    for group in _bus_groups(names, ports):
        if group[0] == "scalar":
            declarations.append(scalar.format(name=group[1]))
        else:
            declarations.append(
                vector.format(base=group[1], hi=group[3], lo=group[2])
            )
    return declarations


def _verilog_port_decls(ports):
    kinds = {"input": "input", "output": "output", "inout": "inout"}
    return [f"{kinds[p['direction']]} {p['name']}" for p in ports]
