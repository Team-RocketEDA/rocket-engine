"""Gdsfactory results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.gdsfactory.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
views parse shapes (identity mappings plus an unknown cell); the
normalizer must map them to a schema-valid ResultBundle with a
cell mappings table, PASS measurements per mapping, and findings
per violation.
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
    "total": 0,
    "violations": [],
    "measurements": [
        {"name": "polygons(ota)", "value": 42, "unit": "count"},
        {"name": "ports(ota)", "value": 3, "unit": "count"},
        {"name": "bbox_area_um2(ota)", "value": 120.5, "unit": "um2"},
    ],
    "mappings": [
        {
            "component": "ota",
            "ports": ["in", "out", "vdd"],
            "n_polygons": 42,
            "bbox_um": [[0.0, 0.0], [10.0, 12.05]],
        },
    ],
    "diagnostics": {"recipe": "export", "active_pdk": "generic"},
    "artifacts": [{"kind": "gds", "path": "run/ota.gds"}],
    "gdsfactory_version": "8.0",
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "views.unknown_cell",
            "severity": "error",
            "message": "unknown cell nope",
            "file": "spec.py",
        },
    ],
    "measurements": [],
    "mappings": [],
    "diagnostics": {"recipe": "export"},
    "artifacts": [],
    "gdsfactory_version": "8.0",
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.gdsfactory.results import normalize

    params = {"run_id": "run-gf-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """Identity mappings normalize to a valid bundle with a table."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "generate_views"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 1
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_measurements_carry_values_as_pass(contract):
    """Mapping counts ride PASS measurements with their values."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["polygons(ota)"]["status"] == "PASS"
    assert by_name["polygons(ota)"]["value"]["value"] == pytest.approx(42.0)
    assert by_name["bbox_area_um2(ota)"]["value"]["unit"] == "um2"


def test_bad_bundle_reports_error_findings(contract):
    """An unknown cell normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-gf-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "views.unknown_cell",
                "severity": "error",
                "message": "g" * 5000,
                "file": "spec.py",
            },
        ],
        "measurements": [],
        "mappings": [],
        "diagnostics": {"recipe": "export"},
        "artifacts": [],
    }
    first = _normalize(parsed, run_id="run-gf-cap")
    second = _normalize(parsed, run_id="run-gf-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
