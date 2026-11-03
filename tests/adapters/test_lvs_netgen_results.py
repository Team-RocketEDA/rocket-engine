"""Lvs_netgen results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.lvs_netgen.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
netgen parse shapes (match plus net/device mismatches); the
normalizer must map them to a schema-valid ResultBundle with a
mismatch table, a bound view, and findings per violation.
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


GOOD = {"match": True, "total": 0, "violations": []}

BAD = {
    "match": False,
    "total": 2,
    "violations": [
        {
            "rule": "lvs_net_mismatch",
            "message": "Net: vdd (only in layout)",
            "net": "vdd",
            "severity": "error",
        },
        {
            "rule": "lvs_device_mismatch",
            "message": "Instance: X1",
            "instance": "X1",
            "severity": "error",
        },
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.lvs_netgen.results import normalize

    params = {"run_id": "run-lvs-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """A matching LVS normalizes to a valid bundle with no findings."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_lvs"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 0
    assert bundle["findings"] == []
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_bad_bundle_reports_error_findings(contract):
    """Net and device mismatches become error findings, never clean."""
    bundle = _normalize(BAD, run_id="run-lvs-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert {f["code"] for f in bundle["findings"]} == {
        "lvs_net_mismatch", "lvs_device_mismatch",
    }


def test_table_rows_name_subjects(contract):
    """Mismatch rows carry the net or instance subject."""
    bundle = _normalize(BAD, run_id="run-lvs-rows")
    assert not check(contract, bundle)
    table = next(d for d in bundle["datasets"] if d["kind"] == "table")
    by_name = {c["name"]: c["data"] for c in table["columns"]}
    assert "vdd" in by_name["subject"]
    assert "X1" in by_name["subject"]


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "match": False,
        "total": 1,
        "violations": [
            {
                "rule": "lvs_net_mismatch",
                "message": "z" * 5000,
                "severity": "error",
            },
        ],
    }
    first = _normalize(parsed, run_id="run-lvs-cap")
    second = _normalize(parsed, run_id="run-lvs-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
