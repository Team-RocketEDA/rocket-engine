"""FRONTEND-13 engine touchpoints: annotate, ERC, graph, netlist, xprobe, export.

Six pure query/op helpers over the ENGINE-ECS seam so IDE, MCP,
and script clients share one semantic:

- annotate: reference-designator assignment (idempotent).
- erc_check: ERC_TESTER with severities and pin-conflict config.
- connection_graph: buildConnectionGraph nodes/edges.
- write_netlist / update_netlist: DoWriteNetlist/UpdateNetlist.
- xprobe: ROCKET-XPROBE plus the resolvePin-as-query chokepoint.
- plot_export: plot/export drawing emission (pure SVG/JSON).
- flow_gate: binary-gated verdicts (sta/librelane absent ->
  loud BLOCKED-needs-host, never faked green).

Net data (net_pins) comes from materialize_nets-style extraction
and is passed in by the caller: when it is missing the helpers
say so loudly instead of inventing connectivity.
"""

import importlib.util
import shutil

from ..interfaces.errors import ContractError

#: Netlist languages write_netlist emits.
NETLIST_LANGUAGES = ("spice", "verilog")

#: Plot/export drawing formats.
EXPORT_FORMATS = ("svg", "json")

#: Tools flow_gate probes: binary on PATH, or importable package.
GATED_TOOLS = ("sta", "librelane")

#: Default ERC severities by rule.
DEFAULT_ERC_SEVERITIES = {
    "schematic.duplicate_ref": "error",
    "schematic.unknown_symbol": "error",
    "schematic.pin_conflict": "error",
    "schematic.unannotated": "warning",
    "schematic.unmatched_pins": "warning",
}

#: Default pin-conflict policy by "<type>-<type>" pair.
DEFAULT_PIN_CONFLICT = {"output-output": "error"}


def _all_instances(store):
    """List every instance mapping, id-sorted."""
    found = []
    for entity in store.entities_with("Instance"):
        try:
            raw = store.get_component(entity, "Instance")
        except LookupError:
            continue
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["id"] = entity
        found.append(item)
    found.sort(key=lambda item: item["id"])
    return found


def _symbol_names(store):
    """Return the set of project-owned symbol names."""
    names = set()
    for entity in store.entities_with("Symbol"):
        try:
            raw = store.get_component(entity, "Symbol")
        except LookupError:
            continue
        if isinstance(raw, dict) and raw.get("name"):
            names.add(raw["name"])
    return names


def _symbol_pin_types(store, symbol):
    """Return {pin: pin_type} for one symbol, or None when scoped."""
    if ":" in symbol:
        return None
    for entity in store.entities_with("Symbol"):
        try:
            raw = store.get_component(entity, "Symbol")
        except LookupError:
            continue
        if isinstance(raw, dict) and raw.get("name") == symbol:
            pins = raw.get("pins", [])
            return {
                pin["name"]: pin.get("pin_type", "passive")
                for pin in pins if isinstance(pin, dict)
            }
    return {}


def _linkage_for(store, symbol):
    """Return (cell, pin_map) for one symbol, or (None, {}) unlinked."""
    for entity in store.entities_with("Linkage"):
        try:
            raw = store.get_component(entity, "Linkage")
        except LookupError:
            continue
        if isinstance(raw, dict) and raw.get("symbol") == symbol:
            return raw.get("cell"), {
                entry["symPin"]: entry["cellPin"]
                for entry in raw.get("pin_map", [])
                if isinstance(entry, dict)
            }
    return None, {}


