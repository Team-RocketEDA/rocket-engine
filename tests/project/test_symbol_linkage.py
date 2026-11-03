"""SYMBOL-CELL-EDIT RED: symbol<->cell linkage lane is missing.

Linkage keeps the shared component identity (symbol + cell +
explicit pin map) with CELL-LINK resolution semantics: explicit
entries win, unlisted pins resolve to themselves, and the
frontend renders persisted mappings as visible pin-link strings
while unmatched/conflicting pins are reported, never hidden.
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


def _seed_symbol_cell(store):
    sym = store.create_entity("alice", "symbol")["id"]
    store.attach_component(
        "alice", sym, "Symbol",
        {"name": "opamp",
         "pins": [
             {"name": "IN+", "pin_type": "input", "x": 0, "y": 10},
             {"name": "OUT", "pin_type": "output", "x": 40, "y": 10},
             {"name": "VDD", "pin_type": "power", "x": 20, "y": 30},
         ],
         "graphics": [], "properties": {}, "revision": 1},
        "seed",
    )
    cell = store.create_entity("alice", "cell")["id"]
    store.attach_component(
        "alice", cell, "Cell",
        {"name": "opamp_cell",
         "ports": [
             {"name": "OUT", "x": 100, "y": 50, "layer": "met1"},
             {"name": "VDD", "x": 100, "y": 150, "layer": "met1"},
             {"name": "EXTRA", "x": 0, "y": 0, "layer": "met1"},
         ],
         "properties": {}, "revision": 1},
        "seed",
    )
    return sym, cell


def _linkage():
    from rocket_engine.project.symbols import linkage  # RED: missing

    return linkage


def test_map_and_remap_bumps_revision():
    linkage = _linkage()
    store = FakeStore()
    _seed_symbol_cell(store)
    first = linkage.map_pins(
        store, "alice", "opamp", "opamp_cell",
        [{"symPin": "IN+", "cellPin": "IN_P"}],
    )
    assert first["linkage_revision"] == 1
    second = linkage.map_pins(
        store, "alice", "opamp", "opamp_cell",
        [{"symPin": "IN+", "cellPin": "IN_P"},
         {"symPin": "OUT", "cellPin": "OUT"}],
    )
    assert second["linkage_revision"] == 2
    assert second["linkage"] == first["linkage"]


def test_check_mapping_reports_unmatched_explicitly():
    linkage = _linkage()
    store = FakeStore()
    _seed_symbol_cell(store)
    linkage.map_pins(
        store, "alice", "opamp", "opamp_cell",
        [{"symPin": "IN+", "cellPin": "EXTRA"}],
    )
    report = linkage.check_mapping(store, "opamp", "opamp_cell")
    assert report["unmatched_symbol_pins"] == ["OUT", "VDD"]
    assert report["unmatched_cell_ports"] == ["OUT", "VDD"]
    assert report["conflicts"] == []


def test_conflicting_map_entries_reported_not_dropped():
    linkage = _linkage()
    store = FakeStore()
    _seed_symbol_cell(store)
    linkage.map_pins(
        store, "alice", "opamp", "opamp_cell",
        [{"symPin": "GHOST", "cellPin": "OUT"}],
    )
    report = linkage.check_mapping(store, "opamp", "opamp_cell")
    assert len(report["conflicts"]) == 1
    assert report["conflicts"][0]["symPin"] == "GHOST"


def test_pin_link_strings_and_identity_resolution():
    linkage = _linkage()
    store = FakeStore()
    _seed_symbol_cell(store)
    linkage.map_pins(
        store, "alice", "opamp", "opamp_cell",
        [{"symPin": "OUT", "cellPin": "OUT"}],
    )
    rendered = linkage.pin_link_strings(store, "opamp", "opamp_cell")
    assert rendered["links"] == ["opamp.OUT -> opamp_cell.OUT"]
    assert linkage.resolve_mapped_pin(store, "opamp", "OUT") == "OUT"
    assert linkage.resolve_mapped_pin(store, "opamp", "VDD") == "VDD"


def test_missing_symbol_or_cell_fails_loud():
    linkage = _linkage()
    store = FakeStore()
    _seed_symbol_cell(store)
    with pytest.raises(ContractError) as caught:
        linkage.map_pins(store, "alice", "ghost", "opamp_cell", [])
    assert caught.value.code == "unknown_symbol"
    with pytest.raises(ContractError) as caught:
        linkage.map_pins(store, "alice", "opamp", "ghost_cell", [])
    assert caught.value.code == "unknown_cell"
