"""SCHEMATIC-EDIT RED: hierarchy lane does not exist yet.

Hierarchy bindings link a parent sheet to a child sheet through a
block instance with an explicit port map. Navigation queries serve
the frontend tree without adapter-specific drawing state.
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


def _seed(store):
    top = store.create_entity("alice", "sheet top")["id"]
    store.attach_component(
        "alice", top, "Sheet", {"name": "top", "title": ""}, "seed"
    )
    sub = store.create_entity("alice", "sheet sub")["id"]
    store.attach_component(
        "alice", sub, "Sheet", {"name": "sub", "title": ""}, "seed"
    )
    inst = store.create_entity("alice", "block instance")["id"]
    store.attach_component(
        "alice", inst, "Instance",
        {"sheet": top, "symbol": "pdk:sub", "x": 0, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": "X1"},
        "seed",
    )
    return top, sub, inst


def _hierarchy():
    from rocket_engine.project.schematic import hierarchy  # RED: missing

    return hierarchy


def test_bind_and_navigate_tree():
    hierarchy = _hierarchy()
    store = FakeStore()
    top, sub, inst = _seed(store)
    made = hierarchy.bind_block(store, "alice", top, sub, inst)
    assert made["binding"]
    assert hierarchy.children_of(store, top) == [sub]
    assert hierarchy.parent_of(store, sub) == [top]
    tree = hierarchy.hierarchy_tree(store, top)
    assert tree["sheet"] == top
    assert [c["sheet"] for c in tree["children"]] == [sub]
    assert hierarchy.sheet_path(store, sub) == [top, sub]
    assert hierarchy.sheet_path(store, top) == [top]


def test_duplicate_binding_and_self_binding_refused():
    hierarchy = _hierarchy()
    store = FakeStore()
    top, sub, inst = _seed(store)
    hierarchy.bind_block(store, "alice", top, sub, inst)
    with pytest.raises(ContractError) as caught:
        hierarchy.bind_block(store, "alice", top, sub, inst)
    assert caught.value.code == "binding_exists"
    with pytest.raises(ContractError) as caught:
        hierarchy.bind_block(store, "alice", top, top, inst)
    assert caught.value.code == "invalid_hierarchy"


def test_missing_sheet_or_instance_fails_loud():
    hierarchy = _hierarchy()
    store = FakeStore()
    top, sub, inst = _seed(store)
    with pytest.raises(ContractError) as caught:
        hierarchy.bind_block(store, "alice", "e999", sub, inst)
    assert caught.value.code == "unknown_sheet"
    with pytest.raises(ContractError) as caught:
        hierarchy.bind_block(store, "alice", top, sub, "e999")
    assert caught.value.code == "unknown_instance"


def test_port_map_set_and_unbind():
    hierarchy = _hierarchy()
    store = FakeStore()
    top, sub, inst = _seed(store)
    made = hierarchy.bind_block(store, "alice", top, sub, inst)
    updated = hierarchy.set_port_map(
        store, "alice", made["binding"],
        [{"parent": "VCC", "child": "VDD"}],
    )
    assert updated["port_map"] == [{"parent": "VCC", "child": "VDD"}]
    with pytest.raises(ContractError) as caught:
        hierarchy.set_port_map(
            store, "alice", made["binding"],
            [{"parent": "VCC", "child": "VDD"},
             {"parent": "GND", "child": "VDD"}],
        )
    assert caught.value.code == "invalid_hierarchy"
    hierarchy.unbind_block(store, "alice", made["binding"])
    assert hierarchy.children_of(store, top) == []
