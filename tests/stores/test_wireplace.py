"""WIRE-PLACE ops: schemas, wire/junction verbs, ERC. RED-first.

Exercises rocket_engine.stores.wireplace through FakeEntityStore,
an in-memory stand-in for the ENGINE-ECS entity store seam (exact
interface request lives in docs/work/WIRE-PLACE/report.md). The fake
adds only rewind(), which the real ledger owns — it exists here to
prove every op lands in exactly one revision.
"""

import copy

import pytest

from rocket_engine.interfaces.errors import ContractError
from rocket_engine.stores.wireplace import (
    DEFAULT_WIRE_POLICY,
    RULE_DANGLING_ENDPOINT,
    RULE_ORPHAN_JUNCTION,
    RULE_STALE_GEOMETRY,
    RULE_UNKNOWN_REF,
    collect_wire_erc,
    connect_endpoint,
    delete_junction,
    delete_wire,
    move_wire,
    place_junction,
    place_wire,
    split_wire,
    validate_junction,
    validate_net,
    validate_pin,
    validate_wire,
)


class FakeEntityStore:
    """In-memory entity store implementing the requested seam."""

    def __init__(self):
        self._entities = {}
        self._revision = 0
        self._events = []
        self._snapshots = {0: ({}, [])}
        self._counter = 0

    @property
    def revision(self):
        return self._revision

    def _snapshot(self):
        self._snapshots[self._revision] = (
            copy.deepcopy(self._entities), list(self._events),
        )

    def _bump(self):
        self._revision += 1
        self._snapshot()
        return self._revision

    def create_entity(self, actor, description):
        self._counter += 1
        entity = f"e{self._counter}"
        self._entities[entity] = {}
        revision = self._bump()
        event = {
            "event": "entity_created", "entity": entity,
            "revision": revision, "actor": actor,
        }
        self._events.append(event)
        self._snapshot()
        return {"id": entity, "revision": revision}

    def _require(self, entity):
        try:
            return self._entities[entity]
        except KeyError:
            raise LookupError(f"Unknown entity: {entity!r}.") from None

    def get_component(self, entity, component):
        try:
            return copy.deepcopy(self._require(entity)[component])
        except KeyError:
            raise LookupError(
                f"Unknown component {component!r} on {entity!r}."
            ) from None

    def _mutate(self, actor, entity, component, value, kind, event):
        components = self._require(entity)
        if kind == "set" and component not in components:
            raise LookupError(
                f"Unknown component {component!r} on {entity!r}."
            )
        if kind == "attach" and component in components:
            raise ValueError(f"Component already attached: {component!r}.")
        if kind == "detach" and component not in components:
            raise LookupError(
                f"Unknown component {component!r} on {entity!r}."
            )
        if kind == "detach":
            del components[component]
        else:
            components[component] = copy.deepcopy(value)
        revision = self._bump()
        record = {
            "event": event, "entity": entity, "component": component,
            "revision": revision, "actor": actor,
        }
        self._events.append(record)
        self._snapshot()
        return {"revision": revision}

    def set_component(self, actor, entity, component, value, description):
        return self._mutate(
            actor, entity, component, value, "set", "component_changed"
        )

    def attach_component(self, actor, entity, component, value, description):
        return self._mutate(
            actor, entity, component, value, "attach", "component_changed"
        )

    def detach_component(self, actor, entity, component, description):
        return self._mutate(
            actor, entity, component, None, "detach", "component_changed"
        )

    def delete_entity(self, actor, entity, description):
        self._require(entity)
        del self._entities[entity]
        revision = self._bump()
        event = {
            "event": "entity_deleted", "entity": entity,
            "revision": revision, "actor": actor,
        }
        self._events.append(event)
        self._snapshot()
        return {"revision": revision}

    def components_of(self, entity):
        return copy.deepcopy(self._require(entity))

    def entities_with(self, component, predicate=None):
        found = []
        for entity in sorted(self._entities):
            if component in self._entities[entity]:
                value = self._entities[entity][component]
                if predicate is None or predicate(copy.deepcopy(value)):
                    found.append(entity)
        return found

    def _resolve(self, node, aliases):
        if isinstance(node, dict) and set(node) == {"alias"}:
            return aliases[node["alias"]]
        if isinstance(node, dict):
            return {k: self._resolve(v, aliases) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve(v, aliases) for v in node]
        return node

    def transact(self, actor, description, calls):
        saved = (
            copy.deepcopy(self._entities), list(self._events),
            self._revision, self._counter,
        )
        aliases = {}
        events = []
        try:
            for call in calls:
                verb = call["verb"]
                args = self._resolve(dict(call.get("args", {})), aliases)
                if verb == "create_entity":
                    self._counter += 1
                    entity = f"e{self._counter}"
                    self._entities[entity] = {}
                    events.append({"event": "entity_created", "entity": entity})
                    if "alias" in call:
                        aliases[call["alias"]] = entity
                elif verb in ("set_component", "attach_component"):
                    entity = args["entity"]
                    component = args["component"]
                    components = self._require(entity)
                    if verb == "set_component" and component not in components:
                        raise LookupError(f"Unknown component {component!r}.")
                    if verb == "attach_component" and component in components:
                        raise ValueError("Component already attached.")
                    components[component] = copy.deepcopy(args["value"])
                    events.append({
                        "event": "component_changed", "entity": entity,
                        "component": component,
                    })
                elif verb == "detach_component":
                    entity = args["entity"]
                    component = args["component"]
                    del self._require(entity)[component]
                    events.append({
                        "event": "component_changed", "entity": entity,
                        "component": component,
                    })
                elif verb == "delete_entity":
                    entity = args["entity"]
                    self._require(entity)
                    del self._entities[entity]
                    events.append({"event": "entity_deleted", "entity": entity})
                else:
                    raise ValueError(f"Unknown verb: {verb!r}.")
        except (LookupError, ValueError, KeyError):
            (self._entities, self._events, self._revision, self._counter) = saved
            raise
        revision = self._bump()
        for event in events:
            event["revision"] = revision
            event["actor"] = actor
        self._events.extend(events)
        self._snapshot()
        return {"revision": revision, "aliases": aliases, "events": events}

    def events_since(self, cursor):
        return [e for e in self._events if e["revision"] > cursor]

    def rewind(self, target_revision):
        """Test-only ledger rewind: restore one revision snapshot."""
        entities, events = copy.deepcopy(self._snapshots[target_revision])
        self._entities = entities
        self._events = events
        self._revision = target_revision


