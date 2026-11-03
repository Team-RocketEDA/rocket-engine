"""I27-GATE unit lane: plan_checks + design-completion gate (RED-first).

Proves the new `workflows.completion` surface directly (no Engine
wiring needed): mixed M14 + run_thermal surface as named blockers,
blocked stages refuse fully-verified claims, unblocked stages claim
with evidence refs. Wiring to `Engine.submit` rides the integrator
patch; see `test_completion_wiring.py` (skips pre-patch).
"""

import pytest

SCRIPTED = frozenset({"project scripting", "get_capabilities", "ip_instantiate"})


def _live_ops():
    """Registered solver operations on a stock in-memory Engine."""
    from rocket_engine.composition import Engine

    engine = Engine("probe-i27", actor="probe")
    kinds = engine.job_kinds()["job_kinds"]
    return {entry["operation"] for entry in kinds}


def _mixed_tool_ops():
    """Every tool entrypoint the mixed flow needs (scripted excluded)."""
    from rocket_engine.workflows import STAGES

    ops = set()
    for stage in STAGES["mixed"]:
        for entry in stage["entrypoints"]:
            if entry not in SCRIPTED:
                ops.add(entry)
    return ops


def _pass_checks(ops):
    """All-PASS check records with stable run ids for `ops`."""
    return {
        op: {
            "run_id": f"run-{op}",
            "state": "completed",
            "status": "PASS",
            "verdict": {"status": "PASS", "finding_counts": {}},
        }
        for op in ops
    }


def test_plan_mixed_m14_blocked_on_live_solvers():
    from rocket_engine.workflows.completion import plan_checks_report

    plan = plan_checks_report("mixed", _live_ops())
    assert "M14" in plan["blocked_stages"]
    m14 = next(s for s in plan["stages"] if s["id"] == "M14")
    assert m14["required"] is True
    assert m14["readiness"] == "blocked"
    assert m14["missing_operations"] == ["run_thermal"]
    assert "run_thermal" in plan["missing_operations"]


def test_plan_digital_all_ready_on_live_solvers():
    from rocket_engine.workflows.completion import plan_checks_report

    plan = plan_checks_report("digital", _live_ops())
    assert plan["blocked_stages"] == []
    assert plan["missing_operations"] == []
    assert len(plan["ready_stages"]) == len(plan["stages"])


def test_plan_missing_backend_keeps_stage_required():
    from rocket_engine.workflows.completion import plan_checks_report

    plan = plan_checks_report("digital", {"run_syntax", "run_hdl_test"})
    d25 = next(s for s in plan["stages"] if s["id"] == "D25")
    assert d25["required"] is True
    assert d25["readiness"] == "blocked"
    assert d25["missing_operations"] == ["run_drc"]


def test_plan_rejects_unknown_flow():
    from rocket_engine.workflows.completion import plan_checks_report

    with pytest.raises(ValueError, match="Unknown flow"):
        plan_checks_report("nope", _live_ops())


def test_plan_report_shape_partitions_stages():
    from rocket_engine.workflows.completion import plan_checks_report

    plan = plan_checks_report("mixed", _live_ops())
    ids = [s["id"] for s in plan["stages"]]
    assert sorted(plan["blocked_stages"] + plan["ready_stages"]) == sorted(ids)
    assert plan["missing_operations"] == sorted(plan["missing_operations"])
    for stage in plan["stages"]:
        assert stage["readiness"] in ("ready", "blocked")
        assert isinstance(stage["missing_operations"], list)


def test_run_thermal_is_vocab_only_live():
    from rocket_engine.composition import Engine
    from rocket_engine.interfaces.vocabulary import OPERATIONS
    from rocket_engine.project.errors import ProjectError

    assert "run_thermal" in OPERATIONS
    engine = Engine("probe-i27", actor="probe")
    assert "run_thermal" not in engine.solvers_for("run_thermal")
    with pytest.raises(ProjectError) as caught:
        engine.submit(
            {
                "project_id": "probe-i27",
                "operation": "run_thermal",
                "arguments": {},
                "request_id": "i27-thermal-probe",
            }
        )
    assert caught.value.code == "unsupported_operation"
    assert "No solver registered: run_thermal" in str(caught.value)


