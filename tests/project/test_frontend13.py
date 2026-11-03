"""FRONTEND-13 RED: the six engine touchpoints are missing.

Touchpoints: annotate, ERC_TESTER (+severities/pin-conflict
config), connection-graph (+net-occurrence query), netlist
write/update, ROCKET-XPROBE (+resolvePin-as-query), plot/export
(+binary-gated flow verdicts: sta/librelane absent -> loud
BLOCKED-needs-host, never faked green).
"""

import copy
import shutil

import pytest

from rocket_engine.interfaces.errors import ContractError


class FakeStore:
    """Minimal ENGINE-ECS seam stand-in (create/read/write/delete)."""

    def __init__(self):
        self._entities = {}
        self._revision = 0
        self._counter = 0

    def create_entity(self, actor, description):
        del actor, description
        self._counter += 1
        entity = f"e{self._counter}"
        self._entities[entity] = {}
        self._revision += 1
        return {"id": entity, "revision": self._revision}

    def _require(self, entity):
        try:
            return self._entities[entity]
        except KeyError:
            raise LookupError(entity) from None

    def get_component(self, entity, component):
        try:
            return copy.deepcopy(self._require(entity)[component])
        except KeyError:
            raise LookupError((entity, component)) from None

    def components_of(self, entity):
        return copy.deepcopy(self._require(entity))

    def entities_with(self, component, predicate=None):
        found = []
        for entity in sorted(self._entities):
            if component in self._entities[entity]:
                value = copy.deepcopy(self._entities[entity][component])
                if predicate is None or predicate(value):
                    found.append(entity)
        return found

    def attach_component(self, actor, entity, component, value, description):
        del actor, description
        components = self._require(entity)
        if component in components:
            raise ValueError(component)
        components[component] = copy.deepcopy(value)
        self._revision += 1
        return {"revision": self._revision}

    def set_component(self, actor, entity, component, value, description):
        del actor, description
        components = self._require(entity)
        if component not in components:
            raise LookupError(component)
        components[component] = copy.deepcopy(value)
        self._revision += 1
        return {"revision": self._revision}

    def delete_entity(self, actor, entity, description):
        del actor, description
        self._require(entity)
        del self._entities[entity]
        self._revision += 1
        return {"revision": self._revision}


def _frontend():
    from rocket_engine.project import frontend13  # RED: missing module

    return frontend13


