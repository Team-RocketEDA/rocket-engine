"""Drc_kl results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.drc.results_kl` does not exist
yet, so every test fails on ImportError. Fixtures are v0 klayout
parse shapes (clean plus deck-mode and synthetic-mode violations);
the normalizer must map them to a schema-valid ResultBundle with
a rule/message/bbox table, a bound view, and findings per
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


GOOD = {"total": 0, "violations": []}

BAD = {
    "total": 2,
    "violations": [
        {
            "rule": "metal1_width",
            "message": "metal1_width: min width 0.14um",
            "bbox_um": [1.0, 2.0, 1.5, 2.5],
        },
        {"rule": "via1_density", "bbox_um": [0.0, 0.0, 3.0, 3.0]},
    ],
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.drc.results_kl import normalize

    params = {"run_id": "run-drckl-good", "project_id": "analog_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_table(contract):
    """A clean klayout DRC normalizes to a valid bundle."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_drc"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert tables and tables[0]["row_count"] == 0
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_bad_bundle_reports_error_findings(contract):
    """Both deck and synthetic violations become error findings."""
    bundle = _normalize(BAD, run_id="run-drckl-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert all(f["severity"] == "error" for f in bundle["findings"])
    assert {f["code"] for f in bundle["findings"]} == {
        "metal1_width", "via1_density",
    }


def test_synthetic_violation_without_message_still_names_rule(contract):
    """A synthetic bbox-only violation still carries its rule text."""
    bundle = _normalize(BAD, run_id="run-drckl-synth")
    assert not check(contract, bundle)
    by_code = {f["code"]: f for f in bundle["findings"]}
    assert "via1_density" in by_code["via1_density"]["message"]


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = {
        "total": 1,
        "violations": [{"rule": "r", "message": "y" * 5000}],
    }
    first = _normalize(parsed, run_id="run-drckl-cap")
    second = _normalize(parsed, run_id="run-drckl-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
