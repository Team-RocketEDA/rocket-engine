"""Formal-sby results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.formal_sby.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
parse shapes (a bounded PASS with checked properties and a FAIL
with a counterexample); the normalizer must map them to a
schema-valid ResultBundle with a scoped measurement set, a
witness table, bound views, and findings for failures.
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
        "mode": "bmc",
        "depth": 20,
        "top": "prop_top",
        "sby_version": "SBY 0.70",
        "timeout_s": 300,
        "assumptions": 1,
        "properties": 2,
        "scope": "bounded",
        "sby_status": "PASS",
        "sby_rc": 0,
        "engine_status": ["engine_0 (smtbmc boolector) returned pass"],
        "failures": [],
        "counterexamples": [],
        "cover_witnesses": [],
    },
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "assert_fail",
            "severity": "error",
            "message": "assertion `p_no_overflow` failed at step 7.",
            "file": "prop_top.sv",
            "line": 31,
        },
    ],
    "measurements": {
        "mode": "bmc",
        "depth": 20,
        "top": "prop_top",
        "sby_version": "SBY 0.70",
        "timeout_s": 300,
        "assumptions": 1,
        "properties": 2,
        "scope": "bounded",
        "sby_status": "FAIL",
        "sby_rc": 2,
        "engine_status": ["engine_0 (smtbmc boolector) returned FAIL"],
        "failures": [{"property": "p_no_overflow", "kind": "assert"}],
        "counterexamples": [{"property": "p_no_overflow", "present": True}],
        "cover_witnesses": [],
    },
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.formal_sby.results import normalize

    params = {"run_id": "run-formal-good", "project_id": "digital_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_bounded_pass_bundle_validates(contract):
    """A bounded PASS normalizes to a valid bundle with scope measures."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_formal"
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["properties"]["value"]["value"] == pytest.approx(2.0)
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_fail_carries_counterexample_findings(contract):
    """A FAIL normalizes to error findings, never a bare PASS."""
    bundle = _normalize(BAD, run_id="run-formal-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert any(f["severity"] == "error" for f in bundle["findings"])


def test_normalize_is_deterministic(contract):
    """Repeat calls over the same parsed output are byte-identical."""
    assert _normalize(GOOD) == _normalize(GOOD)
    assert _normalize(BAD, run_id="b") == _normalize(BAD, run_id="b")
    assert not check(contract, _normalize(GOOD))