def _seed(store):
    sheet = store.create_entity("alice", "sheet")["id"]
    store.attach_component(
        "alice", sheet, "Sheet", {"name": "top", "title": ""}, "seed"
    )
    sym = store.create_entity("alice", "symbol")["id"]
    store.attach_component(
        "alice", sym, "Symbol",
        {"name": "resistor",
         "pins": [
             {"name": "A", "pin_type": "passive", "x": 0, "y": 0},
             {"name": "B", "pin_type": "passive", "x": 20, "y": 0},
         ],
         "graphics": [], "properties": {}, "revision": 1},
        "seed",
    )
    first = store.create_entity("alice", "instance")["id"]
    store.attach_component(
        "alice", first, "Instance",
        {"sheet": sheet, "symbol": "resistor", "x": 0, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": ""},
        "seed",
    )
    second = store.create_entity("alice", "instance")["id"]
    store.attach_component(
        "alice", second, "Instance",
        {"sheet": sheet, "symbol": "resistor", "x": 50, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": "R7"},
        "seed",
    )
    return sheet, first, second


def test_annotate_assigns_stable_refs_and_is_idempotent():
    frontend13 = _frontend()
    store = FakeStore()
    _seed(store)
    receipt = frontend13.annotate(store, "alice", prefixes={"resistor": "R"})
    assert [a["ref"] for a in receipt["annotated"]] == ["R8"]
    assert receipt["unannotated"] == []
    again = frontend13.annotate(store, "alice", prefixes={"resistor": "R"})
    assert again["annotated"] == []
    mystery = store.create_entity("alice", "instance")["id"]
    store.attach_component(
        "alice", mystery, "Instance",
        {"sheet": "e1", "symbol": "mystery", "x": 0, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": ""},
        "seed",
    )
    third = frontend13.annotate(store, "alice", prefixes={"resistor": "R"})
    assert [u["symbol"] for u in third["unannotated"]] == ["mystery"]


def test_erc_tester_flags_duplicates_and_unknowns():
    frontend13 = _frontend()
    store = FakeStore()
    _seed(store)
    dupe = store.create_entity("alice", "instance")["id"]
    store.attach_component(
        "alice", dupe, "Instance",
        {"sheet": "e1", "symbol": "ghost_sym", "x": 0, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": "R7"},
        "seed",
    )
    report = frontend13.erc_check(store)
    rules = {f["rule"] for f in report["findings"]}
    assert "schematic.duplicate_ref" in rules
    assert "schematic.unknown_symbol" in rules
    assert "schematic.unannotated" in rules
    assert report["verdict"] == "fail"
    escalated = frontend13.erc_check(
        store, severities={"schematic.unannotated": "error"}
    )
    unannotated = [f for f in escalated["findings"]
                   if f["rule"] == "schematic.unannotated"]
    assert unannotated and unannotated[0]["severity"] == "error"


def test_erc_pin_conflicts_honor_config():
    frontend13 = _frontend()
    store = FakeStore()
    net_pins = [
        {"instance": "e3", "pin": "OUT", "net": "n1", "pin_type": "output"},
        {"instance": "e4", "pin": "OUT", "net": "n1", "pin_type": "output"},
    ]
    report = frontend13.erc_check(store, net_pins=net_pins)
    conflicts = [f for f in report["findings"]
                 if f["rule"] == "schematic.pin_conflict"]
    assert len(conflicts) == 1
    assert conflicts[0]["severity"] == "error"
    downgraded = frontend13.erc_check(
        store, net_pins=net_pins,
        pin_conflict={"output-output": "warning"},
    )
    soft = [f for f in downgraded["findings"]
            if f["rule"] == "schematic.pin_conflict"]
    assert soft[0]["severity"] == "warning"


def test_connection_graph_and_net_occurrences():
    frontend13 = _frontend()
    store = FakeStore()
    sheet, first, second = _seed(store)
    graph = frontend13.connection_graph(store)
    kinds = {n["kind"] for n in graph["nodes"]}
    assert {"sheet", "instance"} <= kinds
    contains = [e for e in graph["edges"] if e["rel"] == "contains"]
    assert {e["to"] for e in contains} == {first, second}
    net_pins = [
        {"instance": first, "pin": "A", "net": "VCC"},
        {"instance": second, "pin": "A", "net": "VCC"},
    ]
    occurrences = frontend13.net_occurrences(net_pins, "VCC")
    assert occurrences == [
        {"instance": first, "pin": "A"},
        {"instance": second, "pin": "A"},
    ]
    assert frontend13.net_occurrences(net_pins, "GND") == []


def test_netlist_write_needs_nets_and_update_detects_change():
    frontend13 = _frontend()
    store = FakeStore()
    _seed(store)
    with pytest.raises(ContractError) as caught:
        frontend13.write_netlist(store, language="spice")
    assert caught.value.code == "invalid_command"
    net_pins = [
        {"instance": "e3", "pin": "A", "net": "VCC"},
        {"instance": "e3", "pin": "B", "net": "GND"},
        {"instance": "e4", "pin": "A", "net": "VCC"},
        {"instance": "e4", "pin": "B", "net": "OUT"},
    ]
    spice = frontend13.write_netlist(
        store, language="spice", title="top", net_pins=net_pins
    )
    assert ".end" in spice["text"]
    assert "VCC" in spice["text"]
    verilog = frontend13.write_netlist(store, language="verilog", net_pins=net_pins)
    assert "module top" in verilog["text"]
    with pytest.raises(ContractError) as caught:
        frontend13.write_netlist(store, language="eldorado", net_pins=net_pins)
    assert caught.value.code == "invalid_language"
    same = frontend13.update_netlist(
        store, "spice", spice["text"], title="top", net_pins=net_pins
    )
    assert same["changed"] is False
    changed = frontend13.update_netlist(
        store, "spice", spice["text"], title="top",
        net_pins=net_pins + [{"instance": "e4", "pin": "B", "net": "GND"}],
    )
    assert changed["changed"] is True


def test_xprobe_resolves_pin_cell_and_net():
    frontend13 = _frontend()
    store = FakeStore()
    _seed(store)
    cell = store.create_entity("alice", "cell")["id"]
    store.attach_component(
        "alice", cell, "Cell",
        {"name": "res_cell",
         "ports": [{"name": "A", "x": 0, "y": 0, "layer": "met1"}],
         "properties": {}, "revision": 1},
        "seed",
    )
    link = store.create_entity("alice", "linkage")["id"]
    store.attach_component(
        "alice", link, "Linkage",
        {"symbol": "resistor", "cell": "res_cell",
         "pin_map": [{"symPin": "A", "cellPin": "A"}],
         "revision": 1},
        "seed",
    )
    net_pins = [{"instance": "e3", "pin": "A", "net": "VCC"}]
    probe = frontend13.xprobe(store, "e3", "A", net_pins=net_pins)
    assert probe["symbol"] == "resistor"
    assert probe["cell"] == "res_cell"
    assert probe["cell_pin"] == "A"
    assert probe["net"] == "VCC"
    assert probe["net_known"] is True
    dangling = frontend13.xprobe(store, "e3", "B")
    assert dangling["net"] is None
    assert dangling["net_known"] is False
    with pytest.raises(ContractError) as caught:
        frontend13.xprobe(store, "e999", "A")
    assert caught.value.code == "unknown_instance"


def test_plot_export_formats_and_rejects_unknown():
    frontend13 = _frontend()
    store = FakeStore()
    _seed(store)
    svg = frontend13.plot_export(store, format="svg")
    assert svg["content"].startswith("<svg")
    assert "R7" in svg["content"]
    drawing = frontend13.plot_export(store, format="json")
    assert drawing["content"]["instances"]
    with pytest.raises(ContractError) as caught:
        frontend13.plot_export(store, format="png")
    assert caught.value.code == "invalid_format"


def test_binary_gated_flows_report_blocked_never_green():
    frontend13 = _frontend()
    sta_gate = frontend13.flow_gate("sta")
    assert sta_gate["tool"] == "sta"
    if shutil.which("sta") is None:
        assert sta_gate["verdict"] == "BLOCKED-needs-host"
        assert sta_gate["available"] is False
        assert "remedy" in sta_gate and sta_gate["remedy"]
    else:
        assert sta_gate["verdict"] == "ready"
    librelane_gate = frontend13.flow_gate("librelane")
    assert librelane_gate["tool"] == "librelane"
    assert librelane_gate["verdict"] in ("ready", "BLOCKED-needs-host")
    if librelane_gate["verdict"] == "BLOCKED-needs-host":
        assert librelane_gate["remedy"]
    with pytest.raises(ContractError) as caught:
        frontend13.flow_gate("eldorado")
    assert caught.value.code == "unknown_tool"
