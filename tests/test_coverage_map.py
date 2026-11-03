"""COVERAGE-MAP RED — committed op x PDK x tool matrix with rerun.

The committed coverage/map.json matrix pins per-cell verdicts from
committed fixtures (correct plus mutated per lane); coverage/check.py
re-runs every cell through the real adapter parse and rejects a stale
map whose fingerprint no longer matches the tree. Fails today: the
coverage dir does not exist yet.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CHECK = ROOT / "coverage" / "check.py"
MAP = ROOT / "coverage" / "map.json"


def _check_module():
    spec = importlib.util.spec_from_file_location("coverage_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coverage_check_command_exists_with_map():
    assert CHECK.is_file()
    assert MAP.is_file()
    doc = json.loads(MAP.read_text())
    assert doc["cells"], "coverage map must claim at least one cell"


def test_committed_map_is_fresh_and_green():
    assert _check_module().check() == []


def test_map_cells_cover_all_four_lanes():
    doc = json.loads(MAP.read_text())
    lanes = {c["lane"] for c in doc["cells"]}
    assert {"digital", "analog", "photonic", "mixed"} <= lanes


def test_map_cell_fixtures_exist_and_pin_both_directions():
    doc = json.loads(MAP.read_text())
    for cell in doc["cells"]:
        assert cell["expect"]["good"]["verdict"] == "pass", cell["cell"]
        assert cell["expect"]["bad"]["verdict"] == "fail", cell["cell"]
        for rel in cell["fixtures"]["good"] + cell["fixtures"]["bad"]:
            assert (ROOT / rel).is_file(), f"{cell['cell']}: {rel}"


def test_map_cells_resolve_against_registry_catalog_and_pdks():
    from rocket_engine.composition import Engine

    engine = Engine("coverage-map", actor="coverage-map")
    solvers = {op: set(tools) for op, tools in engine._solvers.items()}
    catalog = json.loads(
        (ROOT / "contracts" / "v1" / "catalog" / "tasks.json").read_text()
    )
    catalog_tools = {t for tasks in catalog.values() for t in tasks["tools"]}
    from rocket_engine.interfaces.setup import load_catalogue

    catalogue_pdks = {
        e["pdk_id"] for e in load_catalogue()["entries"] if e["kind"] == "pdk"
    }
    doc = json.loads(MAP.read_text())
    for cell in doc["cells"]:
        assert cell["tool"] in solvers.get(cell["op"], set()), cell["cell"]
        assert cell["tool"] in catalog_tools, cell["cell"]
        assert cell["pdk"] in catalogue_pdks | {"generic"}, cell["cell"]


def test_map_rerun_pins_both_directions_through_real_parse(tmp_path):
    module = _check_module()
    doc = json.loads(MAP.read_text())
    for cell in doc["cells"]:
        report = module.rerun_cell(cell, tmp_path / cell["cell"])
        assert report["problems"] == [], report


def test_stale_map_is_rejected(tmp_path):
    module = _check_module()
    stale = tmp_path / "map.json"
    doc = json.loads(MAP.read_text())
    doc["cells"] = doc["cells"][:1]
    stale.write_text(json.dumps(doc, indent=1))
    assert module.check(stale) != []


def test_fingerprint_covers_stages_decks_and_catalog():
    module = _check_module()
    doc = json.loads(MAP.read_text())
    assert doc["fingerprint"] == module.compute_fingerprint(doc["cells"])
    assert any(e.endswith("stages.py") for e in doc["fingerprinted"])
    assert any(e.endswith("tasks.json") for e in doc["fingerprinted"])
