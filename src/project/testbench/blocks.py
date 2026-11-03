"""Scoped testbench blocks over the ENGINE-ECS entity seam.

One block names a device under test (a primary circuit-instance
occurrence plus explicit nonoverlapping additional targets),
probes inside the DUT closure, an explicit harness binding, and
an editable source rendered from the materialized interface. At
occurrence ``P+[bench]`` the legal DUTs are sibling circuit
instances plus descendants: ancestors, the bench scope itself,
unrelated scopes, overlapping targets, and out-of-closure probes
are refused. Stable entity ids disambiguate reused definitions —
never names or positions.

Renames preserve bindings; hierarchy moves, deletes, interface
changes, and template upgrades mark the link stale and block the
run. Regeneration renders a candidate the client adopts
explicitly and never overwrites an edited source. Harness
components stay out of the production netlist unless the design
adopts them. Simulator runs stay binary-gated: absent tools
report BLOCKED-needs-host, never a faked green.
"""

import importlib.util
import shutil

from ...interfaces.errors import ContractError
from ...interfaces.refs import digest_mapping
from ..edit.cas import read_entity_revision
from .templates import (
    TEMPLATE_EXTENSIONS,
    TEMPLATE_VERSION,
    describe_template,
    render,
)

#: Entity component carrying the testbench record.
TESTBENCH_COMPONENT = "Testbench"

#: Saved source document prefix per block name.
SOURCE_PREFIX = "testbench/"

#: Simulator binary probed per testbench kind.
SIMULATOR_TOOLS = {"spice": "ngspice", "hdl": "icarus", "cocotb": "cocotb"}


def _instance_of(service, entity):
    """Read one instance payload, or None when not an instance.

    Args:
        service: ProjectService handle to read through.
        entity: Entity id to inspect.

    Returns:
        Instance payload mapping, or None for a missing entity
            or a non-instance holder.
    """
    from ..errors import ProjectError as _ProjectError

    try:
        data = service.get_component(entity, "Instance")["data"]
    except _ProjectError:
        return None
    except LookupError:
        return None
    return data if isinstance(data, dict) else None


def _bindings(service):
    """List every hierarchy binding payload, id-sorted.

    Args:
        service: ProjectService handle to read through.

    Returns:
        Binding mappings with id, parent_sheet, child_sheet,
            and instance.
    """
    found = []
    for entity in service.entities_with("Hierarchy")["entities"]:
        try:
            raw = service.get_component(entity, "Hierarchy")["data"]
        except Exception:  # noqa: BLE001 — skip unreadable rows
            continue
        if isinstance(raw, dict):
            item = dict(raw)
            item["id"] = entity
            found.append(item)
    found.sort(key=lambda item: item["id"])
    return found


def _descendant_sheets(service, root):
    """Collect a sheet plus every sheet bound beneath it.

    Args:
        service: ProjectService handle to read through.
        root: Root sheet entity id.

    Returns:
        Sheet ids in the root closure (root first).
    """
    seen = [root]
    changed = True
    bindings = _bindings(service)
    while changed:
        changed = False
        for binding in bindings:
            if (
                binding.get("parent_sheet") in seen
                and binding.get("child_sheet") not in seen
            ):
                seen.append(binding.get("child_sheet"))
                changed = True
    return seen


def _ancestor_sheets(service, sheet):
    """Collect sheets above one sheet through hierarchy bindings.

    Args:
        service: ProjectService handle to read through.
        sheet: Sheet entity id to walk up from.

    Returns:
        Ancestor sheet ids, nearest first.
    """
    parents = {
        binding.get("child_sheet"): binding.get("parent_sheet")
        for binding in _bindings(service)
    }
    seen = []
    current = parents.get(sheet)
    while current is not None and current not in seen:
        seen.append(current)
        current = parents.get(current)
    return seen


def _closure_instances(service, targets):
    """Collect DUT targets plus instances on descendant sheets.

    Args:
        service: ProjectService handle to read through.
        targets: Normalized targets with primary and
            additional entity ids.

    Returns:
        Entity ids in the DUT closure (targets plus
            descendant-scope instances).
    """
    sheets = set()
    for entity in [targets["primary"], *targets["additional"]]:
        payload = _instance_of(service, entity) or {}
        if payload.get("sheet"):
            sheets.update(
                _descendant_sheets(service, payload["sheet"]))
    found = {targets["primary"], *targets["additional"]}
    for entity in service.entities_with("Instance")["entities"]:
        payload = _instance_of(service, entity) or {}
        if payload.get("sheet") in sheets:
            found.add(entity)
    return found


