"""Sax results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.sax.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 sax
parse shapes (passing sweep plus a malformed circuit); the
normalizer must map them to a schema-valid ResultBundle with a
measurement table, per-target series datasets with bound trace
views, PASS measurements keeping (value, target, margin,
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
            "name": "in>out",
            "value": -0.5,
            "unit": "dB",
            "target": {"min": -1.0, "max": 0.0},
            "margin": 0.5,
            "status": "pass",
        },
    ],
    "spectra": [
        {
            "from": "in",
            "to": "out",
            "wavelength_nm": [1500.0, 1550.0, 1600.0],
            "transmission_db": [-0.6, -0.5, -0.7],
        },
    ],
    "sax_version": "0.1",
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "circuit",
            "severity": "error",
            "message": "unknown component foo",
            "file": "spec.py",
            "line": 3,
        },
    ],
    "measurements": [],
    "sax_version": "0.1",
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.sax.results import normalize

    params = {"run_id": "run-sax-good", "project_id": "photonic_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_series(contract):
    """A passing sweep normalizes to a valid bundle with a series."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_optical"
    series = [d for d in bundle["datasets"] if d["kind"] == "series"]
    assert len(series) == 1
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_pass_measurements_keep_target_margin_status(contract):
    """PASS measurements still carry value, target, margin, status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    meas = by_name["in>out"]
    assert meas["status"] == "PASS"
    assert meas["value"]["value"] == pytest.approx(-0.5)
    assert meas["value"]["unit"] == "dB"
    assert meas["margin"]["value"] == pytest.approx(0.5)


def test_bad_bundle_reports_error_findings(contract):
    """A malformed circuit normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-sax-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert bundle["convergence"] == "not_converged"


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "circuit",
                "severity": "error",
                "message": "e" * 5000,
                "file": "spec.py",
            },
        ],
        "measurements": [],
    }
    first = _normalize(parsed, run_id="run-sax-cap")
    second = _normalize(parsed, run_id="run-sax-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