@pytest.fixture()
def store():
    return FakeEntityStore()


def _pin_entity(store, actor="agent"):
    return store.create_entity(actor, "test pin")["id"]


def _wire_value(ref_a=None, ref_b=None):
    return {
        "segments": [[[0, 0], [10, 0]]],
        "layer": "metal1",
        "endpoints": [
            {"ref": ref_a, "xy": [0, 0]},
            {"ref": ref_b, "xy": [10, 0]},
        ],
    }


def _placed_wire(store, ref_a=None, ref_b=None, actor="agent"):
    value = _wire_value(ref_a, ref_b)
    receipt = place_wire(
        store, actor, value["segments"], value["layer"], value["endpoints"]
    )
    return receipt["wire"]


# Schema validation: Wire.


def test_validate_wire_accepts_dangling_endpoints():
    clean = validate_wire(_wire_value())
    assert clean == _wire_value()
    assert clean is not _wire_value()


def test_validate_wire_rejects_endpoint_xy_off_polyline_ends():
    bad = _wire_value()
    bad["endpoints"][0]["xy"] = [1, 0]
    with pytest.raises(ContractError) as excinfo:
        validate_wire(bad)
    assert excinfo.value.code == "invalid_wire"


@pytest.mark.parametrize("segments", [
    [],
    [[[0, 0]]],
    [[[0, 0], [0, 0]]],
    [[[0, 0], [1, True]]],
    [[[0, 0], ["1", 0]]],
    "not-a-list",
])
def test_validate_wire_rejects_bad_segments(segments):
    bad = {"segments": segments, "layer": "metal1",
           "endpoints": [{"ref": None, "xy": [0, 0]}] * 2}
    with pytest.raises(ContractError) as excinfo:
        validate_wire(bad)
    assert excinfo.value.code == "invalid_wire"


