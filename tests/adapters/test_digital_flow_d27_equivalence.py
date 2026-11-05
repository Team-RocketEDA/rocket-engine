"""D27 regression: the equivalence gate must judge the flow's real evidence.

LibreLane Classic 3.0.17 runs no eqy/equiv/signoff/finish step, so a D27
gate that only matches those substrings can never pass — every clean run
fails it. The flow DOES emit equivalence-grade evidence: netgen LVS vs
reference (unmatched-device/net/pin counts, 0 means match) plus the
final/ metrics. D27 must pass on that evidence and still fail loudly
when it is genuinely absent (gate stays strict, just pointed right).

All other gates are force-bypassed so the test judges D27's own
verdict, not the blocked-by-earlier-gates cascade.
"""

import json

from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

ADAPTER = LibrelaneFlowAdapter()
OTHERS = [f"D{i:02d}" for i in range(11, 27)]

LVS_STATE = {
    "metrics": {
        "design__lvs_unmatched_device__count": 0,
        "design__lvs_unmatched_net__count": 0,
        "design__lvs_unmatched_pin__count": 0,
    }
}
FINAL_CSV = "Metric,Value\ndesign__instance__count,100\n"


def _native(run_dir, tag):
    cfg = run_dir.parent / "digital_flow_config.json"
    cfg.write_text(json.dumps({"DESIGN_NAME": "t", "VERILOG_FILES": []}))
    return {
        "exit_code": 0,
        "timed_out": False,
        "run_dir": str(run_dir),
        "config": str(cfg),
        "top": "t",
        "tag": tag,
        "pdk": "sky130A",
        "flow": "Classic",
        "forced": list(OTHERS),
        "librelane_version": "LibreLane v3.0.17",
        "timeout_s": 3600,
    }


def _d27(parsed):
    return [v for v in parsed["violations"] if v["message"].startswith("D27 ")]


def test_d27_passes_on_netgen_lvs_plus_final(tmp_path):
    """Classic-shaped clean run: netgen LVS match + final/ metrics, no eqy step."""
    run = tmp_path / "design" / "runs" / "v1"
    step = run / "70-netgen-lvs"
    step.mkdir(parents=True)
    (step / "state_out.json").write_text(json.dumps(LVS_STATE))
    final = run / "final"
    final.mkdir()
    (final / "metrics.csv").write_text(FINAL_CSV)
    parsed = ADAPTER.parse(_native(run, "v1"))
    assert _d27(parsed) == [], (
        f"D27 must pass on netgen-LVS + final evidence: {_d27(parsed)}"
    )


def test_d27_still_fails_without_equivalence_evidence(tmp_path):
    """No LVS/final steps at all: the gate must fail loudly, not go green."""
    run = tmp_path / "design" / "runs" / "v1"
    step = run / "06-yosys-synthesis"
    step.mkdir(parents=True)
    (step / "state_out.json").write_text(json.dumps({"metrics": {}}))
    parsed = ADAPTER.parse(_native(run, "v1"))
    viol = _d27(parsed)
    assert len(viol) == 1, f"D27 must fail with no equivalence evidence: {viol}"
    assert "machine-file metrics" in viol[0]["message"]
