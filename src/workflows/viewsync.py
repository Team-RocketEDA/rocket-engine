"""Intended-vs-extracted view comparison (VIEW-SYNC, photonic P14).

`compare_views` reduces two schematics through the shared
CONNECT-GRAPH extraction (`prepare_netlist_structs`), correlates
pins through CellLink identity (never a second naming scheme),
and reports missing/wrong/extra ports, missing/unexpected
connections, and unmapped objects with per-finding identity
references. Every net name flows from the cited view's shared
`Connectivity.net_name` authority.
"""

import json

from ..interfaces.celllink import REFERENCE, ContractError, resolve_link
from .connectgraph import ConnectGraphError, prepare_netlist_structs

RULE_MISSING_PORT = "view_sync.missing_port"
RULE_EXTRA_PORT = "view_sync.extra_port"
RULE_WRONG_PORT = "view_sync.wrong_port"
RULE_MISSING_CONNECTION = "view_sync.missing_connection"
RULE_UNEXPECTED_CONNECTION = "view_sync.unexpected_connection"
RULE_UNMAPPED = "view_sync.unmapped"


class ViewSyncError(ValueError):
    """Bad view-sync input: malformed view or bad identity mapping."""


def _identity_maps(links, variant):
    """Per-instance symbol-to-cell maps plus their inverses."""
    if links is None:
        links = []
    if not isinstance(links, list):
        raise ViewSyncError(f"links must be a list, got {links!r}.")
    base_variant = variant in (None, REFERENCE)
    if not base_variant:
        if not isinstance(variant, str) or not variant:
            raise ViewSyncError(
                f"variant must be a non-empty string, got {variant!r}."
            )
        if not links:
            raise ViewSyncError(f"Unknown variant {variant!r}: no links define it.")
    forward = {}
    for index, entry in enumerate(links):
        if not isinstance(entry, dict):
            raise ViewSyncError(f"links[{index}] must be a mapping, got {entry!r}.")
        block_id = entry.get("id")
        if not isinstance(block_id, str) or not block_id:
            raise ViewSyncError(f"links[{index}] needs a non-empty string id.")
        if block_id in forward:
            raise ViewSyncError(f"Duplicate link id: {block_id!r}.")
        block = {"id": block_id}
        if "CellLink" in entry:
            block["CellLink"] = entry["CellLink"]
        try:
            resolved = resolve_link(block, variant=variant)
        except ContractError as exc:
            raise ViewSyncError(f"link {block_id!r}: {exc}") from exc
        mapping = {item["symPin"]: item["cellPin"] for item in resolved["pinMap"]}
        targets = sorted(mapping.values())
        if len(set(targets)) != len(targets):
            raise ViewSyncError(
                f"link {block_id!r}: pinMap collision: two symbol pins "
                f"resolve to one cell pin ({', '.join(targets)})."
            )
        forward[block_id] = mapping
    reverse = {
        name: {cell: sym for sym, cell in mapping.items()}
        for name, mapping in forward.items()
    }
    return forward, reverse


def _extract_side(schematic, side):
    """Extract one view, naming the side on failure."""
    try:
        return prepare_netlist_structs(schematic)
    except ConnectGraphError as exc:
        raise ViewSyncError(f"{side} schematic: {exc}") from exc


def _net_id_by_name(connectivity, name, side):
    """Net id for a port name (ports always name an extracted net)."""
    for net in connectivity.nets:
        if net.name == name:
            return net.id
    raise ViewSyncError(f"{side} port {name!r} names no extracted net.")


def _port_findings(intended_structs, extracted_structs):
    """Missing/wrong/extra port findings with authority net names."""
    findings = []
    iconn = intended_structs.connectivity
    econn = extracted_structs.connectivity
    intended_ports = {p["name"]: p["direction"] for p in intended_structs.ports}
    extracted_ports = {p["name"]: p["direction"] for p in extracted_structs.ports}
    for name in sorted(set(intended_ports) - set(extracted_ports)):
        net_id = _net_id_by_name(iconn, name, "intended")
        findings.append(
            {
                "rule": RULE_MISSING_PORT,
                "severity": "error",
                "message": (
                    f"port {name} is missing in extracted "
                    f"(intended direction {intended_ports[name]})"
                ),
                "view": "intended",
                "port": name,
                "expected_direction": intended_ports[name],
                "net": iconn.net_name(net_id),
                "net_id": net_id,
            }
        )
    for name in sorted(set(extracted_ports) - set(intended_ports)):
        net_id = _net_id_by_name(econn, name, "extracted")
        findings.append(
            {
                "rule": RULE_EXTRA_PORT,
                "severity": "error",
                "message": (
                    f"port {name} is unexpected in extracted "
                    f"(direction {extracted_ports[name]})"
                ),
                "view": "extracted",
                "port": name,
                "actual_direction": extracted_ports[name],
                "net": econn.net_name(net_id),
                "net_id": net_id,
            }
        )
    for name in sorted(set(intended_ports) & set(extracted_ports)):
        if intended_ports[name] == extracted_ports[name]:
            continue
        intended_id = _net_id_by_name(iconn, name, "intended")
        extracted_id = _net_id_by_name(econn, name, "extracted")
        findings.append(
            {
                "rule": RULE_WRONG_PORT,
                "severity": "error",
                "message": (
                    f"port {name} direction {extracted_ports[name]}, "
                    f"expected {intended_ports[name]}"
                ),
                "view": "extracted",
                "port": name,
                "expected_direction": intended_ports[name],
                "actual_direction": extracted_ports[name],
                "net": econn.net_name(extracted_id),
                "net_id": extracted_id,
                "intended_net_id": intended_id,
                "extracted_net_id": extracted_id,
            }
        )
    return findings


