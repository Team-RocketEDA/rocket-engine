"""Digital_flow results RED — pure v1 ResultBundle normalizer.

Valid RED = `rocket_engine.adapters.digital_flow.results` does not
exist yet, so every test fails on ImportError. Fixtures are v0
librelane parse shapes (passing gates plus a failed gate); the
normalizer must map them to a schema-valid ResultBundle with a
per-stage table, a deliverables table, LVS/DRC measurements, and
findings per failed gate.
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
    "measurements": {},
    "stages": [
        {
            "id": "D11",
            "label": "synth",
            "status": "pass",
            "steps": ["synth"],
            "evidence": ["run/synth"],
            "reports": ["run/synth/rpt.txt"],
            "reason": "gate clean",
        },
        {
            "id": "D12",
            "label": "floorplan",
            "status": "pass",
            "steps": ["fp"],
            "evidence": ["run/fp"],
            "reports": [],
            "reason": "gate clean",
        },
    ],
    "gds": "run/final.gds",
    "netlist": "run/final.v",
    "spef": "run/final.spef",
    "drc_total": 0,
    "lvs_match": True,
    "librelane_version": "3.0.17",
    "tag": "demo",
    "run_dir": "run",
    "timed_out": False,
}

BAD = {
    "total": 1,
    "violations": [
        {
            "rule": "digital_flow_gate",
            "severity": "error",
            "message": "D11 synth failed: no clock (see run/synth)",
            "file": "run/synth",
        },
    ],
    "measurements": {},
    "stages": [
        {
            "id": "D11",
            "label": "synth",
            "status": "fail",
            "steps": ["synth"],
            "evidence": [],
            "reports": ["run/synth/rpt.txt"],
            "reason": "no clock",
        },
        {
            "id": "D12",
            "label": "floorplan",
            "status": "not_run",
            "steps": [],
            "evidence": [],
            "reports": [],
            "reason": "upstream gate failed",
        },
    ],
    "gds": None,
    "netlist": None,
    "spef": None,
    "drc_total": None,
    "lvs_match": False,
    "librelane_version": "3.0.17",
    "tag": "demo",
    "run_dir": "run",
    "timed_out": False,
}


def _normalize(parsed, **over):
    from rocket_engine.adapters.digital_flow.results import normalize

    params = {"run_id": "run-flow-good", "project_id": "digital_demo"}
    params.update(over)
    return normalize(parsed, **params)


def test_good_bundle_validates_and_carries_tables(contract):
    """Passing gates normalize to a valid bundle with stage rows."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    assert bundle["task"] == "run_digital_flow"
    tables = [d for d in bundle["datasets"] if d["kind"] == "table"]
    assert len(tables) == 2
    stage = tables[0]
    assert stage["row_count"] == 2
    ids = {d["id"] for d in bundle["datasets"]}
    assert bundle["views"]
    assert all(v["dataset_id"] in ids for v in bundle["views"])


def test_lvs_and_drc_measurements_keep_status(contract):
    """LVS-match and DRC-total ride measurements with PASS status."""
    bundle = _normalize(GOOD)
    assert not check(contract, bundle)
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["lvs_match"]["status"] == "PASS"
    assert by_name["drc_total"]["status"] == "PASS"
    assert by_name["drc_total"]["value"]["value"] == pytest.approx(0.0)


def test_bad_bundle_reports_failed_gate(contract):
    """A failed gate becomes an error finding, never clean."""
    bundle = _normalize(BAD, run_id="run-flow-bad")
    assert not check(contract, bundle)
    assert bundle["findings"]
    assert bundle["findings"][0]["code"] == "digital_flow_gate"
    assert all(f["severity"] == "error" for f in bundle["findings"])
    by_name = {m["name"]: m for m in bundle["measurements"]}
    assert by_name["lvs_match"]["status"] == "FAIL"


def test_long_diagnostics_are_capped_and_deterministic(contract):
    """Long tool text is capped and repeat calls are byte-identical."""
    parsed = dict(BAD)
    parsed["violations"] = [
        {
            "rule": "digital_flow_gate",
            "severity": "error",
            "message": "f" * 5000,
        },
    ]
    first = _normalize(parsed, run_id="run-flow-cap")
    second = _normalize(parsed, run_id="run-flow-cap")
    assert not check(contract, first)
    assert first == second
    assert all(len(f["message"]) <= 240 for f in first["findings"])
