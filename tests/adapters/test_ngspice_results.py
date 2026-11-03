"""Ngspice results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.ngspice.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 parse
shapes (good corner + valueless sim_fail); the normalizer must map
them to a schema-valid ResultBundle with a measurement table, a
bound view, PASS measurements keeping (value, target, margin,
status), and length-capped diagnostics.
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
        {
            "name": "vref",
            "value": 1.2,
            "unit": "V",
            "target": {"min": 1.15, "max": 1.25},
            "margin": 0.05,
            "status": "pass",
        },
    ],
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "sim_fail",
            "severity": "error",
            "message": (
                "ngspice produced no value for vref. ngspice said: "
                "Error: no such model 'sky130_nope'"
            ),
            "file": "tb.spice",
        },
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.ngspice.results import normalize

    params = {"run_id": "run-ngspice-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """A passing corner normalizes to a valid bundle with table+view."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_spice"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 1
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_pass_measurements_keep_target_margin_status(contract):
    """PASS measurements still carry value, target, margin, and status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    meas = by_name["vref"]
    assert meas["status"] == "PASS"
    assert meas["value"]["value"] == pytest.approx(1.2)
    assert meas["margin"]["value"] == pytest.approx(0.05)


def test_bad_bundle_reports_error_findings(contract):
    """A valueless sim normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-ngspice-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "sim_fail",
                "severity": "error",
                "message": "x" * 5000,
                "file": "tb.spice",
            },
        ],
    }
    first = _normalize(parsed, run_id="run-ngspice-cap")
    second = _normalize(parsed, run_id="run-ngspice-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