def annotate(store, actor, prefixes=None, sheet=None):
    """Assign reference designators to unannotated instances.

    Counters continue past the highest numeric suffix already on
    the sheet set, so reruns never collide; already-annotated
    instances keep their refs (idempotent).

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        actor: Attribution recorded on the revision and events.
        prefixes: Symbol name to ref-prefix mapping (symbols
            absent from it are reported, never guessed).
        sheet: Sheet entity id to scope to, or None for all.

    Returns:
        Receipt with annotated ([{instance, ref}]) and
            unannotated ([{instance, symbol}]) lists.

    Raises:
        ContractError: invalid_command for a malformed prefix map.
    """
    prefixes = prefixes or {}
    if not isinstance(prefixes, dict) or not all(
        isinstance(key, str) and isinstance(val, str) and val
        for key, val in prefixes.items()
    ):
        raise ContractError(
            "invalid_command",
            "Annotate prefixes must map symbol text to ref prefix.",
        )
    counters = {}
    for item in _all_instances(store):
        ref = item.get("ref", "")
        for prefix in set(prefixes.values()):
            if ref.startswith(prefix):
                tail = ref[len(prefix):]
                if tail.isdigit():
                    counters[prefix] = max(
                        counters.get(prefix, 0), int(tail)
                    )
    annotated = []
    unannotated = []
    for item in _all_instances(store):
        if sheet is not None and item.get("sheet") != sheet:
            continue
        if item.get("ref"):
            continue
        prefix = prefixes.get(item.get("symbol", ""))
        if not prefix:
            unannotated.append(
                {"instance": item["id"],
                 "symbol": item.get("symbol", "")}
            )
            continue
        counters[prefix] = counters.get(prefix, 0) + 1
        ref = f"{prefix}{counters[prefix]}"
        store.set_component(
            actor, item["id"], "Instance",
            {**{k: v for k, v in item.items() if k != "id"},
             "ref": ref},
            f"annotate {item['id']} {ref}",
        )
        annotated.append({"instance": item["id"], "ref": ref})
    return {
        "op": "annotate", "actor": actor,
        "annotated": annotated, "unannotated": unannotated,
    }


def erc_check(store, severities=None, pin_conflict=None,
              net_pins=None):
    """Run the ERC_TESTER rule set over the schematic.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        severities: Rule-to-severity overrides over
            DEFAULT_ERC_SEVERITIES.
        pin_conflict: "<type>-<type>" pair to severity overrides
            over DEFAULT_PIN_CONFLICT.
        net_pins: Materialized [{instance, pin, net}] rows for
            the pin-conflict rule; without them that rule is
            skipped loudly (reported, never assumed clean).

    Returns:
        Mapping with findings ([{rule, severity, message}]) and
            verdict ("fail" when any error-severity finding
            exists, else "pass").

    Raises:
        ContractError: invalid_command for malformed configs.
    """
    policy = dict(DEFAULT_ERC_SEVERITIES)
    for key, value in (severities or {}).items():
        if key not in DEFAULT_ERC_SEVERITIES:
            raise ContractError(
                "invalid_command", f"Unknown ERC rule: {key!r}."
            )
        if value not in ("error", "warning", "info"):
            raise ContractError(
                "invalid_command",
                f"Bad severity for {key!r}: {value!r}.",
            )
        policy[key] = value
    conflict_policy = dict(DEFAULT_PIN_CONFLICT)
    for key, value in (pin_conflict or {}).items():
        if value not in ("error", "warning", "info"):
            raise ContractError(
                "invalid_command",
                f"Bad pin-conflict severity for {key!r}.",
            )
        conflict_policy[key] = value
    findings = []
    instances = _all_instances(store)
    known = _symbol_names(store)
    seen_refs = {}
    for item in instances:
        ref = item.get("ref", "")
        if ref:
            seen_refs.setdefault(ref, []).append(item["id"])
        symbol = item.get("symbol", "")
        if ":" not in symbol and symbol not in known:
            findings.append({
                "rule": "schematic.unknown_symbol",
                "severity": policy["schematic.unknown_symbol"],
                "message": f"Instance {item['id']!r} references "
                f"unknown symbol {symbol!r}.",
            })
        if not ref:
            findings.append({
                "rule": "schematic.unannotated",
                "severity": policy["schematic.unannotated"],
                "message": f"Instance {item['id']!r} carries no ref.",
            })
    for ref, holders in sorted(seen_refs.items()):
        if len(holders) > 1:
            findings.append({
                "rule": "schematic.duplicate_ref",
                "severity": policy["schematic.duplicate_ref"],
                "message": f"Ref {ref!r} repeats on {holders}.",
            })
    if net_pins is not None:
        by_net = {}
        for row in net_pins:
            by_net.setdefault(row["net"], []).append(row)
        for net in sorted(by_net):
            outputs = [
                row for row in by_net[net]
                if row.get("pin_type") == "output"
            ]
            if len(outputs) >= 2:
                severity = conflict_policy.get(
                    "output-output", "error"
                )
                findings.append({
                    "rule": "schematic.pin_conflict",
                    "severity": severity,
                    "message": f"Net {net!r} shorts outputs "
                    f"{[(r['instance'], r['pin']) for r in outputs]}.",
                })
    for symbol in sorted(known):
        cell, pin_map = _linkage_for(store, symbol)
        if cell is None:
            continue
        pins = set(_symbol_pin_types(store, symbol) or ())
        problems = sorted(pins - set(pin_map))
        if problems:
            findings.append({
                "rule": "schematic.unmatched_pins",
                "severity": policy["schematic.unmatched_pins"],
                "message": f"Symbol {symbol!r} pins {problems} "
                "have no cell-port map.",
            })
    verdict = (
        "fail" if any(f["severity"] == "error" for f in findings)
        else "pass"
    )
    return {"findings": findings, "verdict": verdict}


