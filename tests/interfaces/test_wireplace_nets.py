"""WIRE-PLACE nets: extraction glue, materialization, emitter parity.

Builds pin-to-pin worlds through the wire ops, materializes stable
Net entities under the shared net_name() authority, and proves the
ticket acceptance loop: place -> wire -> net -> SPICE names -> ERC
-> rewind removes wire + net cleanly.
"""

import pytest

from rocket_engine.interfaces.wireplace import (
    RULE_DANGLING_ENDPOINT,
    collect_wire_erc,
    connect_endpoint,
    delete_wire,
    materialize_nets,
    place_junction,
    place_wire,
    split_wire,
    world_schematic,
)
from tests.interfaces.test_wireplace import FakeEntityStore


@pytest.fixture()
def store():
    return FakeEntityStore()


def _pin(store, instance, pin, xy):
    entity = store.create_entity("agent", "test pin")["id"]
    return {"entity": entity, "instance": instance, "pin": pin, "xy": xy}


def _wire(store, points, layer, ref_a=None, ref_b=None):
    return place_wire(
        store, "agent", [points], layer,
        [{"ref": ref_a, "xy": list(points[0])},
         {"ref": ref_b, "xy": list(points[-1])}],
    )["wire"]


def test_world_schematic_carries_wires_pins_labels(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
          second["entity"])
    view = world_schematic(
        store, [first, second], labels=[{"name": "SIG", "xy": [5, 0]}]
    )
    schematic = view["schematic"]
    assert schematic["cell"] == "top"
    assert schematic["wires"] == [[[0, 0], [10, 0]]]
    assert schematic["labels"] == [{"name": "SIG", "xy": [5, 0]}]
    assert {p["instance"] for p in schematic["pins"]} == {"X1", "X2"}
    assert view["unresolved"] == []


def test_world_schematic_rejects_duplicate_pin_entities(store):
    pin = _pin(store, "X1", "A", [0, 0])
    from rocket_engine.interfaces.errors import ContractError
    with pytest.raises(ContractError) as excinfo:
        world_schematic(store, [pin, dict(pin)])
    assert excinfo.value.code == "invalid_pin"


def test_materialize_creates_one_net_for_pin_to_pin(store):
    from rocket_engine.workflows.connectgraph import (
        prepare_netlist_structs,
    )

    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    wire = _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
                 second["entity"])
    receipt = materialize_nets(store, "agent", [first, second])
    assert receipt["op"] == "materialize_nets"
    assert sorted(receipt["nets"]) == ["net1"]
    net_id = receipt["nets"]["net1"]
    stored = store.get_component(net_id, "Net")
    assert stored["name"] == "net1"
    assert stored["members"]["pins"] == [
        {"instance": "X1", "pin": "A"},
        {"instance": "X2", "pin": "A"},
    ]
    assert stored["members"]["wires"] == [wire]
    assert stored["has_wires"] is True
    view = world_schematic(store, [first, second])
    structs = prepare_netlist_structs(view["schematic"])
    assert structs.connectivity.net_name(0) == stored["name"]
    assert receipt["revision"] == store.revision


def test_materialize_keeps_stable_ids_across_runs(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
          second["entity"])
    first_run = materialize_nets(store, "agent", [first, second])
    second_run = materialize_nets(store, "agent", [first, second])
    assert first_run["nets"] == second_run["nets"]
    assert second_run["created"] == []
    assert second_run["updated"] == []


def test_materialize_names_follow_labels_like_the_emitter(store):
    from rocket_engine.workflows.connectgraph import (
        prepare_netlist_structs,
    )
    from rocket_engine.workflows.connectgraph_emit import to_raw_ir

    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
          second["entity"])
    receipt = materialize_nets(
        store, "agent", [first, second],
        labels=[{"name": "VDD", "xy": [5, 0]}],
    )
    assert sorted(receipt["nets"]) == ["VDD"]
    net_id = receipt["nets"]["VDD"]
    stored = store.get_component(net_id, "Net")
    assert stored["members"]["labels"] == ["VDD"]
    view = world_schematic(
        store, [first, second], labels=[{"name": "VDD", "xy": [5, 0]}]
    )
    structs = prepare_netlist_structs(view["schematic"])
    raw = to_raw_ir(structs)
    assert [n["name"] for n in raw["nets"]] == ["VDD"]
    assert structs.connectivity.net_name(0) == stored["name"]


def test_junction_tap_joins_two_wires_into_one_net(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 10])
    trunk = _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"])
    tap_point = [4, 0]
    split = split_wire(store, "agent", trunk, tap_point)
    junction = split["junction"]
    branch = _wire(store, [[4, 0], [10, 10]], "metal1", junction,
                   second["entity"])
    assert branch != trunk
    receipt = materialize_nets(store, "agent", [first, second])
    assert sorted(receipt["nets"]) == ["net1"]
    stored = store.get_component(receipt["nets"]["net1"], "Net")
    assert stored["members"]["pins"] == [
        {"instance": "X1", "pin": "A"},
        {"instance": "X2", "pin": "A"},
    ]
    assert sorted(stored["members"]["wires"]) == sorted(
        [trunk, split["new_wire"], branch]
    )
    assert stored["members"]["junctions"] == [junction]


