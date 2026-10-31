"""SETUP-HONESTY: capability-aware stage readiness.

`plan_from_capabilities` plans a flow against the capability
report's operations mapping instead of bare wiring: a stage is
ready only when every tool entrypoint it needs reads ready, and a
blocked stage names its blockers with reason, missing items, and
remedy. The no-sta M11 case is the pinning regression.
"""

import pytest


def _ready(tools=None):
    return {"readiness": "ready", "tools": tools or {}}


def _blocked(reason, missing, remedy, tools=None):
    return {
        "readiness": "blocked",
        "reason": reason,
        "missing": missing,
        "remedy": remedy,
        "tools": tools or {},
    }


def _unsupported(reason):
    return {"readiness": "unsupported", "reason": reason, "tools": {}}


def _by_id(planned):
    return {stage["id"]: stage for stage in planned}


def test_unknown_flow_raises():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    with pytest.raises(ValueError, match="Unknown flow"):
        plan_from_capabilities("quantum", {})


def test_ready_report_marks_stage_ready_without_blocker_keys():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    planned = _by_id(plan_from_capabilities(
        "mixed", {"run_timing": _ready({"opensta": {"available": True}})}
    ))

    assert planned["M11"]["readiness"] == "ready"
    assert "blocked_by" not in planned["M11"]
    assert planned["M11"]["required"] is True


def test_missing_sta_blocks_m11_with_remedy():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    operations = {
        "run_timing": _blocked(
            "No run_timing tool resolves on this machine.",
            ["sta"],
            "Install the pinned OpenSTA build 857316f "
            "(scripts/provision_toolchain.sh --install).",
        ),
    }

    m11 = _by_id(plan_from_capabilities("mixed", operations))["M11"]

    assert m11["readiness"] == "blocked"
    assert m11["required"] is True
    assert m11["blocked_by"] == ["run_timing"]
    assert "run_timing" in m11["reason"]
    assert m11["missing"] == ["sta"]
    assert "OpenSTA" in m11["remedy"]


def test_unreported_entrypoint_blocks_loudly():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    m11 = _by_id(plan_from_capabilities("mixed", {}))["M11"]

    assert m11["readiness"] == "blocked"
    assert m11["blocked_by"] == ["run_timing"]
    assert "run_timing" in m11["reason"]
    assert "no capability report" in m11["reason"]
    assert m11["missing"] == ["run_timing"]
    assert m11["remedy"].strip()


def test_unsupported_operation_blocks_with_fallback_remedy():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    operations = {
        "run_em": _ready(),
        "run_spice": _ready(),
        "run_thermal": _unsupported("No solver registered: run_thermal."),
    }

    m14 = _by_id(plan_from_capabilities("mixed", operations))["M14"]

    assert m14["readiness"] == "blocked"
    assert m14["blocked_by"] == ["run_thermal"]
    assert "No solver registered" in m14["reason"]
    assert m14["remedy"].strip()


def test_scripted_entrypoints_need_no_backend():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    planned = _by_id(plan_from_capabilities("mixed", {}))

    assert planned["M01"]["readiness"] == "ready"
    assert planned["M02"]["readiness"] == "ready"


def test_multi_entrypoint_stage_unions_blockers():
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    operations = {
        "run_drc": _ready(),
        "run_erc": _ready(),
        "run_lvs": _blocked(
            "No run_lvs tool resolves on this machine.",
            ["netgen"],
            "Install opencircuitdesign netgen from source.",
        ),
    }

    m09 = _by_id(plan_from_capabilities("mixed", operations))["M09"]

    assert m09["readiness"] == "blocked"
    assert m09["blocked_by"] == ["run_lvs"]
    assert m09["missing"] == ["netgen"]
    assert "netgen" in m09["remedy"]


def test_live_engine_report_plans_honestly(tmp_path):
    import shutil

    from rocket_engine.composition import Engine
    from rocket_engine.workflows.capability_plan import plan_from_capabilities

    engine = Engine("setup-honesty", actor="setup-honesty")
    report = engine.submit(
        {
            "project_id": "setup-honesty",
            "operation": "get_capabilities",
            "arguments": {"engine_root": str(tmp_path / "nostore")},
            "request_id": "setup-honesty-1",
        }
    )

    planned = _by_id(plan_from_capabilities("mixed", report["operations"]))
    timing = report["operations"]["run_timing"]
    m11 = planned["M11"]

    assert m11["readiness"] == timing["readiness"]
    if timing["readiness"] != "ready":
        assert m11["blocked_by"] == ["run_timing"]
        assert set(timing.get("missing", [])) <= set(m11["missing"])
        if timing.get("remedy"):
            assert timing["remedy"] in m11["remedy"]
    if shutil.which("sta") is None:
        assert m11["readiness"] == "blocked"
        assert "sta" in m11["missing"]
