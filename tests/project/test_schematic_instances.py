"""SCHEMATIC-EDIT RED: instances lane does not exist yet.

Instances are durable entities carrying the Instance component
({sheet, symbol, x, y, rotation, mirror, properties, ref}).
Bare symbol names must resolve to a project Symbol; scoped refs
(pdk:/lib:/pkg:) pass through as immutable upstream references.
"""

import copy

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


def _seed_sheet(store, name="top"):
    holder = store.create_entity("alice", "sheet holder")["id"]
    store.attach_component(
        "alice", holder, "Sheet", {"name": name, "title": ""},
        "seed sheet",
    )
    return holder


def _seed_symbol(store, name="opamp"):
    holder = store.create_entity("alice", "symbol holder")["id"]
    store.attach_component(
        "alice", holder, "Symbol",
        {"name": name, "pins": [], "graphics": [],
         "properties": {}, "revision": 1},
        "seed symbol",
    )
    return holder


def _instances():
    from rocket_engine.project.schematic import instances  # RED: missing

    return instances


def test_place_move_rotate_mirror_round_trip():
    instances = _instances()
    store = FakeStore()
    sheet = _seed_sheet(store)
    _seed_symbol(store)
    made = instances.place_instance(
        store, "alice", sheet, "opamp", 10, 20,
        properties={"footprint": "soic8"},
    )
    moved = instances.move_instance(store, "alice", made["instance"], 30, 40)
    assert moved["revision"] is not None
    rotated = instances.rotate_instance(
        store, "alice", made["instance"], 90
    )
    assert rotated["rotation"] == 90
    mirrored = instances.mirror_instance(store, "alice", made["instance"])
    assert mirrored["mirror"] is True
    got = instances.get_instance(store, made["instance"])
    assert (got["x"], got["y"]) == (30, 40)
    assert got["properties"] == {"footprint": "soic8"}


def test_place_on_missing_sheet_fails_loud():
    instances = _instances()
    store = FakeStore()
    with pytest.raises(ContractError) as caught:
        instances.place_instance(store, "alice", "e999", "opamp", 0, 0)
    assert caught.value.code == "unknown_sheet"


def test_bare_symbol_must_exist_but_scoped_refs_pass_through():
    instances = _instances()
    store = FakeStore()
    _seed_sheet(store)
    with pytest.raises(ContractError) as caught:
        instances.place_instance(store, "alice", "e1", "ghost", 0, 0)
    assert caught.value.code == "unknown_symbol"
    scoped = instances.place_instance(
        store, "alice", "e1", "pdk:sky130:opamp", 0, 0
    )
    assert scoped["instance"]


def test_bad_rotation_and_shape_rejected():
    instances = _instances()
    store = FakeStore()
    _seed_sheet(store)
    _seed_symbol(store)
    with pytest.raises(ContractError) as caught:
        instances.place_instance(
            store, "alice", "e1", "opamp", 0, 0, rotation=45
        )
    assert caught.value.code == "invalid_instance"
    with pytest.raises(ContractError) as caught:
        instances.validate_instance(
            {"sheet": "e1", "symbol": "opamp", "x": 1.5, "y": 0,
             "rotation": 0, "mirror": False, "properties": {},
             "ref": ""}
        )
    assert caught.value.code == "invalid_instance"


def test_set_ref_properties_and_delete():
    instances = _instances()
    store = FakeStore()
    _seed_sheet(store)
    _seed_symbol(store)
    made = instances.place_instance(store, "alice", "e1", "opamp", 0, 0)
    instances.set_instance_ref(store, "alice", made["instance"], "U1")
    instances.set_instance_properties(
        store, "alice", made["instance"], {"gain": "10"}
    )
    got = instances.get_instance(store, made["instance"])
    assert got["ref"] == "U1"
    assert got["properties"] == {"gain": "10"}
    assert len(instances.instances_on_sheet(store, "e1")) == 1
    instances.delete_instance(store, "alice", made["instance"])
    assert instances.instances_on_sheet(store, "e1") == []
    with pytest.raises(ContractError) as caught:
        instances.get_instance(store, made["instance"])
    assert caught.value.code == "unknown_instance"