def test_validate_wire_rejects_bad_layer_and_endpoints():
    good = _wire_value()
    for mutate in (
        lambda v: v.update(layer=""),
        lambda v: v.update(layer=7),
        lambda v: v.update(endpoints=[v["endpoints"][0]]),
        lambda v: v["endpoints"][0].update(ref=7),
        lambda v: v.update(extra=1),
    ):
        bad = copy.deepcopy(good)
        mutate(bad)
        with pytest.raises(ContractError) as excinfo:
            validate_wire(bad)
        assert excinfo.value.code == "invalid_wire"


# Schema validation: Junction / Net / Pin.


def test_validate_junction_round_trip():
    assert validate_junction({"xy": [3, 4], "layer": "metal1"}) == {
        "xy": [3, 4], "layer": "metal1",
    }
    for bad in ({"xy": [3, 4], "layer": ""}, {"xy": [3], "layer": "m"},
                {"xy": [3, 4]}, "dot"):
        with pytest.raises(ContractError) as excinfo:
            validate_junction(bad)
        assert excinfo.value.code == "invalid_junction"


def test_validate_net_round_trip():
    net = {
        "name": "net1",
        "extraction": {"cell": "top", "net_ids": [0]},
        "members": {"pins": [], "labels": [], "wires": ["e1"],
                    "junctions": []},
        "has_wires": True,
    }
    assert validate_net(net) == net
    bad = copy.deepcopy(net)
    bad["members"]["wires"] = ["e2", "e1"]
    with pytest.raises(ContractError) as excinfo:
        validate_net(bad)
    assert excinfo.value.code == "invalid_net"


def test_validate_pin_round_trip():
    pin = {"entity": "e1", "instance": "X1", "pin": "A", "xy": [0, 0]}
    assert validate_pin(pin) == pin
    bad = dict(pin, entity="")
    with pytest.raises(ContractError) as excinfo:
        validate_pin(bad)
    assert excinfo.value.code == "invalid_pin"


# place_wire / place_junction.


def test_place_wire_is_one_attributed_revision(store):
    pin = _pin_entity(store)
    before = store.revision
    receipt = place_wire(
        store, "agent", [[[0, 0], [10, 0]]], "metal1",
        [{"ref": pin, "xy": [0, 0]}, {"ref": None, "xy": [10, 0]}],
    )
    assert receipt["op"] == "place_wire"
    assert receipt["actor"] == "agent"
    assert receipt["revision"] == before + 1
    stored = store.get_component(receipt["wire"], "Wire")
    assert stored["endpoints"][0]["ref"] == pin
    kinds = [e["event"] for e in receipt["events"]]
    assert kinds == ["entity_created", "component_changed"]
    assert all(e["actor"] == "agent" for e in receipt["events"])


def test_place_wire_rejects_unknown_and_wire_refs(store):
    with pytest.raises(ContractError) as excinfo:
        place_wire(store, "agent", [[[0, 0], [1, 0]]], "m1",
                   [{"ref": "e999", "xy": [0, 0]},
                    {"ref": None, "xy": [1, 0]}])
    assert excinfo.value.code == "unknown_ref"
    wire = _placed_wire(store)
    with pytest.raises(ContractError) as excinfo:
        place_wire(store, "agent", [[[0, 0], [1, 0]]], "m1",
                   [{"ref": wire, "xy": [0, 0]},
                    {"ref": None, "xy": [1, 0]}])
    assert excinfo.value.code == "invalid_ref"


def test_place_wire_rejects_empty_actor(store):
    with pytest.raises(ContractError) as excinfo:
        place_wire(store, "", [[[0, 0], [1, 0]]], "m1",
                   [{"ref": None, "xy": [0, 0]},
                    {"ref": None, "xy": [1, 0]}])
    assert excinfo.value.code == "invalid_actor"


def test_place_junction(store):
    receipt = place_junction(store, "agent", [5, 0], "metal1")
    assert receipt["op"] == "place_junction"
    assert store.get_component(receipt["junction"], "Junction") == {
        "xy": [5, 0], "layer": "metal1",
    }


# connect_endpoint.


def test_connect_endpoint_moves_ref(store):
    pin = _pin_entity(store)
    junction = place_junction(store, "agent", [10, 0], "metal1")["junction"]
    wire = _placed_wire(store, ref_a=pin)
    receipt = connect_endpoint(store, "agent", wire, "b", junction)
    assert receipt["revision"] == store.revision
    stored = store.get_component(wire, "Wire")
    assert stored["endpoints"][1] == {"ref": junction, "xy": [10, 0]}
    assert stored["endpoints"][0]["ref"] == pin