def normalize_targets(service, targets):
    """Validate and normalize one DUT target set.

    The primary must be a circuit-instance occurrence;
    additional targets must be nonoverlapping sibling or
    descendant instances — never ancestors, the scope itself,
    or unrelated scopes.

    Args:
        service: ProjectService handle to read through.
        targets: Mapping with primary plus additional ids.

    Returns:
        Normalized mapping with primary and additional ids.

    Raises:
        ContractError: invalid_target for a missing primary or
            a non-instance target, overlapping_targets for a
            repeated DUT, illegal_scope for an ancestor or an
            unrelated scope.
    """
    if not isinstance(targets, dict) or not targets.get("primary"):
        raise ContractError(
            "invalid_target", "Testbench targets need a primary.")
    primary = targets["primary"]
    primary_payload = _instance_of(service, primary)
    if primary_payload is None:
        raise ContractError(
            "invalid_target",
            f"Primary DUT is not a circuit instance: {primary!r}.")
    additional = list(targets.get("additional") or [])
    if len(set(additional)) != len(additional) or primary in additional:
        raise ContractError(
            "overlapping_targets",
            "Additional DUT targets must not overlap the primary.")
    home = primary_payload.get("sheet")
    allowed = set(_descendant_sheets(service, home)) if home else set()
    ancestors = set(_ancestor_sheets(service, home)) if home else set()
    for entity in additional:
        payload = _instance_of(service, entity)
        if payload is None:
            raise ContractError(
                "invalid_target",
                f"Additional DUT is not an instance: {entity!r}.")
        sheet = payload.get("sheet")
        if sheet in ancestors:
            raise ContractError(
                "illegal_scope",
                f"DUT {entity!r} is an ancestor of the primary.")
        if sheet not in allowed:
            raise ContractError(
                "illegal_scope",
                f"DUT {entity!r} is outside the primary scope.")
    return {"primary": primary, "additional": additional}


def normalize_probes(service, targets, probes):
    """Validate probes against the DUT closure.

    Args:
        service: ProjectService handle to read through.
        targets: Normalized DUT targets.
        probes: Probe mappings with an entity each.

    Returns:
        Normalized probe list.

    Raises:
        ContractError: illegal_scope for a probe outside the
            DUT closure.
    """
    closure = _closure_instances(service, targets)
    kept = []
    for probe in probes or []:
        entity = (probe or {}).get("entity")
        if entity not in closure:
            raise ContractError(
                "illegal_scope",
                f"Probe {entity!r} is outside the DUT closure.")
        kept.append({"entity": entity})
    return kept


def materialize_interface(service, targets):
    """Materialize the target interface from symbol definitions.

    Only symbol-defined pins appear with their occurrence; symbols
    that do not resolve stay pin-less instead of invented.

    Args:
        service: ProjectService handle to read through.
        targets: Normalized DUT targets.

    Returns:
        Interface with pins ([{occurrence, pin}]) and digest.
    """
    symbols = {}
    for entity in service.entities_with("Symbol")["entities"]:
        try:
            raw = service.get_component(entity, "Symbol")["data"]
        except Exception:  # noqa: BLE001 — skip unreadable rows
            continue
        if isinstance(raw, dict) and raw.get("name"):
            symbols[raw["name"]] = raw.get("pins") or []
    pins = []
    for entity in [targets["primary"], *targets["additional"]]:
        payload = _instance_of(service, entity) or {}
        for pin in symbols.get(payload.get("symbol", ""), []):
            if isinstance(pin, dict) and pin.get("name"):
                pins.append(
                    {"occurrence": entity, "pin": pin["name"]})
    interface = {"pins": pins}
    interface["digest"] = digest_mapping(interface)
    return interface


def dut_digest(service, targets):
    """Digest the DUT occurrence set plus its live revisions.

    Args:
        service: ProjectService handle to read through.
        targets: Normalized DUT targets.

    Returns:
        Digest pinning occurrences, payloads, and revisions.
    """
    members = [targets["primary"], *targets["additional"]]
    payloads = {
        entity: (_instance_of(service, entity) or {}) for entity in members
    }
    revisions = {
        entity: read_entity_revision(service, entity)
        for entity in members
    }
    return digest_mapping(
        {"payloads": payloads, "revisions": revisions})


def _record(service, bench):
    """Read one testbench record payload.

    Args:
        service: ProjectService handle to read through.
        bench: Testbench entity id.

    Returns:
        Testbench record mapping.
    """
    return service.get_component(bench, TESTBENCH_COMPONENT)["data"]


