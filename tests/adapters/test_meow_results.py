"""Meow results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.meow.results` does not exist
yet, so every test fails on ImportError. Fixtures are v0 meow
parse shapes (passing S-params plus a malformed device); the
normalizer must map them to a schema-valid ResultBundle with a
metrics table, PASS measurements keeping (value, target, margin,
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
            "name": "transmission",
            "value": 0.95,
            "unit": "",
            "target": {"min": 0.9},
            "margin": 0.05,
            "status": "pass",
        },
        {
            "name": "convergence_dT",
            "value": 1e-06,
            "unit": "",
            "target": {"max": 1e-05},
            "margin": 9e-06,
            "status": "pass",
        },
    ],
    "modes": {"base": {"transmission": 0.95}, "refined": {}},
    "convergence": {"dT": 1e-06, "dneff": 1e-07},
    "meow_version": "0.3",
    "tidy3d_version": "2.0",
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "device",
            "severity": "error",
            "message": "unknown material foo",
            "file": "spec.py",
            "line": 2,
        },
    ],
    "measurements": [],
    "meow_version": "0.3",
    "tidy3d_version": "2.0",
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.meow.results import normalize

    params = {"run_id": "run-meow-good", "project_id": "photonic_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """Passing S-params normalize to a valid bundle with a table."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_em"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 2
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_pass_measurements_keep_target_margin_status(contract):
    """PASS measurements still carry value, target, margin, status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["transmission"]["status"] == "PASS"
    assert by_name["transmission"]["value"]["value"] == pytest.approx(0.95)
    assert by_name["convergence_dT"]["margin"]["value"] == pytest.approx(9e-06)


def test_bad_bundle_reports_error_findings(contract):
    """A malformed device normalizes to error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-meow-bad")
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
                "rule": "device",
                "severity": "error",
                "message": "m" * 5000,
                "file": "spec.py",
            },
        ],
        "measurements": [],
    }
    first = _normalize(parsed, run_id="run-meow-cap")
    second = _normalize(parsed, run_id="run-meow-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