def connection_graph(store, sheet=None):
    """Build the connection graph: sheets, instances, bindings.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        sheet: Sheet entity id to scope to, or None for all.

    Returns:
        Mapping with nodes ([{id, kind, name}]) and edges
            ([{from, to, rel}]; "contains" for sheet
            membership, "binds" for hierarchy bindings).
    """
    nodes = []
    edges = []
    want_sheets = set()
    for entity in store.entities_with("Sheet"):
        try:
            raw = store.get_component(entity, "Sheet")
        except LookupError:
            continue
        if not isinstance(raw, dict):
            continue
        if sheet is not None and entity != sheet:
            continue
        want_sheets.add(entity)
        nodes.append(
            {"id": entity, "kind": "sheet",
             "name": raw.get("name", entity)}
        )
    for item in _all_instances(store):
        if sheet is not None and item.get("sheet") != sheet:
            continue
        nodes.append({
            "id": item["id"], "kind": "instance",
            "name": item.get("ref") or item.get("symbol", ""),
        })
        if item.get("sheet") in want_sheets or sheet is None:
            edges.append({
                "from": item.get("sheet"), "to": item["id"],
                "rel": "contains",
            })
    for entity in store.entities_with("Hierarchy"):
        try:
            raw = store.get_component(entity, "Hierarchy")
        except LookupError:
            continue
        if not isinstance(raw, dict):
            continue
        parent, child = (
            raw.get("parent_sheet"), raw.get("child_sheet")
        )
        if sheet is not None and parent != sheet:
            continue
        edges.append({"from": parent, "to": child, "rel": "binds"})
    nodes.sort(key=lambda node: node["id"])
    edges.sort(key=lambda edge: (str(edge["from"]), str(edge["to"])))
    return {"nodes": nodes, "edges": edges}


def net_occurrences(net_pins, net):
    """List every (instance, pin) occurrence of one net.

    Args:
        net_pins: Materialized [{instance, pin, net}] rows from
            net extraction (materialize_nets output shape).
        net: Net name to collect.

    Returns:
        Occurrence rows [{instance, pin}] in input order.
    """
    return [
        {"instance": row["instance"], "pin": row["pin"]}
        for row in net_pins
        if isinstance(row, dict) and row.get("net") == net
    ]


def _net_index(net_pins):
    """Index net_pins rows into {(instance, pin): net}."""
    if net_pins is None:
        raise ContractError(
            "invalid_command",
            "Netlist emission needs net_pins from net extraction; "
            "refusing to invent connectivity.",
        )
    index = {}
    for row in net_pins:
        if (
            isinstance(row, dict) and row.get("instance")
            and row.get("pin") and row.get("net")
        ):
            index[(row["instance"], row["pin"])] = row["net"]
    return index


def _instance_nets(store, instance_id, symbol, index):
    """Return (ordered nets, unconnected pins) for one instance."""
    pins = _symbol_pin_types(store, symbol) or {}
    if pins:
        ordered = list(pins)
    else:
        ordered = sorted({
            pin for (inst, pin) in index if inst == instance_id
        })
    nets = []
    unconnected = []
    for pin in ordered:
        net = index.get((instance_id, pin))
        if net is None:
            nets.append(f"NC_{pin}")
            unconnected.append(pin)
        else:
            nets.append(net)
    return nets, unconnected


