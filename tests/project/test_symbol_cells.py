"""SYMBOL-CELL-EDIT RED: physical cell definitions lane is missing.

Project-owned cells carry explicit ports (name, location, layer),
properties, and hierarchy with monotonic revisions, mirroring the
symbol lane without duplicating geometry across links.
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


def _cells():
    from rocket_engine.project.symbols import cells  # RED: missing

    return cells


def _ports():
    return [
        {"name": "OUT", "x": 100, "y": 50, "layer": "met1"},
        {"name": "VDD", "x": 100, "y": 150, "layer": "met1"},
    ]


def test_create_copy_revise_round_trip():
    cells = _cells()
    store = FakeStore()
    made = cells.create_cell(store, "alice", "opamp_cell", _ports())
    assert made["cell"]
    got = cells.get_cell(store, made["cell"])
    assert got["revision"] == 1
    copied = cells.copy_cell(store, "alice", made["cell"], "opamp_cell2")
    assert copied["cell"] != made["cell"]
    revised = cells.revise_cell(
        store, "alice", made["cell"],
        ports=[{"name": "OUT", "x": 100, "y": 50, "layer": "met1"}],
    )
    assert revised["cell_revision"] == 2
    assert [c["name"] for c in cells.list_cells(store)] == [
        "opamp_cell", "opamp_cell2",
    ]


def test_duplicate_name_and_bad_port_rejected():
    cells = _cells()
    store = FakeStore()
    cells.create_cell(store, "alice", "opamp_cell", _ports())
    with pytest.raises(ContractError) as caught:
        cells.create_cell(store, "alice", "opamp_cell", _ports())
    assert caught.value.code == "cell_exists"
    with pytest.raises(ContractError) as caught:
        cells.validate_cell(
            {"name": "bad", "ports": [
                {"name": "", "x": 0, "y": 0, "layer": "met1"}],
             "properties": {}, "revision": 1}
        )
    assert caught.value.code == "invalid_cell"


def test_rename_refuses_when_linkage_references_cell():
    cells = _cells()
    store = FakeStore()
    made = cells.create_cell(store, "alice", "opamp_cell", _ports())
    holder = store.create_entity("alice", "linkage holder")["id"]
    store.attach_component(
        "alice", holder, "Linkage",
        {"symbol": "opamp", "cell": "opamp_cell",
         "pin_map": [], "revision": 1},
        "seed linkage",
    )
    with pytest.raises(ContractError) as caught:
        cells.rename_cell(store, "alice", made["cell"], "renamed")
    assert caught.value.code == "cell_in_use"


def test_unknown_cell_loud():
    cells = _cells()
    store = FakeStore()
    with pytest.raises(ContractError) as caught:
        cells.get_cell(store, "e999")
    assert caught.value.code == "unknown_cell"
