"""I27-GATE wiring lane: Engine.submit plan_checks + completion (post-patch).

Every test skips loudly while the integrator patch is unapplied
(`unsupported_operation` on either query name) and runs with zero
skips after it. The fake-PASS adapter proves the unblocked claim
end to end without touching live tools.
"""

import pytest

from rocket_engine.composition import Engine
from rocket_engine.project.errors import ProjectError


class _FakePassAdapter:
    """Trivial solver that always passes (no tools, no I/O)."""

    def preflight(self, job):
        return None

    def execute(self, job):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    def parse(self, native):
        return {"violations": []}


def _engine():
    return Engine("wire-i27", actor="probe")


def _submit(engine, operation, arguments, request_id):
    """Submit once; skip when the wiring patch is unapplied."""
    try:
        return engine.submit(
            {
                "project_id": "wire-i27",
                "operation": operation,
                "arguments": arguments,
                "request_id": request_id,
            }
        )
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip("wiring patch not applied: I27 queries unwired")
        raise


def _mixed_tool_ops():
    from rocket_engine.workflows import STAGES

    scripted = {"project scripting", "get_capabilities", "ip_instantiate"}
    ops = set()
    for stage in STAGES["mixed"]:
        for entry in stage["entrypoints"]:
            if entry not in scripted:
                ops.add(entry)
    return ops


def test_wired_plan_checks_names_m14_and_thermal():
    plan = _submit(_engine(), "plan_checks", {"flow": "mixed"}, "i27-w-plan")
    assert plan["flow"] == "mixed"
    assert "M14" in plan["blocked_stages"]
    m14 = next(s for s in plan["stages"] if s["id"] == "M14")
    assert m14["missing_operations"] == ["run_thermal"]
    assert "run_thermal" in plan["missing_operations"]


def test_wired_completion_refuses_mixed_live():
    report = _submit(
        _engine(), "get_design_completion", {"flow": "mixed"}, "i27-w-refuse"
    )
    assert report["fully_verified"] is False
    assert report["claim"] is None
    assert any(b.get("stage") == "M14" for b in report["blockers"])
    assert "run_thermal" in report["missing_operations"]
    assert any(b.get("operation") == "run_thermal" for b in report["blockers"])


def test_wired_plan_checks_needs_flow():
    engine = _engine()
    try:
        engine.submit(
            {
                "project_id": "wire-i27",
                "operation": "plan_checks",
                "arguments": {},
                "request_id": "i27-w-plan-noflow",
            }
        )
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip("wiring patch not applied: I27 queries unwired")
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("plan_checks without flow must refuse")


def test_wired_plan_checks_rejects_unknown_flow():
    engine = _engine()
    with pytest.raises(ProjectError) as caught:
        _submit(engine, "plan_checks", {"flow": "nope"}, "i27-w-plan-bad")
    assert caught.value.code == "invalid_command"


def test_wired_completion_needs_flow():
    engine = _engine()
    try:
        engine.submit(
            {
                "project_id": "wire-i27",
                "operation": "get_design_completion",
                "arguments": {},
                "request_id": "i27-w-comp-noflow",
            }
        )
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip("wiring patch not applied: I27 queries unwired")
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("completion without flow must refuse")


def test_wired_completion_rejects_unknown_flow():
    engine = _engine()
    with pytest.raises(ProjectError) as caught:
        _submit(engine, "get_design_completion", {"flow": "nope"}, "i27-w-comp-bad")
    assert caught.value.code == "invalid_command"


def test_wired_queries_registered_for_docs():
    from rocket_engine.composition import QUERY_ENGINE_METHODS

    if (
        QUERY_ENGINE_METHODS.get("plan_checks") != "plan_checks"
        or QUERY_ENGINE_METHODS.get("get_design_completion")
        != "design_completion"
    ):
        pytest.skip("wiring patch not applied: I27 queries unwired")
    assert QUERY_ENGINE_METHODS["plan_checks"] == "plan_checks"
    assert QUERY_ENGINE_METHODS["get_design_completion"] == "design_completion"


def test_wired_unblocked_claims_with_fake_thermal():
    engine = _engine()
    _submit(engine, "get_design_completion", {"flow": "mixed"}, "i27-w-probe")
    for op in sorted(_mixed_tool_ops()):
        engine.register_solver(op, _FakePassAdapter(), tool="fake")
    for op in sorted(_mixed_tool_ops()):
        head = engine.snapshot()["current_revision"]
        completion = engine.submit(
            {
                "project_id": "wire-i27",
                "operation": op,
                "arguments": {
                    "deck": {"tool": "fake"},
                    "expected_revision": head,
                },
                "request_id": f"i27-fake-{op}",
            }
        )
        assert completion["verdict"]["status"] == "PASS", op
    report = _submit(
        engine, "get_design_completion", {"flow": "mixed"}, "i27-w-claim"
    )
    assert report["fully_verified"] is True
    assert report["claim"] == "fully verified"
    assert report["blockers"] == []
    for op in _mixed_tool_ops():
        assert report["evidence"][op], op
