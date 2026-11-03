"""SCHEMATIC-EDIT RED: sheets lane does not exist yet.

Every import below fails until src/project/schematic/sheets.py
lands. Sheets are durable entities carrying the Sheet component
({name, title}); names are unique per project.
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


def _sheets():
    from rocket_engine.project.schematic import sheets  # RED: missing module

    return sheets


def test_create_and_list_sheets_round_trip():
    sheets = _sheets()
    store = FakeStore()
    first = sheets.create_sheet(store, "alice", "top", title="Top level")
    second = sheets.create_sheet(store, "alice", "psu")
    assert first["sheet"] != second["sheet"]
    listed = sheets.list_sheets(store)
    assert [(s["name"], s["title"]) for s in listed] == [
        ("psu", ""),
        ("top", "Top level"),
    ]


def test_duplicate_sheet_name_refused():
    sheets = _sheets()
    store = FakeStore()
    sheets.create_sheet(store, "alice", "top")
    with pytest.raises(ContractError) as caught:
        sheets.create_sheet(store, "alice", "top")
    assert caught.value.code == "sheet_exists"


def test_bad_sheet_shape_rejected_at_edit_time():
    sheets = _sheets()
    with pytest.raises(ContractError) as caught:
        sheets.validate_sheet({"name": "", "title": "x"})
    assert caught.value.code == "invalid_sheet"
    with pytest.raises(ContractError) as caught:
        sheets.validate_sheet({"name": "has space", "title": ""})
    assert caught.value.code == "invalid_sheet"


def test_rename_sheet_and_unknown_sheet_loud():
    sheets = _sheets()
    store = FakeStore()
    made = sheets.create_sheet(store, "alice", "top")
    renamed = sheets.rename_sheet(store, "alice", made["sheet"], "top2")
    assert renamed["revision"] is not None
    assert sheets.get_sheet(store, made["sheet"])["name"] == "top2"
    with pytest.raises(ContractError) as caught:
        sheets.rename_sheet(store, "alice", "e999", "ghost")
    assert caught.value.code == "unknown_sheet"


def test_delete_sheet_refuses_when_instances_remain():
    sheets = _sheets()
    store = FakeStore()
    made = sheets.create_sheet(store, "alice", "top")
    holder = store.create_entity("alice", "instance holder")["id"]
    store.attach_component(
        "alice", holder, "Instance",
        {"sheet": made["sheet"], "symbol": "pdk:opamp",
         "x": 0, "y": 0, "rotation": 0, "mirror": False,
         "properties": {}, "ref": ""},
        "seed instance",
    )
    with pytest.raises(ContractError) as caught:
        sheets.delete_sheet(store, "alice", made["sheet"])
    assert caught.value.code == "sheet_in_use"


def test_delete_empty_sheet_lands():
    sheets = _sheets()
    store = FakeStore()
    made = sheets.create_sheet(store, "alice", "top")
    receipt = sheets.delete_sheet(store, "alice", made["sheet"])
    assert receipt["sheet"] == made["sheet"]
    assert sheets.list_sheets(store) == []
