"""Synth-yosys results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.synth_yosys.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
parse shapes (a mapped netlist with cell counts plus a latch
warning, and a failed run with a synth_error); the normalizer must
map them to a schema-valid ResultBundle with a cell table, bound
views, and measurements for cell/wire counts.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "v1_contract", ROOT / "scripts/check_v1_contract.py"
)
CONTRACT_MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT_MOD)


@pytest.fixture(scope="module")
def contract():
    """Load the one canonical v1 contract bundle."""
    return CONTRACT_MOD.load_contract()


def check(contract, value):
    """Collect ResultBundle schema errors for one bundle."""
    return list(
        CONTRACT_MOD.validator(contract, "#/$defs/ResultBundle").iter_errors(
            value
        )
    )


GOOD = {
    "total": 1,
    "violations": [
        {
            "rule": "latch",
            "severity": "warning",
            "message": "Latch inferred for signal `q`.",
            "file": "top.v",
            "line": 21,
        },
    ],
    "measurements": [
        {"name": "cell_count", "value": 3, "unit": "cells"},
        {"name": "wire_count", "value": 9, "unit": "wires"},
    ],
    "cells": {"$_DLATCH_P_": 2, "$_NOT_": 1},
    "cell_count": 3,
    "wire_count": 9,
    "area": None,
    "mapped": True,
    "netlist": "synth_netlist.v",
    "top": "top",
    "yosys_version": "Yosys 0.70",
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "synth_error",
            "severity": "error",
            "message": "top.v:3: ERROR: Module `missing` not found.",
            "file": "top.v",
            "line": 3,
        },
    ],
    "measurements": [],
    "cells": {},
    "cell_count": 0,
    "wire_count": 0,
    "area": None,
    "mapped": False,
    "netlist": None,
    "top": "top",
    "yosys_version": "Yosys 0.70",
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.synth_yosys.results import normalize

    params = {"run_id": "run-synth-good", "project_id": "digital_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_with_cell_table(contract):
    """A mapped netlist normalizes to a per-family cell table."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_synth"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 2
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_count_measurements_keep_status(contract):
    """Cell/wire counts land as measurements with a PASS status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["cell_count"]["status"] == "PASS"
    assert by_name["cell_count"]["value"]["value"] == pytest.approx(3.0)


def test_failed_run_reports_error_findings(contract):
    """A failed synth run normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-synth-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert any(f["severity"] == "error" for f in bundle["findings"])


def test_normalize_is_deterministic(contract):
    """Repeat calls over the same parsed output are byte-identical."""
    assert _normalize(GOOD) == _normalize(GOOD)
    assert not check(contract, _normalize(GOOD))
