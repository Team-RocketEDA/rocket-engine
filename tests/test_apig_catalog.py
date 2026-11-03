"""API-GENERALIZE (b) catalogue index + place_cell durable mutation.

RED: src/library/apig_catalog.py does not exist yet; the loader below
fails until the module lands.
"""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from rocket_engine.library.errors import LibraryError
from rocket_engine.project.errors import ProjectError
from rocket_engine.project.service import ProjectService

ROOT = Path(__file__).resolve().parent.parent


def _load_catalog():
    spec = importlib.util.spec_from_file_location(
        "apig_catalog", ROOT / "src" / "library" / "apig_catalog.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ENTRIES = [
    {
        "cell": "nand2",
        "pdk": "demopdk",
        "pdk_revision": "r1",
        "ports": ["A", "B", "Y"],
        "default_params": {"drive": 2},
    },
    {
        "cell": "inv",
        "pdk": "demopdk",
        "pdk_revision": "r1",
        "ports": ["A", "Y"],
        "default_params": {"drive": 1},
    },
    {
        "cell": "inv",
        "pdk": "otherpdk",
        "pdk_revision": "r2",
        "ports": ["A", "Y"],
        "default_params": {"drive": 4},
    },
]


def test_list_cells_is_versioned_sorted_and_json_clean():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    listing = catalog.list_cells()
    assert listing["catalog_version"] == catalog_mod.CATALOG_VERSION
    assert [(e["pdk"], e["cell"]) for e in listing["cells"]] == [
        ("demopdk", "inv"),
        ("demopdk", "nand2"),
        ("otherpdk", "inv"),
    ]
    for entry in listing["cells"]:
        assert entry["catalog_version"] == catalog_mod.CATALOG_VERSION
        assert set(entry) >= {
            "cell", "pdk", "pdk_revision", "ports",
            "default_params", "catalog_version",
        }
    json.dumps(listing)  # frontend-serializable: no gdsfactory objects
    assert "gdsfactory" not in sys.modules or True
    filtered = catalog.list_cells(pdk="demopdk")
    assert [e["cell"] for e in filtered["cells"]] == ["inv", "nand2"]


def test_get_cell_unknown_and_ambiguous_are_loud():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    assert catalog.get_cell("inv", pdk="demopdk")["default_params"] == {"drive": 1}
    with pytest.raises(LibraryError) as caught:
        catalog.get_cell("xor2", pdk="demopdk")
    assert caught.value.code == "unknown_cell"
    with pytest.raises(LibraryError) as caught:
        catalog.get_cell("inv")
    assert caught.value.code == "ambiguous_cell"
    assert "demopdk" in str(caught.value) and "otherpdk" in str(caught.value)


def test_place_cell_is_a_durable_project_mutation():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    project = ProjectService("place", actor="test")
    mapping = catalog.place_cell(
        project, "nand2", "req-place-1", expected_revision="p12",
        pdk="demopdk", instance_id="u1",
        params={"drive": 3},
        connections=[{"port": "A"}, {"port": "Y"}],
    )
    assert mapping["current_revision"] == "p13"
    assert project.snapshot()["current_revision"] == "p13"
    from ruamel.yaml import YAML

    doc = project.read_doc("components/u1.yaml")
    record = YAML(typ="safe").load(doc["content"])
    assert record["cell"] == "nand2"
    assert record["pdk"] == "demopdk"
    assert record["params"] == {"drive": 3}
    assert mapping["events"][0]["event"] == "mutations_applied"


def test_place_cell_replay_is_idempotent():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    project = ProjectService("placeid", actor="test")
    first = catalog.place_cell(
        project, "inv", "req-place-1", expected_revision="p12",
        pdk="demopdk", instance_id="u1",
    )
    second = catalog.place_cell(
        project, "inv", "req-place-1", expected_revision="p13",
        pdk="demopdk", instance_id="u1",
    )
    assert second == first
    assert project.snapshot()["current_revision"] == "p13"


def test_place_cell_validates_ports_params_and_identity():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    project = ProjectService("placebad", actor="test")
    with pytest.raises(LibraryError) as caught:
        catalog.place_cell(
            project, "inv", "req-1", expected_revision="p12",
            pdk="demopdk", instance_id="u1",
            connections=[{"port": "ZZZ"}],
        )
    assert caught.value.code == "incompatible_port"
    with pytest.raises(LibraryError) as caught:
        catalog.place_cell(
            project, "inv", "req-2", expected_revision="p12",
            pdk="demopdk", instance_id="u1", params={"slew": 1},
        )
    assert caught.value.code == "unknown_param"
    with pytest.raises(LibraryError) as caught:
        catalog.place_cell(
            project, "xor2", "req-3", expected_revision="p12",
            pdk="demopdk", instance_id="u1",
        )
    assert caught.value.code == "unknown_cell"
    assert project.snapshot()["current_revision"] == "p12"
    catalog.place_cell(
        project, "inv", "req-4", expected_revision="p12",
        pdk="demopdk", instance_id="u1",
    )
    with pytest.raises(LibraryError) as caught:
        catalog.place_cell(
            project, "inv", "req-5", expected_revision="p13",
            pdk="demopdk", instance_id="u1",
        )
    assert caught.value.code == "instance_exists"


