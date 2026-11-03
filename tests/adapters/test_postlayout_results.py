"""Postlayout results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.postlayout.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
parse shapes (good corner with pre/post comparison plus a short
waveform, and a valueless sim_fail); the normalizer must map them
to a schema-valid ResultBundle with measurement and waveform
datasets, bound views, and capped diagnostics.
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
            "value": 1.19,
            "unit": "V",
            "target": {"min": 1.15, "max": 1.25},
            "margin": 0.04,
            "status": "pass",
        },
    ],
    "comparison": [
        {
            "name": "vref",
            "pre": 1.2,
            "post": 1.19,
            "delta": -0.01,
            "rel": -0.0083,
            "status": "pass",
        },
    ],
    "waveforms": [
        {
            "name": "vout",
            "expr": "v(vout)",
            "samples": [0.0, 0.6, 1.2],
            "scale": [0.0, 1e-9, 2e-9],
            "count": 3,
            "downsampled": False,
        },
    ],
    "provenance": {"extraction_run_id": "run-extract-1"},
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "sim_fail",
            "severity": "error",
            "message": (
                "ngspice produced no value for vref. ngspice said: "
                "Error: singular matrix"
            ),
            "file": "extracted.spice",
        },
    ],
    "comparison": [],
    "waveforms": [],
    "provenance": {"extraction_run_id": "run-extract-1"},
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.postlayout.results import normalize

    params = {"run_id": "run-postlayout-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_with_trace_and_table(contract):
    """A passing corner yields table plus transient-trace datasets."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_post_layout"
    kinds = {d["kind"] for d in bundle["datasets"]}
    assert "table" in kinds and "series" in kinds
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_waveform_axes_carry_units_and_signal_identity(contract):
    """Waveform datasets keep explicit time axes and signal names."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    series = [d for d in bundle["datasets"] if d["kind"] == "series"]
    assert series[0]["axes"][0]["unit"] == "s"
    assert series[0]["signals"][0]["name"] == "vout"


def test_bad_bundle_reports_error_findings(contract):
    """A valueless post-layout sim normalizes to error findings."""
    bundle = _normalize(BAD, run_id="run-postlayout-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])


def test_normalize_is_deterministic(contract):
    """Repeat calls over the same parsed output are byte-identical."""
    assert _normalize(GOOD) == _normalize(GOOD)
    assert not check(contract, _normalize(GOOD))