def write_netlist(store, language="spice", sheet=None, title="top",
                  net_pins=None):
    """Write a netlist for the schematic (DoWriteNetlist).

    Pins with no extracted net emit explicit ``NC_<pin>``
    stubs and are reported under ``unconnected`` — dangling
    connections are named, never dropped.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        language: Netlist language ("spice" or "verilog").
        sheet: Sheet entity id to scope to, or None for all.
        title: Netlist/circuit title.
        net_pins: Materialized [{instance, pin, net}] rows
            (required — connectivity is never invented).

    Returns:
        Mapping with language, text, instance count, nets,
            and unconnected pins.

    Raises:
        ContractError: invalid_language for an unknown
            language, invalid_command without net_pins.
    """
    if language not in NETLIST_LANGUAGES:
        raise ContractError(
            "invalid_language",
            f"Netlist language must be one of {NETLIST_LANGUAGES}.",
        )
    index = _net_index(net_pins)
    instances = [
        item for item in _all_instances(store)
        if sheet is None or item.get("sheet") == sheet
    ]
    nets = sorted(set(index.values()))
    unconnected = []
    if language == "spice":
        lines = [f"* {title}"]
        for item in instances:
            inst_nets, missing = _instance_nets(
                store, item["id"], item.get("symbol", ""), index
            )
            unconnected.extend(
                {"instance": item["id"], "pin": pin}
                for pin in missing
            )
            tag = item.get("ref") or item["id"]
            lines.append(
                f"X{tag} {' '.join(inst_nets)} "
                f"{item.get('symbol', '')}"
            )
        lines.append(".end")
    else:
        lines = [f"module {title} ();"]
        for item in instances:
            inst_nets, missing = _instance_nets(
                store, item["id"], item.get("symbol", ""), index
            )
            unconnected.extend(
                {"instance": item["id"], "pin": pin}
                for pin in missing
            )
            pins = _symbol_pin_types(store, item.get("symbol", "")) or {}
            ordered = list(pins) or sorted({
                pin for (inst, pin) in index
                if inst == item["id"]
            })
            ports = ", ".join(
                f".{pin}({net})"
                for pin, net in zip(ordered, inst_nets)
            )
            tag = item.get("ref") or item["id"]
            lines.append(
                f"  {item.get('symbol', '')} {tag} ({ports});"
            )
        lines.append("endmodule")
    return {
        "language": language, "text": "\n".join(lines) + "\n",
        "title": title, "instances": len(instances), "nets": nets,
        "unconnected": unconnected,
    }


def update_netlist(store, language, prior_text, sheet=None,
                   title="top", net_pins=None):
    """Rewrite a netlist and report whether it changed (UpdateNetlist).

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        language: Netlist language ("spice" or "verilog").
        prior_text: Previously emitted netlist text.
        sheet: Sheet entity id to scope to, or None for all.
        title: Netlist/circuit title.
        net_pins: Materialized [{instance, pin, net}] rows.

    Returns:
        Mapping with language, text, and changed flag.

    Raises:
        ContractError: invalid_language for an unknown
            language, invalid_command without net_pins.
    """
    fresh = write_netlist(
        store, language=language, sheet=sheet, title=title,
        net_pins=net_pins,
    )
    return {
        "language": language, "text": fresh["text"],
        "changed": fresh["text"] != prior_text,
        "unconnected": fresh["unconnected"],
    }


def xprobe(store, instance, pin, net_pins=None):
    """Cross-probe one pin: symbol, cell, cell pin, net (ROCKET-XPROBE).

    The resolvePin-as-query chokepoint: explicit linkage wins,
    unlisted pins resolve to themselves, and the net comes from
    extracted net_pins — without them the probe reports
    ``net_known: False`` instead of guessing.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        instance: Instance entity id to probe.
        pin: Symbol pin to probe.
        net_pins: Materialized [{instance, pin, net}] rows, or
            None when no extraction ran.

    Returns:
        Mapping with instance, pin, symbol, cell (None when
            unlinked), cell_pin, net (None when unknown), and
            net_known flag.

    Raises:
        ContractError: unknown_instance for a missing
            instance, unknown_pin for a pin the symbol lacks.
    """
    try:
        raw = store.get_component(instance, "Instance")
    except LookupError:
        raise ContractError(
            "unknown_instance",
            f"No such instance entity: {instance!r}.",
        ) from None
    if not isinstance(raw, dict):
        raise ContractError(
            "unknown_instance",
            f"No such instance entity: {instance!r}.",
        )
    symbol = raw.get("symbol", "")
    known_pins = _symbol_pin_types(store, symbol)
    if known_pins is not None and pin not in known_pins:
        raise ContractError(
            "unknown_pin",
            f"Symbol {symbol!r} carries no pin {pin!r}.",
        )
    cell, pin_map = _linkage_for(store, symbol)
    net = None
    for row in net_pins or []:
        if (
            isinstance(row, dict) and row.get("instance") == instance
            and row.get("pin") == pin
        ):
            net = row.get("net")
            break
    return {
        "instance": instance, "pin": pin, "symbol": symbol,
        "cell": cell, "cell_pin": pin_map.get(pin, pin),
        "net": net, "net_known": net is not None,
    }


