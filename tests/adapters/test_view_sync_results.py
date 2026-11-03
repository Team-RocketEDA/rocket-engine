"""View_sync results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.view_sync.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
connectgraph view-sync parse shapes (in-sync plus a drift case);
the normalizer must map them to a schema-valid ResultBundle with
a findings table, a coverage table, bound views, and findings per
violation.
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
        "coverage": {"compared": 4, "matched": 4},
        "report": "views in sync",
    },
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "view_drift",
            "severity": "error",
            "message": "cell ota missing pin out in extracted view",
            "cell": "ota",
        },
    ],
    "measurements": {
        "coverage": {"compared": 4, "matched": 3},
        "report": "1 drift",
    },
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.view_sync.results import normalize

    params = {"run_id": "run-viewsync-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_tables(contract):
    """In-sync views normalize to a valid bundle with no findings."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_view_sync"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert len(tables) == 2
    assert bundle["findings"] == []
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_bad_bundle_reports_error_findings(contract):
    """A drifted view becomes an error finding, never clean."""
    bundle = _normalize(BAD, run_id="run-viewsync-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert bundle["findings"][0]["code"] == "view_drift"


def test_coverage_table_carries_compared_counts(contract):
    """Coverage entries ride a key/value table, not prose."""
    bundle = _normalize(GOOD, run_id="run-viewsync-cov")
    assert not check(contract, bundle)
    tables = {d["id"].split(":")[-1]: d for d in bundle["datasets"]}
    coverage = tables["coverage"]
    by_name = {c["name"]: c["data"] for c in coverage["columns"]}
    assert "compared" in by_name["key"]
    assert "matched" in by_name["key"]


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [
            {
                "rule": "view_drift",
                "severity": "error",
                "message": "w" * 5000,
            },
        ],
        "measurements": {"coverage": {}, "report": ""},
    }
    first = _normalize(parsed, run_id="run-viewsync-cap")
    second = _normalize(parsed, run_id="run-viewsync-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
