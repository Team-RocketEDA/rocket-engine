"""LAYER-CATALOG RED — editable profile-bound layer catalog.

Valid RED = src/project/layers/*.py do not exist yet, so the
loader below fails.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src" / "project"


def _load(name, rel):
    path = SRC / rel
    assert path.is_file(), f"RED: missing owned module {path}"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mods():
    catalog = _load("layers_catalog_red", "layers/catalog.py")
    presets = _load("layers_presets_red", "layers/presets.py")
    bindings = _load("layers_bindings_red", "layers/bindings.py")
    return catalog, presets, bindings


def test_profile_vocabulary_list_and_edit(mods):
    catalog, _, _ = mods
    cat = catalog.LayerCatalog(profile={"name": "sky130A", "version": "v1"})
    layer = cat.add_layer(
        name="met1", purpose="drawing",
        color="#0000ff", order=10,
    )
    assert cat.list_layers()[0]["name"] == "met1"
    cat.rename_layer(layer["lid"], "metal1")
    assert cat.get_layer(layer["lid"])["name"] == "metal1"
    assert cat.get_layer(layer["lid"])["lid"] == layer["lid"]


def test_missing_profile_never_reinterprets(mods):
    catalog, _, _ = mods
    cat = catalog.LayerCatalog(profile=None)
    assert cat.setup_visible is True
    layer = cat.add_layer(name="met1", purpose="drawing")
    saved = cat.to_dict()
    clone = catalog.LayerCatalog.from_dict(saved)
    assert clone.get_layer(layer["lid"])["name"] == "met1"


def test_adding_pdk_keeps_geometry(mods):
    catalog, _, _ = mods
    cat = catalog.LayerCatalog(profile={"name": "base", "version": "v0"})
    layer = cat.add_layer(name="met1", purpose="drawing")
    geometry = [{"layer": layer["lid"], "shape": "rect"}]
    cat.attach_profile({"name": "sky130A", "version": "v1"})
    assert cat.get_layer(layer["lid"])["name"] == "met1"
    assert geometry[0]["layer"] == layer["lid"]


def test_presets_round_trip(mods):
    _, presets, _ = mods
    names = presets.builtin_presets()
    assert "All" in names
    saved = presets.apply_preset("All", ["met1", "via1"])
    assert set(saved["enabled"]) == {"met1", "via1"}


def test_unmapped_layer_reports_unsupported(mods):
    catalog, _, bindings = mods
    cat = catalog.LayerCatalog(profile={"name": "sky130A", "version": "v1"})
    layer = cat.add_layer(name="custom123", purpose="drawing")
    report = bindings.bind_layers(cat, {"sky130A": ["met1"]})
    verdict = bindings.check_operation(report, layer["lid"], "export_gds")
    assert verdict["state"] in ("unsupported", "incomplete")
    assert verdict["layer"] == layer["lid"]