def _correlate(intended_structs, extracted_structs, forward, reverse):
    """Correlate pins through CellLink identity (mapped + unmapped)."""
    intended_by_inst = {i.name: i for i in intended_structs.instances}
    extracted_by_inst = {i.name: i for i in extracted_structs.instances}
    findings = []
    for name in sorted(set(intended_by_inst) - set(extracted_by_inst)):
        pins = sorted(p for p, _ in intended_by_inst[name].pins)
        findings.append(
            {
                "rule": RULE_UNMAPPED,
                "severity": "error",
                "message": (
                    f"instance {name} has no extracted counterpart "
                    f"({len(pins)} pins)"
                ),
                "view": "intended",
                "kind": "instance",
                "instance": name,
                "side": "intended",
                "pins": pins,
            }
        )
    for name in sorted(set(extracted_by_inst) - set(intended_by_inst)):
        pins = sorted(p for p, _ in extracted_by_inst[name].pins)
        findings.append(
            {
                "rule": RULE_UNMAPPED,
                "severity": "error",
                "message": (
                    f"instance {name} has no intended counterpart "
                    f"({len(pins)} pins)"
                ),
                "view": "extracted",
                "kind": "instance",
                "instance": name,
                "side": "extracted",
                "pins": pins,
            }
        )
    mapped = []
    for name in sorted(set(intended_by_inst) & set(extracted_by_inst)):
        pin_map = forward.get(name, {})
        back_map = reverse.get(name, {})
        intended_pins = {p: n for p, n in intended_by_inst[name].pins}
        extracted_pins = {p: n for p, n in extracted_by_inst[name].pins}
        matched = set()
        for sym in sorted(intended_pins):
            cell = pin_map.get(sym, sym)
            if cell in extracted_pins:
                matched.add(cell)
                mapped.append(
                    (name, sym, cell, intended_pins[sym], extracted_pins[cell])
                )
                continue
            conn = intended_structs.connectivity
            net_id = intended_pins[sym]
            findings.append(
                {
                    "rule": RULE_UNMAPPED,
                    "severity": "error",
                    "message": (
                        f"pin {name}.{sym} has no extracted counterpart "
                        f"(cell pin {cell})"
                    ),
                    "view": "intended",
                    "kind": "pin",
                    "instance": name,
                    "pin": sym,
                    "cell_pin": cell,
                    "side": "intended",
                    "net": conn.net_name(net_id),
                    "net_id": net_id,
                }
            )
        for cell in sorted(set(extracted_pins) - matched):
            conn = extracted_structs.connectivity
            net_id = extracted_pins[cell]
            findings.append(
                {
                    "rule": RULE_UNMAPPED,
                    "severity": "error",
                    "message": (
                        f"pin {name}.{cell} has no intended counterpart "
                        f"(symbol pin {back_map.get(cell, cell)})"
                    ),
                    "view": "extracted",
                    "kind": "pin",
                    "instance": name,
                    "pin": cell,
                    "sym_pin": back_map.get(cell, cell),
                    "side": "extracted",
                    "net": conn.net_name(net_id),
                    "net_id": net_id,
                }
            )
    return mapped, findings