def test_completion_mixed_refuses_with_m14_and_thermal_named():
    from rocket_engine.workflows.completion import design_completion_report

    report = design_completion_report("mixed", _live_ops(), {}, 7)
    assert report["fully_verified"] is False
    assert report["claim"] is None
    assert report["refusal"] is not None
    assert report["current_revision"] == 7
    kinds = {(b.get("stage"), b.get("kind")) for b in report["blockers"]}
    assert ("M14", "blocked_stage") in kinds
    m14 = next(b for b in report["blockers"] if b.get("stage") == "M14")
    assert m14["missing_operations"] == ["run_thermal"]
    assert "run_thermal" in report["missing_operations"]
    thermal = [b for b in report["blockers"] if b.get("operation") == "run_thermal"]
    assert thermal, "run_thermal must appear as a named blocker"


def test_completion_all_pass_still_blocked_without_thermal():
    from rocket_engine.workflows.completion import design_completion_report

    ops = _live_ops()
    mixed_ops = {op for op in _mixed_tool_ops() if op in ops}
    report = design_completion_report("mixed", ops, _pass_checks(mixed_ops))
    assert report["fully_verified"] is False
    assert any(b.get("stage") == "M14" for b in report["blockers"])
    assert "run_thermal" in report["missing_operations"]


def test_completion_unblocked_claims_with_evidence_refs():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    assert "run_thermal" in available
    checks = _pass_checks(available)
    report = design_completion_report("mixed", available, checks, 9)
    assert report["fully_verified"] is True
    assert report["claim"] == "fully verified"
    assert report["refusal"] is None
    assert report["blockers"] == []
    assert report["missing_operations"] == []
    for op in available:
        assert report["evidence"][op] == f"run-{op}"
    assert report["current_revision"] == 9


def test_completion_two_passes_do_not_look_fully_verified():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    checks = _pass_checks({"run_spice", "run_hdl_test"})
    report = design_completion_report("mixed", available, checks)
    assert report["fully_verified"] is False
    stages = {b.get("stage") for b in report["blockers"] if b.get("stage")}
    assert "M09" in stages
    assert "M10" in stages


def test_completion_failing_check_refuses_and_names_run():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    checks = _pass_checks(available)
    checks["run_drc"] = {
        "run_id": "run-drc-bad",
        "state": "completed",
        "status": "FAIL",
        "verdict": {"status": "FAIL", "finding_counts": {"error": 2}},
    }
    report = design_completion_report("mixed", available, checks)
    assert report["fully_verified"] is False
    failing = [b for b in report["blockers"] if b.get("kind") == "failing_check"]
    assert any(
        b["stage"] == "M09" and b["operation"] == "run_drc"
        and b["status"] == "FAIL" and b["run_id"] == "run-drc-bad"
        for b in failing
    )


def test_completion_not_run_refuses():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    checks = _pass_checks(available)
    checks["run_lvs"]["status"] = "NOT_RUN"
    checks["run_lvs"]["verdict"] = {"status": "NOT_RUN", "reason": "nope"}
    report = design_completion_report("mixed", available, checks)
    assert report["fully_verified"] is False
    assert any(
        b.get("kind") == "failing_check" and b.get("operation") == "run_lvs"
        and b.get("status") == "NOT_RUN" for b in report["blockers"]
    )


def test_completion_never_run_is_unverified_blocker():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    checks = _pass_checks(available)
    del checks["run_extraction"]
    report = design_completion_report("mixed", available, checks)
    assert report["fully_verified"] is False
    assert any(
        b.get("kind") == "unverified_stage" and b.get("stage") == "M10"
        and b.get("operation") == "run_extraction"
        and b.get("status") == "never_run" for b in report["blockers"]
    )


def test_completion_scripted_stages_need_no_evidence():
    from rocket_engine.workflows.completion import design_completion_report

    available = set(_mixed_tool_ops())
    report = design_completion_report("mixed", available, _pass_checks(available))
    assert report["fully_verified"] is True
    scripted = {"M01", "M02", "M03"}
    by_id = {s["id"]: s for s in report["stages"]}
    for stage_id in scripted:
        assert by_id[stage_id]["stage_status"] == "verified"


def test_completion_stages_carry_status():
    from rocket_engine.workflows.completion import design_completion_report

    report = design_completion_report("mixed", _live_ops(), {})
    by_id = {s["id"]: s for s in report["stages"]}
    assert by_id["M14"]["stage_status"] == "blocked"
    assert by_id["M01"]["stage_status"] == "verified"
    assert by_id["M09"]["stage_status"] == "unverified"


def test_completion_rejects_unknown_flow():
    from rocket_engine.workflows.completion import design_completion_report

    with pytest.raises(ValueError, match="Unknown flow"):
        design_completion_report("nope", _live_ops(), {})
