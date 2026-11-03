"""Plan target+canvas gating (WIRE-DECLARED-OPS MC-25 remainder).

`plan_checks_report` plans a flow against backends only; the gate
scopes that plan to a v1 target and canvas: every stage names its
deck tools, the canvas tool settings joined to those tools, and
the project-top metric budgets it must satisfy, so cost
(settings) and evidence travel with the plan instead of living
in a separate display.
"""

TARGET = {"kind": "project", "project_id": "bandgap"}

CANVAS = {
    "targets": [
        {
            "metric": "gain_db",
            "operator": "ge",
            "limit": {"value": 60.0, "unit": "dB"},
        },
        {
            "metric": "vbg_v",
            "operator": "eq",
            "limit": {"value": 1.2, "unit": "V"},
            "target": "A06",
        },
    ],
    "tools": {"ngspice": {"profile": "sky130"},
              "xyce": {"profile": "sky130"}},
}


def _plan():
    from rocket_engine.workflows.completion import plan_checks_report

    return plan_checks_report("analog", {"run_spice", "run_syntax"})


def test_gate_rejects_bad_target_and_canvas():
    import pytest

    from rocket_engine.workflows.gates import gate_plan_for_target

    plan = _plan()
    with pytest.raises(ValueError):
        gate_plan_for_target(plan, {"project_id": "no-kind"})
    with pytest.raises(ValueError):
        gate_plan_for_target(plan, "project")
    with pytest.raises(ValueError):
        gate_plan_for_target(plan, TARGET, canvas=["not-a-mapping"])


def test_gate_scopes_tools_budgets_evidence_to_stages():
    from rocket_engine.workflows.gates import gate_plan_for_target

    gated = gate_plan_for_target(_plan(), TARGET, CANVAS)
    assert gated["target"] == {"kind": "project", "project_id": "bandgap"}
    assert gated["canvas_metrics"] == ["gain_db", "vbg_v"]
    assert gated["canvas_tools"] == ["ngspice", "xyce"]
    spice = next(s for s in gated["stages"] if s["id"] == "A06")
    assert "run_spice" in spice["entrypoints"]
    assert spice["canvas_tools"] == {"ngspice": {"profile": "sky130"}}
    assert spice["evidence"]
    assert [b["metric"] for b in spice["budgets"]] == ["gain_db"]
    scripted = next(s for s in gated["stages"]
                    if s["id"] == "A05")
    assert scripted["canvas_tools"] == {}
    assert [b["metric"] for b in scripted["budgets"]] == ["gain_db"]


def test_plan_checks_accepts_target_and_canvas():
    from rocket_engine.workflows.completion import plan_checks_report

    plain = plan_checks_report("analog", {"run_spice"})
    assert "target" not in plain
    gated = plan_checks_report("analog", {"run_spice"}, TARGET, CANVAS)
    assert gated["flow"] == "analog"
    assert gated["target"]["kind"] == "project"
    assert gated["blocked_stages"] == plain["blocked_stages"]
    assert gated["missing_operations"] == plain["missing_operations"]