def test_connect_endpoint_noop_keeps_revision(store):
    pin = _pin_entity(store)
    wire = _placed_wire(store, ref_a=pin)
    before = store.revision
    receipt = connect_endpoint(store, "agent", wire, "a", pin)
    assert receipt["noop"] is True
    assert receipt["revision"] is None
    assert store.revision == before


def test_connect_endpoint_rejects_bad_end_unknowns(store):
    wire = _placed_wire(store)
    with pytest.raises(ContractError) as excinfo:
        connect_endpoint(store, "agent", wire, "c", None)
    assert excinfo.value.code == "invalid_endpoint"
    with pytest.raises(ContractError) as excinfo:
        connect_endpoint(store, "agent", "e999", "a", None)
    assert excinfo.value.code == "unknown_wire"
    with pytest.raises(ContractError) as excinfo:
        connect_endpoint(store, "agent", wire, "a", "e999")
    assert excinfo.value.code == "unknown_ref"
    with pytest.raises(ContractError) as excinfo:
        connect_endpoint(store, "agent", wire, "a", wire)
    assert excinfo.value.code == "invalid_ref"


# move_wire.


def test_move_wire_translates_geometry_keeps_refs(store):
    pin = _pin_entity(store)
    wire = _placed_wire(store, ref_a=pin)
    receipt = move_wire(store, "agent", wire, 5, -5)
    assert receipt["wire"] == wire
    stored = store.get_component(wire, "Wire")
    assert stored["segments"] == [[[5, -5], [15, -5]]]
    assert stored["endpoints"] == [
        {"ref": pin, "xy": [5, -5]},
        {"ref": None, "xy": [15, -5]},
    ]


def test_move_wire_noop_and_bad_deltas(store):
    wire = _placed_wire(store)
    before = store.revision
    receipt = move_wire(store, "agent", wire, 0, 0)
    assert receipt["noop"] is True
    assert store.revision == before
    with pytest.raises(ContractError) as excinfo:
        move_wire(store, "agent", wire, 1.5, 0)
    assert excinfo.value.code == "invalid_geometry"
    with pytest.raises(ContractError) as excinfo:
        move_wire(store, "agent", "e999", 1, 0)
    assert excinfo.value.code == "unknown_wire"


# split_wire.


def test_split_wire_creates_junction_and_second_wire(store):
    wire = _placed_wire(store)
    before = store.revision
    receipt = split_wire(store, "agent", wire, [4, 0])
    assert receipt["revision"] == before + 1
    assert receipt["wire"] == wire
    junction = receipt["junction"]
    new_wire = receipt["new_wire"]
    assert store.get_component(junction, "Junction") == {
        "xy": [4, 0], "layer": "metal1",
    }
    head = store.get_component(wire, "Wire")
    assert head["segments"] == [[[0, 0], [4, 0]]]
    assert head["endpoints"] == [
        {"ref": None, "xy": [0, 0]},
        {"ref": junction, "xy": [4, 0]},
    ]
    tail = store.get_component(new_wire, "Wire")
    assert tail["segments"] == [[[4, 0], [10, 0]]]
    assert tail["endpoints"] == [
        {"ref": junction, "xy": [4, 0]},
        {"ref": None, "xy": [10, 0]},
    ]


def test_split_wire_keeps_original_endpoint_refs(store):
    pin_a = _pin_entity(store)
    pin_b = _pin_entity(store)
    wire = _placed_wire(store, ref_a=pin_a, ref_b=pin_b)
    receipt = split_wire(store, "agent", wire, [6, 0])
    head = store.get_component(wire, "Wire")
    tail = store.get_component(receipt["new_wire"], "Wire")
    assert head["endpoints"][0]["ref"] == pin_a
    assert tail["endpoints"][1]["ref"] == pin_b


@pytest.mark.parametrize("at", [[0, 0], [10, 0], [4, 1], [99, 99]])
def test_split_wire_rejects_off_path_points(store, at):
    wire = _placed_wire(store)
    with pytest.raises(ContractError) as excinfo:
        split_wire(store, "agent", wire, at)
    assert excinfo.value.code == "invalid_split"


