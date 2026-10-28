"""B4 RED — I08 immutable inputs, I09 evidence authority, I10 bounded
output, I11 cancellation races, I22 executable-input approval.

Tests assume `rocket_engine.execution.ExecutionService`. Valid RED =
the import itself fails.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def test_long_run_keeps_original_snapshot_after_source_change():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    run = service.dispatch(
        operation="run_drc", target="amplifier", snapshot_id="snapshot_012"
    )
    service.note_source_change(revision="p13")
    evidence = service.evidence(run["run_id"])
    assert evidence["snapshot_id"] == "snapshot_012"
    assert evidence["freshness"] == "stale"


def test_exit_zero_with_violations_stays_fail():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    verdict = service.evaluate(
        run_id="run_drc_001",
        exit_code=0,
        findings_fixture=(FIXTURES / "findings" / "drc_fail.yaml").read_text(),
    )
    assert verdict["status"] == "FAIL"
    assert verdict["finding_counts"] == {"error": 2, "warning": 1}


def test_unparsable_output_is_not_run_not_fail():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    verdict = service.evaluate(
        run_id="run_drc_002", exit_code=0, findings_fixture=":::not findings:::"
    )
    assert verdict["status"] == "NOT_RUN"
    assert "reason" in verdict


def test_bounded_findings_preserve_counts_and_cursors():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    page = service.findings(run_id="run_drc_001", limit=1)
    assert page["total_counts"] == {"error": 2, "warning": 1}
    assert len(page["findings"]) == 1
    assert page["findings"][0]["severity"] == "error"
    assert page["next_cursor"] is not None
    assert page["truncated"] is True


def test_cancel_queued_running_completed_is_truthful():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    queued = service.dispatch(operation="run_drc", target="a", snapshot_id="s1")
    running = service.dispatch(operation="run_drc", target="b", snapshot_id="s1")
    service.mark_running(running["run_id"])
    done = service.dispatch(operation="run_drc", target="c", snapshot_id="s1")
    service.mark_completed(done["run_id"], verdict={"status": "FAIL"})
    assert service.cancel(queued["run_id"])["state"] == "cancelled"
    assert service.cancel(running["run_id"])["state"] in ("cancelled", "completed")
    kept = service.cancel(done["run_id"])
    assert kept["state"] == "completed"
    assert kept["verdict"]["status"] == "FAIL"


def test_executable_closure_change_invalidates_approval():
    from rocket_engine.execution import ExecutionService  # RED: missing surface

    service = ExecutionService(project_id="analog_demo")
    approval = service.request_approval(
        kind="python_factory", closure_hash="abc123", expected_revision="p12"
    )
    assert approval["state"] == "pending_approval"
    with pytest.raises(Exception) as excinfo:
        service.admit(
            approval["approval_id"],
            closure_hash="changed456",
            expected_revision="p12",
        )
    assert getattr(excinfo.value, "code", None) == "approval_invalid"
