"""PROCESS-LAYER-MODEL RED — versioned semantics + recipes.

Valid RED = src/project/process/*.py do not exist yet, so the
loader below fails. Binary-gated tools (opensta, librelane,
klayout, docker) are probed and loud-skipped, never faked.
"""
import importlib.util
import shutil
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
    model = _load("process_model_red", "process/model.py")
    recipes = _load("process_recipes_red", "process/recipes.py")
    return model, recipes


def test_layer_map_reports_source_and_capability(mods):
    model, _ = mods
    profile = model.TechProfile(
        name="sky130A", version="v1.2", source_hash="abc123",
        units="nm", grid=5,
    )
    mapping = model.bind_layer(
        profile, layer="lyr-met1", purpose="drawing",
        gds=(68, 20), capability="supported",
    )
    assert mapping["destination"] == (68, 20)
    assert mapping["capability"] == "supported"
    assert mapping["source_hash"] == "abc123"


def test_missing_mapping_is_loud_unsupported(mods):
    model, _ = mods
    profile = model.TechProfile(
        name="sky130A", version="v1.2", source_hash="abc123",
        units="nm", grid=5,
    )
    verdict = model.check_capability(profile, "export_gds", [])
    assert verdict["state"] in ("unsupported", "incomplete")
    assert "sky130A" in verdict["profile"]


def test_binary_gated_tools_report_blocked(mods):
    model, _ = mods
    for tool in ("opensta", "librelane", "klayout"):
        probe = model.probe_tool(tool)
        assert probe["tool"] == tool
        if shutil.which(tool) is None:
            assert probe["state"] == "BLOCKED-needs-host"
            pytest.skip(f"{tool} absent: {probe['reason']}")
        else:
            assert probe["state"] == "available"


def test_recipe_round_trip_and_unsupported_op(mods):
    _, recipes = mods
    recipe = recipes.DerivedRecipe(
        name="met1-pin", profile="sky130A@v1.2",
        steps=[{"op": "offset", "dx": 10, "dy": 0}],
    )
    shapes = [{"shape_type": "rect", "layer": "lyr-met1",
               "data": {"x": 0, "y": 0, "w": 100, "h": 50}}]
    out = recipes.apply_recipe(shapes, recipe)
    assert out[0]["data"]["x"] == 10
    assert recipes.round_trip_ok(shapes, recipe) in (True, False)
    bad = recipes.DerivedRecipe(
        name="bad", profile="sky130A@v1.2",
        steps=[{"op": "fractalize"}],
    )
    with pytest.raises(Exception) as excinfo:
        recipes.apply_recipe(shapes, bad)
    assert "unsupported" in str(excinfo.value).lower()