def check_fresh(service, bench):
    """Check whether one testbench link is still fresh.

    Args:
        service: ProjectService handle to read through.
        bench: Testbench entity id.

    Returns:
        (fresh, reasons) with stale reason strings (dut,
            template, hierarchy) when the link drifted.
    """
    record = _record(service, bench)
    reasons = []
    targets = record.get("targets") or {}
    try:
        current = dut_digest(service, targets)
    except Exception:  # noqa: BLE001 — unreadable DUT reads stale
        return False, ["dut"]
    if current != record.get("dut_digest"):
        reasons.append("dut")
    members = [targets.get("primary"), *(targets.get("additional") or [])]
    for entity in members:
        try:
            live = read_entity_revision(service, entity)
        except Exception:  # noqa: BLE001 — a lost DUT reads stale
            reasons.append("hierarchy")
            break
        pinned = (record.get("dut_revisions") or {}).get(entity)
        if pinned is not None and pinned != live:
            reasons.append("hierarchy")
            break
    if (record.get("template") or {}).get(
            "template_version") != TEMPLATE_VERSION:
        reasons.append("template")
    return (not reasons), sorted(set(reasons))


def assert_runnable(service, bench):
    """Refuse to run a stale testbench link.

    Args:
        service: ProjectService handle to read through.
        bench: Testbench entity id.

    Returns:
        True when the link is fresh.

    Raises:
        ContractError: stale_link naming the drift reasons.
    """
    fresh, reasons = check_fresh(service, bench)
    if not fresh:
        raise ContractError(
            "stale_link",
            f"Testbench {bench!r} drifted ({', '.join(reasons)}); "
            "regenerate before running.")
    return True


def create_block(service, request_id, command_text, name, kind,
                 targets, probes, harness, template=None,
                 expected_revision=None):
    """Create one scoped testbench block with editable source.

    Validates the DUT scope, materializes the interface, renders
    the template source, stores the record, and saves the source
    as a project document. The harness binding rides verbatim —
    never ambient parent inclusion.

    Args:
        service: ProjectService handle to write through.
        request_id: Inner client envelope id.
        command_text: Inner command text for identity comparison.
        name: Block name (source saved as testbench/<name>.<ext>).
        kind: Template kind (spice, hdl, or cocotb).
        targets: DUT target set (primary plus additional).
        probes: Probe mappings inside the DUT closure.
        harness: Explicit harness binding mapping.
        template: Reserved template override (unused; the kind
            selects the template).
        expected_revision: Revision the writer read.

    Returns:
        Receipt with testbench id, name, kind, source path,
            DUT digest, and freshness.

    Raises:
        ContractError: invalid_kind, invalid_target,
            overlapping_targets, illegal_scope, or whatever the
            service raises.
    """
    del template
    describe_template(kind)
    normalized = normalize_targets(service, targets)
    kept_probes = normalize_probes(service, normalized, probes)
    digest = dut_digest(service, normalized)
    interface = materialize_interface(service, normalized)
    rendered = render(kind, interface, dict(harness or {}))
    path = f"{SOURCE_PREFIX}{name}.{TEMPLATE_EXTENSIONS[kind]}"
    members = [normalized["primary"], *normalized["additional"]]
    revisions = {
        entity: read_entity_revision(service, entity)
        for entity in members
    }
    created = service.create_entity(
        request_id, command_text, kind="testbench",
        components={
            TESTBENCH_COMPONENT: {
                "name": name, "kind": kind,
                "targets": normalized, "probes": kept_probes,
                "harness": dict(harness or {}),
                "interface": interface, "dut_digest": digest,
                "dut_revisions": revisions,
                "template": rendered["provenance"],
                "source": rendered["source"],
                "source_path": path,
                "candidate_source": None,
                "candidate_digest": None,
                "adopted": False, "fresh": True,
            }
        },
        expected_revision=expected_revision,
    )
    service.write_doc(
        path, rendered["source"],
        f"{request_id}:source", f"{command_text}\n#inner source",
        expected_revision=created["current_revision"],
    )
    return {
        "testbench": created["entity"], "name": name, "kind": kind,
        "source_path": path, "dut_digest": digest,
        "current_revision": created["current_revision"],
        "fresh": True,
    }