def test_split_wire_rejects_multi_polyline(store):
    receipt = place_wire(
        store, "agent",
        [[[0, 0], [2, 0]], [[5, 5], [7, 5]]],
        "metal1",
        [{"ref": None, "xy": [0, 0]}, {"ref": None, "xy": [7, 5]}],
    )
    with pytest.raises(ContractError) as excinfo:
        split_wire(store, "agent", receipt["wire"], [1, 0])
    assert excinfo.value.code == "invalid_split"


# delete_wire / delete_junction.


def test_delete_wire_removes_entity(store):
    wire = _placed_wire(store)
    receipt = delete_wire(store, "agent", wire)
    assert receipt["wire"] == wire
    assert store.entities_with("Wire") == []
    with pytest.raises(ContractError) as excinfo:
        delete_wire(store, "agent", wire)
    assert excinfo.value.code == "unknown_wire"


def test_delete_junction_refuses_use_and_frees_orphans(store):
    junction = place_junction(store, "agent", [10, 0], "metal1")["junction"]
    wire = _placed_wire(store, ref_b=junction)
    with pytest.raises(ContractError) as excinfo:
        delete_junction(store, "agent", junction)
    assert excinfo.value.code == "junction_in_use"
    assert wire in str(excinfo.value)
    connect_endpoint(store, "agent", wire, "b", None)
    receipt = delete_junction(store, "agent", junction)
    assert receipt["junction"] == junction
    with pytest.raises(ContractError) as excinfo:
        delete_junction(store, "agent", junction)
    assert excinfo.value.code == "unknown_junction"


# ERC.


def test_erc_flags_dangling_endpoints_never_drops(store):
    wire = _placed_wire(store)
    findings = collect_wire_erc(store, [])
    dangles = [f for f in findings if f["rule"] == RULE_DANGLING_ENDPOINT]
    assert len(dangles) == 2
    assert dangles[0]["severity"] == DEFAULT_WIRE_POLICY[RULE_DANGLING_ENDPOINT]
    assert dangles[0]["wire"] == wire
    assert dangles[0]["end"] == "a"
    assert dangles[0]["xy"] == [0, 0]


def test_erc_errors_when_a_ref_target_is_deleted(store):
    pin = _pin_entity(store)
    wire = _placed_wire(store, ref_a=pin)
    store.delete_entity("agent", pin, "test target removal")
    findings = collect_wire_erc(store, [])
    errors = [f for f in findings if f["rule"] == RULE_UNKNOWN_REF]
    assert len(errors) == 1
    assert errors[0]["severity"] == "error"
    assert errors[0]["ref"] == pin
    assert errors[0]["wire"] == wire


def test_erc_flags_stale_geometry(store):
    pin = _pin_entity(store)
    wire = _placed_wire(store, ref_a=pin)
    pins = [{"entity": pin, "instance": "X1", "pin": "A", "xy": [99, 99]}]
    findings = collect_wire_erc(store, pins)
    stale = [f for f in findings if f["rule"] == RULE_STALE_GEOMETRY]
    assert len(stale) == 1
    assert stale[0]["target"] == [99, 99]
    aligned = [{"entity": pin, "instance": "X1", "pin": "A", "xy": [0, 0]}]
    again = collect_wire_erc(store, aligned)
    assert [f for f in again if f["rule"] == RULE_STALE_GEOMETRY] == []


def test_erc_flags_orphan_junctions_only(store):
    orphan = place_junction(store, "agent", [50, 50], "m1")["junction"]
    tap = place_junction(store, "agent", [5, 0], "m1")["junction"]
    _placed_wire(store)
    findings = collect_wire_erc(store, [])
    orphans = [f for f in findings if f["rule"] == RULE_ORPHAN_JUNCTION]
    assert [f["junction"] for f in orphans] == [orphan]
    assert tap not in [f["junction"] for f in orphans]


def test_erc_policy_override_and_unknown_rule(store):
    _placed_wire(store)
    findings = collect_wire_erc(
        store, [], policy={RULE_DANGLING_ENDPOINT: "error"}
    )
    assert all(f["severity"] == "error" for f in findings)
    with pytest.raises(ContractError) as excinfo:
        collect_wire_erc(store, [], policy={"wire.nope": "warning"})
    assert excinfo.value.code == "invalid_policy"