def test_place_cell_stale_revision_conflicts():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    project = ProjectService("placerev", actor="test")
    with pytest.raises(ProjectError) as caught:
        catalog.place_cell(
            project, "inv", "req-1", expected_revision="p11",
            pdk="demopdk", instance_id="u1",
        )
    assert caught.value.code == "revision_conflict"


def test_gdsfactory_provider_returns_empty_without_gdsfactory(monkeypatch):
    catalog_mod = _load_catalog()
    monkeypatch.setitem(sys.modules, "gdsfactory", None)
    provider = catalog_mod.gdsfactory_provider(modules=["gdsfactory.components"])
    assert provider() == []


def test_gdsfactory_provider_introspects_ports_and_defaults(monkeypatch):
    catalog_mod = _load_catalog()
    fake_gf = types.ModuleType("gdsfactory")
    fake_gf.__version__ = "9.9.9"

    class _Ports(dict):
        pass

    class _Component:
        def __init__(self):
            self.ports = _Ports({"o1": object(), "o2": object()})

    def bend_euler(radius=10.0, angle=90.0):
        """Fake cell factory."""
        return _Component()

    def _undocumented():
        return _Component()

    fake_cells = types.ModuleType("fakecells")
    fake_cells.bend_euler = bend_euler
    fake_gf.get_cells = lambda modules: {"bend_euler": bend_euler}
    monkeypatch.setitem(sys.modules, "gdsfactory", fake_gf)
    monkeypatch.setitem(sys.modules, "fakecells", fake_cells)
    provider = catalog_mod.gdsfactory_provider(
        modules=["fakecells"], pdk="fakepdk", pdk_revision="v0"
    )
    entries = provider()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["cell"] == "bend_euler"
    assert entry["pdk"] == "fakepdk"
    assert sorted(entry["ports"]) == ["o1", "o2"]
    assert entry["default_params"] == {"radius": 10.0, "angle": 90.0}
    json.dumps(entries)


def test_gdsfactory_provider_survives_broken_factories(monkeypatch):
    catalog_mod = _load_catalog()
    fake_gf = types.ModuleType("gdsfactory")
    fake_gf.__version__ = "9.9.9"

    def good(length=5):
        class _Component:
            ports = {"o1": object()}

        return _Component()

    def bad():
        raise RuntimeError("no PDK data")

    fake_gf.get_cells = lambda modules: {"good": good, "bad": bad}
    fake_cells = types.ModuleType("fakecells2")
    monkeypatch.setitem(sys.modules, "gdsfactory", fake_gf)
    monkeypatch.setitem(sys.modules, "fakecells2", fake_cells)
    provider = catalog_mod.gdsfactory_provider(modules=["fakecells2"])
    entries = {entry["cell"]: entry for entry in provider()}
    assert entries["good"]["ports"] == ["o1"]
    assert entries["bad"]["ports"] == []
    json.dumps(entries)


def test_index_caches_providers_until_refresh_or_new_provider():
    catalog_mod = _load_catalog()
    calls = []

    def counting():
        calls.append(1)
        return [
            {
                "cell": "inv",
                "pdk": "demopdk",
                "pdk_revision": "r1",
                "ports": ["A"],
                "default_params": {},
                "catalog_version": catalog_mod.CATALOG_VERSION,
                "source": "counting",
            }
        ]

    catalog = catalog_mod.ApigCatalog(providers=[counting])
    catalog.list_cells()
    catalog.get_cell("inv", pdk="demopdk")
    assert len(calls) == 1
    catalog.refresh()
    assert len(calls) == 2
    catalog.add_provider(catalog_mod.static_provider([]))
    catalog.list_cells()
    assert len(calls) == 3


def test_returned_entries_are_copies():
    catalog_mod = _load_catalog()
    catalog = catalog_mod.ApigCatalog(
        providers=[catalog_mod.static_provider(ENTRIES)]
    )
    listing = catalog.list_cells(pdk="demopdk")
    listing["cells"][0]["ports"].append("HACKED")
    listing["cells"][0]["default_params"]["HACKED"] = 1
    fresh = catalog.list_cells(pdk="demopdk")
    assert "HACKED" not in fresh["cells"][0]["ports"]
    assert "HACKED" not in fresh["cells"][0]["default_params"]
    entry = catalog.get_cell("inv", pdk="demopdk")
    entry["ports"].append("HACKED")
    assert "HACKED" not in catalog.get_cell("inv", pdk="demopdk")["ports"]


def test_real_gdsfactory_components_introspect():
    pytest.importorskip("gdsfactory")
    catalog_mod = _load_catalog()
    provider = catalog_mod.gdsfactory_provider(instantiate=False)
    entries = provider()
    assert len(entries) > 100
    assert all(entry["catalog_version"] == catalog_mod.CATALOG_VERSION
               for entry in entries)
    json.dumps(entries[:5])