def regenerate_block(service, request_id, command_text, testbench,
                     expected_revision=None):
    """Regenerate one block to a candidate without overwriting edits.

    A fresh link returns a noop receipt; a drifted link renders
    the candidate from the current interface and stores it
    beside the edited live source for explicit adoption.

    Args:
        service: ProjectService handle to write through.
        request_id: Inner client envelope id.
        command_text: Inner command text for identity comparison.
        testbench: Testbench entity id.
        expected_revision: Revision the writer read.

    Returns:
        Noop receipt when fresh, else the candidate source,
            digest, drift reasons, and live-source diff flag.

    Raises:
        Exception: Whatever the service raises.
    """
    record = _record(service, testbench)
    fresh, reasons = check_fresh(service, testbench)
    normalized = normalize_targets(service, record.get("targets"))
    if fresh:
        return {"testbench": testbench, "noop": True, "fresh": True}
    interface = materialize_interface(service, normalized)
    rendered = render(
        record.get("kind"), interface, record.get("harness") or {})
    digest = dut_digest(service, normalized)
    service.set_component(
        testbench, TESTBENCH_COMPONENT,
        {**record, "candidate_source": rendered["source"],
         "candidate_digest": rendered["digest"],
         "dut_digest": digest, "fresh": False},
        request_id, command_text,
        expected_revision=expected_revision,
    )
    return {
        "testbench": testbench, "fresh": False,
        "stale_reasons": reasons,
        "candidate_source": rendered["source"],
        "candidate_digest": rendered["digest"],
        "differs_from_live":
            rendered["source"] != record.get("source"),
    }


def describe_block(service, bench):
    """Describe one block with freshness and closure pins.

    Args:
        service: ProjectService handle to read through.
        bench: Testbench entity id.

    Returns:
        Record plus freshness, stale reasons, port bindings,
            interface digest, template provenance, and the I28
            closure pin.
    """
    record = dict(_record(service, bench))
    fresh, reasons = check_fresh(service, bench)
    record["fresh"] = fresh
    record["stale_reasons"] = reasons
    record["port_bindings"] = [
        {"occurrence": pin.get("occurrence"), "pin": pin.get("pin")}
        for pin in (record.get("interface") or {}).get("pins", [])
    ]
    record["interface_digest"] = (
        record.get("interface") or {}).get("digest")
    record["i28"] = {
        "revision": service.snapshot()["current_revision"],
        "dut_revisions": record.get("dut_revisions"),
        "template": record.get("template"),
        "digest": digest_mapping({
            "dut": record.get("dut_digest"),
            "template": record.get("template"),
            "source": record.get("source"),
        }),
    }
    return record


def harness_instances(record):
    """List harness-owned instances excluded from production output.

    Args:
        record: Testbench record mapping.

    Returns:
        Harness instance ids (explicit binding only).
    """
    harness = record.get("harness") or {}
    return list(harness.get("instances") or [])


def design_net_pins(record, net_pins):
    """Filter harness instances out of production net pins.

    Args:
        record: Testbench record mapping.
        net_pins: Materialized [{instance, pin, net}] rows.

    Returns:
        Rows excluding harness-owned instances (adopted blocks
            return every row unchanged).
    """
    if record.get("adopted"):
        return list(net_pins or [])
    excluded = set(harness_instances(record))
    return [
        row for row in net_pins or []
        if row.get("instance") not in excluded
    ]


def excluded_harness_instances(service):
    """Collect harness-owned instances across all testbenches.

    Args:
        service: ProjectService handle to read through.

    Returns:
        Harness instance ids excluded from production output.
    """
    from ..errors import ProjectError as _ProjectError

    excluded = set()
    for bench in service.entities_with(
            TESTBENCH_COMPONENT)["entities"]:
        try:
            record = service.get_component(
                bench, TESTBENCH_COMPONENT)["data"]
        except _ProjectError:
            continue
        excluded.update(harness_instances(record))
    return excluded


def probe_simulator(kind):
    """Probe the simulator binary for one testbench kind.

    Absent simulators report BLOCKED-needs-host with a remedy —
    never a faked PASS.

    Args:
        kind: Testbench kind (spice, hdl, or cocotb).

    Returns:
        Probe with kind, tool, available flag, and verdict
            (ready or BLOCKED-needs-host) plus remedy text.
    """
    tool = SIMULATOR_TOOLS.get(kind, kind)
    if tool == "cocotb":
        available = importlib.util.find_spec("cocotb") is not None
    else:
        available = shutil.which(tool) is not None
    if available:
        return {"kind": kind, "tool": tool, "available": True,
                "verdict": "ready"}
    return {
        "kind": kind, "tool": tool, "available": False,
        "verdict": "BLOCKED-needs-host",
        "remedy": (
            f"Install {tool} on PATH (or provision the sim profile) "
            "and rerun; testbench simulation stays gated until then."
        ),
    }