def plot_export(store, format="svg", sheet=None):
    """Export the schematic drawing (plot/export op).

    Pure emission — no solver, no display server: SVG frames
    each sheet with instance boxes plus ref/symbol labels, and
    JSON carries the same drawing as structured data.

    Args:
        store: Entity store serving the ENGINE-ECS seam.
        format: Drawing format ("svg" or "json").
        sheet: Sheet entity id to scope to, or None for all.

    Returns:
        Mapping with format, content (text or drawing
            mapping), and sheet/instance counts.

    Raises:
        ContractError: invalid_format for an unknown format.
    """
    if format not in EXPORT_FORMATS:
        raise ContractError(
            "invalid_format",
            f"Export format must be one of {EXPORT_FORMATS}.",
        )
    instances = [
        item for item in _all_instances(store)
        if sheet is None or item.get("sheet") == sheet
    ]
    sheets = [
        node for node in connection_graph(store, sheet)["nodes"]
        if node["kind"] == "sheet"
    ]
    drawing = {
        "sheets": sheets,
        "instances": [
            {"id": item["id"], "sheet": item.get("sheet"),
             "symbol": item.get("symbol"), "ref": item.get("ref"),
             "x": item.get("x"), "y": item.get("y"),
             "rotation": item.get("rotation"),
             "mirror": item.get("mirror")}
            for item in instances
        ],
    }
    if format == "json":
        return {
            "format": format, "content": drawing,
            "sheets": len(sheets), "instances": len(instances),
        }
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg">',
        f"<!-- sheets={len(sheets)} instances={len(instances)} -->",
    ]
    for order, item in enumerate(drawing["instances"]):
        x = 20 + (order % 8) * 90
        y = 20 + (order // 8) * 70
        label = item["ref"] or item["symbol"]
        parts.append(
            f'<g id="{item["id"]}">'
            f'<rect x="{x}" y="{y}" width="70" height="50" '
            'fill="none" stroke="black"/>'
            f'<text x="{x + 4}" y="{y + 20}">{label}</text>'
            f"<title>{item['symbol']} {item['ref']}</title></g>"
        )
    parts.append("</svg>")
    return {
        "format": format, "content": "\n".join(parts),
        "sheets": len(sheets), "instances": len(instances),
    }


def flow_gate(tool):
    """Report the availability verdict for a binary-gated flow tool.

    Absent tools report loud BLOCKED-needs-host with a remedy —
    never a faked green verdict.

    Args:
        tool: Tool name ("sta" or "librelane").

    Returns:
        Mapping with tool, available flag, verdict ("ready" or
            "BLOCKED-needs-host"), and remedy text when blocked.

    Raises:
        ContractError: unknown_tool for an unlisted tool.
    """
    if tool not in GATED_TOOLS:
        raise ContractError(
            "unknown_tool", f"No flow gate for tool {tool!r}."
        )
    if tool == "sta":
        available = shutil.which("sta") is not None
        remedy = (
            "Install OpenSTA on PATH (or provision the timing "
            "profile) and rerun; run_timing stays unwired until then."
        )
    else:
        available = importlib.util.find_spec("librelane") is not None
        remedy = (
            "Provision the digital-flow profile (librelane) and "
            "rerun; run_digital_flow stays unwired until then."
        )
    if available:
        return {"tool": tool, "available": True, "verdict": "ready"}
    return {
        "tool": tool, "available": False,
        "verdict": "BLOCKED-needs-host", "remedy": remedy,
    }