def _connection_findings(intended_structs, extracted_structs, mapped):
    """Split (missing) and joined (unexpected) net findings."""
    findings = []
    iconn = intended_structs.connectivity
    econn = extracted_structs.connectivity
    by_intended = {}
    for inst, sym, cell, intended_id, extracted_id in mapped:
        by_intended.setdefault(intended_id, []).append(
            (inst, sym, cell, extracted_id)
        )
    for intended_id in sorted(by_intended):
        members = by_intended[intended_id]
        landed = sorted({extracted_id for (_, _, _, extracted_id) in members})
        if len(landed) > 1:
            split = [{"net": econn.net_name(x), "net_id": x} for x in landed]
            pin_list = sorted(f"{i}.{s}" for (i, s, _, _) in members)
            findings.append(
                {
                    "rule": RULE_MISSING_CONNECTION,
                    "severity": "error",
                    "message": (
                        f"net {iconn.net_name(intended_id)} splits across "
                        f"{', '.join(s['net'] for s in split)} in extracted: "
                        + ", ".join(pin_list)
                    ),
                    "view": "intended",
                    "net": iconn.net_name(intended_id),
                    "net_id": intended_id,
                    "split_across": split,
                    "members": [
                        {"instance": i, "pin": s, "cell_pin": c}
                        for (i, s, c, _) in sorted(members)
                    ],
                }
            )
    by_extracted = {}
    for inst, sym, cell, intended_id, extracted_id in mapped:
        by_extracted.setdefault(extracted_id, []).append(
            (inst, sym, cell, intended_id)
        )
    for extracted_id in sorted(by_extracted):
        members = by_extracted[extracted_id]
        sources = sorted({intended_id for (_, _, _, intended_id) in members})
        if len(sources) > 1:
            merged = [{"net": iconn.net_name(i), "net_id": i} for i in sources]
            pin_list = sorted(f"{i}.{c}" for (i, _, c, _) in members)
            findings.append(
                {
                    "rule": RULE_UNEXPECTED_CONNECTION,
                    "severity": "error",
                    "message": (
                        f"net {econn.net_name(extracted_id)} joins "
                        f"{', '.join(m['net'] for m in merged)} in extracted: "
                        + ", ".join(pin_list)
                    ),
                    "view": "extracted",
                    "net": econn.net_name(extracted_id),
                    "net_id": extracted_id,
                    "merged_from": merged,
                    "members": [
                        {"instance": i, "pin": c, "sym_pin": s}
                        for (i, s, c, _) in sorted(members)
                    ],
                }
            )
    return findings


def _coverage(intended_structs, extracted_structs, mapped, count):
    """Coverage mapping with the explicit sync statement."""
    pinless = sum(1 for n in intended_structs.connectivity.nets if not n.pins)
    pinless += sum(1 for n in extracted_structs.connectivity.nets if not n.pins)
    intended_nets = len(intended_structs.connectivity.nets)
    extracted_nets = len(extracted_structs.connectivity.nets)
    sizes = (
        f"{intended_nets} vs {extracted_nets} nets, {len(mapped)} mapped pins"
    )
    if count == 0:
        statement = (
            "view_sync: intended and extracted are in sync "
            f"(0 findings, {sizes})"
        )
    else:
        noun = "finding" if count == 1 else "findings"
        statement = (
            f"view_sync: {count} {noun}; intended vs extracted out of sync "
            f"({sizes})"
        )
    return {
        "compared_views": ["intended", "extracted"],
        "intended_nets": intended_nets,
        "extracted_nets": extracted_nets,
        "mapped_pins": len(mapped),
        "pinless_nets_skipped": pinless,
        "statement": statement,
    }


def compare_views(intended, extracted, links=None, variant=None):
    """Diff intended vs extracted schematics over shared connectivity.

    Both views reduce through CONNECT-GRAPH extraction, pins
    correlate through CellLink identity, and ports, connections,
    and unmapped objects diff with per-finding identity
    references; every net name resolves through the cited view's
    `Connectivity.net_name` authority.

    Args:
        intended: Intended-view schematic record (symbol-pin space;
            see workflows.connectgraph for the shape).
        extracted: Extracted-view schematic record (cell-pin space).
        links: CellLink block links ([{id, CellLink?}]) mapping
            intended symbol pins to extracted cell pins; None or []
            correlates by identity.
        variant: Variant selector applied to every link; None and
            REFERENCE resolve each stored base link.

    Returns:
        Mapping with findings (sorted by rule, deterministic),
            coverage (compared views, net counts, mapped pins,
            pinless skips, statement), and a text report.

    Raises:
        ViewSyncError: Malformed schematic (naming its side),
            malformed links, an unknown variant, or a pinMap
            collision.

    Caution: Optical view comparison, never transistor LVS —
        findings judge connectivity sync only, not device
        equivalence.
    """
    forward, reverse = _identity_maps(links, variant)
    intended_structs = _extract_side(intended, "intended")
    extracted_structs = _extract_side(extracted, "extracted")
    mapped, unmapped = _correlate(
        intended_structs, extracted_structs, forward, reverse
    )
    findings = _port_findings(intended_structs, extracted_structs)
    findings.extend(unmapped)
    findings.extend(_connection_findings(intended_structs, extracted_structs, mapped))
    findings.sort(key=lambda f: (f["rule"], json.dumps(f, sort_keys=True)))
    coverage = _coverage(intended_structs, extracted_structs, mapped, len(findings))
    lines = [coverage["statement"]]
    lines.extend(f"- [{f['rule']}] {f['message']}" for f in findings)
    return {"findings": findings, "coverage": coverage, "report": "\n".join(lines)}
