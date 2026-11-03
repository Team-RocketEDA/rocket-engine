"""Connectivity results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.connectivity.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
connectgraph parse shapes (clean plus a shorted-nets case); the
normalizer must map them to a schema-valid ResultBundle with a
findings table, a nets table, bound views, and count
measurements.
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
    "measurements": {
        "netlists": {},
        "nets": ["vdd", "vss", "out"],
        "net_count": 3,
        "instance_count": 2,
        "skipped": [],
    },
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "short",
            "severity": "error",
            "message": "nets vdd and out are shorted",
            "net": "vdd",
            "net_id": 0,
        },
    ],
    "measurements": {
        "netlists": {},
        "nets": ["vdd", "vss"],
        "net_count": 2,
        "instance_count": 1,
        "skipped": ["X9"],
    },
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.connectivity.results import normalize

    params = {"run_id": "run-conn-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_tables(contract):
    """A clean extraction normalizes to a valid nets bundle."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_connectivity"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert len(tables) == 2
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_bad_bundle_reports_error_findings(contract):
    """A shorted net becomes an error finding, never clean."""
    bundle = _normalize(BAD, run_id="run-conn-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert bundle["findings"][0]["code"] == "short"


def test_counts_become_pass_measurements(contract):
    """Net and instance counts ride PASS measurements with values."""
    bundle = _normalize(GOOD, run_id="run-conn-counts")
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["net_count"]["status"] == "PASS"
    assert by_name["net_count"]["value"]["value"] == 3.0
    assert by_name["instance_count"]["value"]["value"] == 2.0


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "short",
                "severity": "error",
                "message": "q" * 5000,
            },
        ],
        "measurements": {
            "netlists": {},
            "nets": [],
            "net_count": 0,
            "instance_count": 0,
            "skipped": [],
        },
    }
    first = _normalize(parsed, run_id="run-conn-cap")
    second = _normalize(parsed, run_id="run-conn-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
