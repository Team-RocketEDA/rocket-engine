"""Circulax results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.circulax.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
circulax parse shapes (passing transient plus a malformed
circuit); the normalizer must map them to a schema-valid
ResultBundle with a measurement table, a transient series with a
bound trace view, PASS measurements keeping (value, target,
margin, status), and length-capped diagnostics.
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
            "name": "out@1e-06",
            "value": 0.9,
            "unit": "V",
            "target": {"min": 0.8, "max": 1.0},
            "margin": 0.1,
            "status": "pass",
        },
    ],
    "transient": {
        "t_s": [0.0, 1e-06, 2e-06],
        "v_V": [0.0, 0.9, 1.0],
        "observe": "out",
    },
    "circulax_version": "0.2",
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "circuit",
            "severity": "error",
            "message": "unknown component bar",
            "file": "spec.py",
            "line": 7,
        },
    ],
    "measurements": [],
    "circulax_version": "0.2",
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.circulax.results import normalize

    params = {"run_id": "run-circulax-good", "project_id": "photonic_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_series(contract):
    """A passing transient normalizes to a valid bundle with a series."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_optical"
    series = [d for d in bundle["datasets"] if d["kind"] == "series"]
    assert len(series) == 1
    axis = series[0]["axes"][0]
    assert axis["unit"] == "s"
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_pass_measurements_keep_target_margin_status(contract):
    """PASS measurements still carry value, target, margin, status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    meas = by_name["out@1e-06"]
    assert meas["status"] == "PASS"
    assert meas["value"]["value"] == pytest.approx(0.9)
    assert meas["value"]["unit"] == "V"
    assert meas["margin"]["value"] == pytest.approx(0.1)


def test_bad_bundle_reports_error_findings(contract):
    """A malformed circuit normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-circulax-bad")
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
                "message": "t" * 5000,
                "file": "spec.py",
            },
        ],
        "measurements": [],
    }
    first = _normalize(parsed, run_id="run-circulax-cap")
    second = _normalize(parsed, run_id="run-circulax-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
