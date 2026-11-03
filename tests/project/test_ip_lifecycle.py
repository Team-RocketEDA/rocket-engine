"""IP-LIFECYCLE RED: ip_* ops lane does not exist yet.

IP blocks are prebuilt HIERARCHICAL schematic blocks (KiCad
catalogue model): each ships a schematic symbol AND a footprint
cell LINKED. Instantiate = place with linkage intact. INVARIANT:
prebuilt IP is PER-PDK — each PDK strictly owns its blocks
(digital MAY generalize case-by-case via scope="shared" with a
recorded reason, default per-PDK).
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


def _lifecycle():
    from rocket_engine.project.ip import lifecycle  # RED: missing

    return lifecycle


def _seed_sheet_symbol(store):
    sheet = store.create_entity("alice", "sheet")["id"]
    store.attach_component(
        "alice", sheet, "Sheet", {"name": "top", "title": ""}, "seed"
    )
    return sheet


def test_register_search_get_round_trip():
    lifecycle = _lifecycle()
    store = FakeStore()
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
        pin_map=[{"symPin": "VIN", "cellPin": "VIN"}],
    )
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v2",
        "buck_sym", "buck_cell",
    )
    hits = lifecycle.ip_search(store, "sky130A")
    assert [(h["name"], h["version"]) for h in hits] == [
        ("buck_3v3", "v1"), ("buck_3v3", "v2"),
    ]
    filtered = lifecycle.ip_search(store, "sky130A", name_filter="buck")
    assert len(filtered) == 2
    assert lifecycle.ip_search(store, "sky130A", name_filter="pll") == []
    latest = lifecycle.ip_get(store, "sky130A", "buck_3v3")
    assert latest["version"] == "v2"
    first = lifecycle.ip_get(store, "sky130A", "buck_3v3", version="v1")
    assert first["pin_map"] == [{"symPin": "VIN", "cellPin": "VIN"}]


def test_per_pdk_invariant_search_scoped_and_cross_pdk_refused():
    lifecycle = _lifecycle()
    store = FakeStore()
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
    )
    assert lifecycle.ip_search(store, "gf180MC") == []
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_search(store, "")
    assert caught.value.code == "invalid_pdk"
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_get(store, "gf180MC", "buck_3v3")
    assert caught.value.code == "unknown_ip"


def test_duplicate_registration_and_shared_scope_rule():
    lifecycle = _lifecycle()
    store = FakeStore()
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
    )
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_register(
            store, "alice", "sky130A", "buck_3v3", "v1",
            "buck_sym", "buck_cell",
        )
    assert caught.value.code == "ip_exists"
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_register(
            store, "alice", "sky130A", "nand2", "v1",
            "nand_sym", "nand_cell", scope="shared",
        )
    assert caught.value.code == "invalid_scope"
    shared = lifecycle.ip_register(
        store, "alice", "sky130A", "nand2", "v1",
        "nand_sym", "nand_cell", scope="shared",
        reason="digital gate, PDK-independent",
    )
    assert shared["scope"] == "shared"


def test_instantiate_places_with_linkage_intact():
    lifecycle = _lifecycle()
    store = FakeStore()
    sheet = _seed_sheet_symbol(store)
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
        pin_map=[{"symPin": "VIN", "cellPin": "VIN"}],
    )
    made = lifecycle.ip_instantiate(
        store, "alice", "sky130A", "buck_3v3", sheet, 10, 20
    )
    instance = store.get_component(made["instance"], "Instance")
    assert instance["symbol"] == "buck_sym"
    assert (instance["x"], instance["y"]) == (10, 20)
    link = store.get_component(made["instance"], "IpLink")
    assert link["name"] == "buck_3v3"
    assert link["version"] == "v1"
    assert link["cell"] == "buck_cell"


def test_instantiate_enforces_per_pdk_invariant():
    lifecycle = _lifecycle()
    store = FakeStore()
    sheet = _seed_sheet_symbol(store)
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
    )
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_instantiate(
            store, "alice", "gf180MC", "buck_3v3", sheet, 0, 0
        )
    assert caught.value.code in ("unknown_ip", "pdk_mismatch")
    lifecycle.ip_register(
        store, "alice", "sky130A", "nand2", "v1",
        "nand_sym", "nand_cell", scope="shared",
        reason="digital gate, PDK-independent",
    )
    shared = lifecycle.ip_instantiate(
        store, "alice", "gf180MC", "nand2", sheet, 0, 0
    )
    assert shared["instance"]


def test_promote_marks_one_version():
    lifecycle = _lifecycle()
    store = FakeStore()
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v1",
        "buck_sym", "buck_cell",
    )
    lifecycle.ip_register(
        store, "alice", "sky130A", "buck_3v3", "v2",
        "buck_sym", "buck_cell",
    )
    promoted = lifecycle.ip_promote(store, "alice", "sky130A", "buck_3v3", "v2")
    assert promoted["promoted"] is True
    assert lifecycle.ip_get(store, "sky130A", "buck_3v3", "v1")["promoted"] is False
    assert lifecycle.ip_get(store, "sky130A", "buck_3v3")["promoted"] is True
    with pytest.raises(ContractError) as caught:
        lifecycle.ip_promote(store, "alice", "sky130A", "buck_3v3", "v9")
    assert caught.value.code == "unknown_ip"
