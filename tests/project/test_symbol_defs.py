"""SYMBOL-CELL-EDIT RED: symbol definitions lane does not exist yet.

Project-owned symbols carry editable pins (name, electrical type,
location), graphics, names, and properties with monotonic
revisions. Upstream PDK bytes are never touched — only project
entities are written.
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


def _symbols():
    from rocket_engine.project.symbols import symbols  # RED: missing

    return symbols


def _pins():
    return [
        {"name": "IN+", "pin_type": "input", "x": 0, "y": 10},
        {"name": "OUT", "pin_type": "output", "x": 40, "y": 10},
        {"name": "VDD", "pin_type": "power", "x": 20, "y": 30},
    ]


def test_create_copy_revise_round_trip():
    symbols = _symbols()
    store = FakeStore()
    made = symbols.create_symbol(store, "alice", "opamp", _pins())
    assert made["symbol"]
    got = symbols.get_symbol(store, made["symbol"])
    assert got["revision"] == 1
    assert [p["name"] for p in got["pins"]] == ["IN+", "OUT", "VDD"]
    copied = symbols.copy_symbol(store, "alice", made["symbol"], "opamp2")
    assert copied["symbol"] != made["symbol"]
    revised = symbols.revise_symbol(
        store, "alice", made["symbol"],
        pins=[{"name": "OUT", "pin_type": "output", "x": 40, "y": 10}],
    )
    assert revised["symbol_revision"] == 2
    names = [s["name"] for s in symbols.list_symbols(store)]
    assert names == ["opamp", "opamp2"]


def test_duplicate_name_and_bad_pin_rejected():
    symbols = _symbols()
    store = FakeStore()
    symbols.create_symbol(store, "alice", "opamp", _pins())
    with pytest.raises(ContractError) as caught:
        symbols.create_symbol(store, "alice", "opamp", _pins())
    assert caught.value.code == "symbol_exists"
    with pytest.raises(ContractError) as caught:
        symbols.validate_symbol(
            {"name": "bad", "pins": [
                {"name": "OUT", "pin_type": "radio", "x": 0, "y": 0}],
             "graphics": [], "properties": {}, "revision": 1}
        )
    assert caught.value.code == "invalid_symbol"
    with pytest.raises(ContractError) as caught:
        symbols.validate_symbol(
            {"name": "bad", "pins": [
                {"name": "A", "pin_type": "input", "x": 0, "y": 0},
                {"name": "A", "pin_type": "input", "x": 1, "y": 1}],
             "graphics": [], "properties": {}, "revision": 1}
        )
    assert caught.value.code == "invalid_symbol"


def test_rename_refuses_when_instances_reference_symbol():
    symbols = _symbols()
    store = FakeStore()
    made = symbols.create_symbol(store, "alice", "opamp", _pins())
    holder = store.create_entity("alice", "instance holder")["id"]
    store.attach_component(
        "alice", holder, "Instance",
        {"sheet": "e9", "symbol": "opamp", "x": 0, "y": 0,
         "rotation": 0, "mirror": False, "properties": {},
         "ref": "U1"},
        "seed instance",
    )
    with pytest.raises(ContractError) as caught:
        symbols.rename_symbol(store, "alice", made["symbol"], "opamp_new")
    assert caught.value.code == "symbol_in_use"
    renamed = symbols.rename_symbol(store, "alice", copied_id(store, symbols), "free")
    assert renamed["name"] == "free"


def copied_id(store, symbols):
    made = symbols.create_symbol(store, "alice", "spare", [])
    return made["symbol"]


def test_unknown_symbol_loud():
    symbols = _symbols()
    store = FakeStore()
    with pytest.raises(ContractError) as caught:
        symbols.get_symbol(store, "e999")
    assert caught.value.code == "unknown_symbol"
