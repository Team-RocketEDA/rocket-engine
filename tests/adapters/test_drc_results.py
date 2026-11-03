"""Drc results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.drc.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 magic
parse shapes (clean plus two rule boxes); the normalizer must map
them to a schema-valid ResultBundle with a rule/area/bbox table,
a bound view, and findings per violation.
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


GOOD = {"total": 0, "violations": []}

BAD = {
    "total": 2,
    "violations": [
        {
            "area": 12,
            "rule": "m1.width",
            "bbox": [0, 0, 100, 200],
        },
        {
            "area": 3,
            "rule": "poly.spacing",
            "bbox": [10, 20, 30, 40],
        },
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.drc.results import normalize

    params = {"run_id": "run-drc-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """A clean DRC normalizes to a valid bundle with an empty table."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_drc"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 0
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_bad_bundle_reports_error_findings(contract):
    """Rule boxes normalize to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-drc-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert {f["code"] for f in bundle["findings"]} == {
        "m1.width", "poly.spacing",
    }


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {"area": 1, "rule": "x" * 5000, "bbox": [0, 0, 1, 1]},
        ],
    }
    first = _normalize(parsed, run_id="run-drc-cap")
    second = _normalize(parsed, run_id="run-drc-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])


def test_table_rows_name_rule_area_and_bbox(contract):
    """Every violation row carries its rule, area, and bbox."""
    bundle = _normalize(BAD, run_id="run-drc-rows")
    assert not check(contract, bundle)
    table = next(d for d in bundle["datasets"] if d["kind"] == "table")
    by_name = {c["name"]: c["data"] for c in table["columns"]}
    assert by_name["rule"] == ["m1.width", "poly.spacing"]
    assert by_name["area"] == [12.0, 3.0]
    assert len(by_name["bbox"]) == 2
