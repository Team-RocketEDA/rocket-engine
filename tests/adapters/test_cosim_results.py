"""Cosim results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.cosim.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 joint
parse shapes (a passing SNDR/ones-density/golden-model corner and
an analog half that yields no bits); the normalizer must map them
to a schema-valid ResultBundle with a measurement table, bound
views, and PASS measurements keeping (value, target, margin,
status).
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
            "name": "sndr_fast_db",
            "value": 42.5,
            "unit": "dB",
            "target": {"min": 36.0},
            "margin": 6.5,
            "status": "pass",
        },
        {
            "name": "ones_density",
            "value": 0.5,
            "unit": "",
            "target": {"min": 0.2, "max": 0.8},
            "margin": 0.3,
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
            "message": "cosim analog half yielded no bits (no bits sampled).",
            "file": "top_tb.spice",
        },
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.cosim.results import normalize

    params = {"run_id": "run-cosim-good", "project_id": "mixed_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_with_joint_measurements(contract):
    """A passing joint corner normalizes to table plus SNDR measures."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_cosim"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 2
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_pass_measurements_keep_target_margin_status(contract):
    """PASS joint measurements keep value, target, margin, status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["sndr_fast_db"]["status"] == "PASS"
    assert by_name["sndr_fast_db"]["value"]["value"] == pytest.approx(42.5)
    assert by_name["ones_density"]["margin"]["value"] == pytest.approx(0.3)


def test_bitless_corner_reports_error_findings(contract):
    """An analog half with no bits normalizes to error findings."""
    bundle = _normalize(BAD, run_id="run-cosim-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])


def test_normalize_is_deterministic(contract):
    """Repeat calls over the same parsed output are byte-identical."""
    assert _normalize(GOOD) == _normalize(GOOD)
    assert not check(contract, _normalize(GOOD))