def test_crossing_wires_without_junction_stay_apart(store):
    first = _pin(store, "X1", "A", [0, 5])
    second = _pin(store, "X2", "A", [10, 5])
    third = _pin(store, "X3", "A", [5, 0])
    fourth = _pin(store, "X4", "A", [5, 10])
    _wire(store, [[0, 5], [10, 5]], "metal1", first["entity"],
          second["entity"])
    _wire(store, [[5, 0], [5, 10]], "metal1", third["entity"],
          fourth["entity"])
    receipt = materialize_nets(store, "agent", [first, second, third,
                                                fourth])
    assert len(receipt["nets"]) == 2


def test_net_ref_endpoint_taps_a_net_by_name(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
          second["entity"])
    first_run = materialize_nets(
        store, "agent", [first, second],
        labels=[{"name": "SIG", "xy": [5, 0]}],
    )
    net_entity = first_run["nets"]["SIG"]
    third = _pin(store, "X3", "A", [20, 20])
    _wire(store, [[20, 0], [20, 20]], "metal1", net_entity,
          third["entity"])
    receipt = materialize_nets(
        store, "agent", [first, second, third],
        labels=[{"name": "SIG", "xy": [5, 0]}],
    )
    stored = store.get_component(receipt["nets"]["SIG"], "Net")
    assert stored["name"] == "SIG"
    assert receipt["nets"]["SIG"] == net_entity
    assert {"instance": "X3", "pin": "A"} in stored["members"]["pins"]


def test_materialize_prunes_nets_whose_wires_are_gone(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    wire = _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
                 second["entity"])
    before = materialize_nets(
        store, "agent", [first, second],
        labels=[{"name": "SIG", "xy": [5, 0]}],
    )
    assert sorted(before["nets"]) == ["SIG"]
    old_net = before["nets"]["SIG"]
    delete_wire(store, "agent", wire)
    receipt = materialize_nets(store, "agent", [first, second])
    assert old_net in receipt["pruned"]
    assert old_net not in store.entities_with("Net")


def test_materialize_records_unresolved_refs(store):
    first = _pin(store, "X1", "A", [0, 0])
    ghost = store.create_entity("agent", "doomed pin")["id"]
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"], ghost)
    store.delete_entity("agent", ghost, "test target removal")
    receipt = materialize_nets(store, "agent", [first])
    assert receipt["unresolved"] == [
        {"wire": store.entities_with("Wire")[0], "end": "b", "ref": ghost}
    ]


def test_place_wire_simulate_verdict_loop_then_rewind(store):
    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
          second["entity"])
    receipt = materialize_nets(store, "agent", [first, second])
    assert sorted(receipt["nets"]) == ["net1"]
    verdict = collect_wire_erc(store, [first, second])
    assert [f for f in verdict if f["rule"] == RULE_DANGLING_ENDPOINT] == []
    store.rewind(0)
    assert store.entities_with("Wire") == []
    assert store.entities_with("Net") == []


def test_dangling_wire_keeps_its_net_visible_to_erc(store):
    from rocket_engine.workflows.connectgraph import (
        erc_findings,
        prepare_netlist_structs,
    )

    first = _pin(store, "X1", "A", [0, 0])
    _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"])
    receipt = materialize_nets(store, "agent", [first])
    assert len(receipt["nets"]) == 1
    findings = collect_wire_erc(store, [first])
    assert any(f["rule"] == RULE_DANGLING_ENDPOINT for f in findings)
    view = world_schematic(store, [first])
    structs = prepare_netlist_structs(view["schematic"])
    rules = [f["rule"] for f in erc_findings(structs.connectivity)]
    assert "connectivity.dangling_net" not in rules
    assert structs.connectivity.net_name(0) in receipt["nets"]


def test_junction_dot_marks_an_explicit_tap(store):
    junction = place_junction(store, "agent", [5, 5], "metal1")["junction"]
    first = _pin(store, "X1", "A", [0, 5])
    second = _pin(store, "X2", "A", [10, 5])
    third = _pin(store, "X3", "A", [5, 0])
    _wire(store, [[0, 5], [5, 5]], "metal1", first["entity"], junction)
    _wire(store, [[5, 5], [10, 5]], "metal1", junction, second["entity"])
    _wire(store, [[5, 0], [5, 5]], "metal1", third["entity"], junction)
    receipt = materialize_nets(store, "agent", [first, second, third])
    assert sorted(receipt["nets"]) == ["net1"]
    stored = store.get_component(receipt["nets"]["net1"], "Net")
    assert stored["members"]["junctions"] == [junction]
    assert len(stored["members"]["wires"]) == 3


def test_move_wire_reshapes_nets_on_next_materialize(store):
    from rocket_engine.interfaces.wireplace import move_wire

    first = _pin(store, "X1", "A", [0, 0])
    second = _pin(store, "X2", "A", [10, 0])
    third = _pin(store, "X3", "A", [20, 0])
    wire = _wire(store, [[0, 0], [10, 0]], "metal1", first["entity"],
                 second["entity"])
    before = materialize_nets(store, "agent", [first, second, third])
    assert len(before["nets"]) == 2
    connect_endpoint(store, "agent", wire, "b", None)
    move_wire(store, "agent", wire, 0, 5)
    receipt = materialize_nets(store, "agent", [first, second, third])
    assert len(receipt["nets"]) == 4
    dangles = [
        f for f in collect_wire_erc(store, [first, second, third])
        if f["rule"] == RULE_DANGLING_ENDPOINT
    ]
    assert len(dangles) == 1
