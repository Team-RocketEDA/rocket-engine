"""B3 RED — I05 caller parity, I06 retries/stale writes, I07 event recovery.

Tests assume `rocket_engine.project.ProjectService` backed by a fake
adapter (real adapter qualification waits for slice 4). Valid RED =
the import itself fails.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_caller_parity_human_and_agent_same_effects():
    from rocket_engine.project import ProjectService  # RED: missing surface

    command = (FIXTURES / "commands" / "run_drc.yaml").read_text()
    human = ProjectService(project_id="analog_demo", actor={"kind": "user"})
    agent = ProjectService(project_id="analog_demo", actor={"kind": "agent"})
    ack_human = human.submit(command, request_id="req-human-1")
    ack_agent = agent.submit(command, request_id="req-agent-1")
    assert ack_human["snapshot_id"] == ack_agent["snapshot_id"]
    assert ack_human["state"] == ack_agent["state"] == "queued"
    assert ack_human["run_id"] != ack_agent["run_id"]


def test_retry_returns_same_handle_changed_payload_conflicts():
    from rocket_engine.project import ProjectService  # RED: missing surface

    service = ProjectService(project_id="analog_demo", actor={"kind": "user"})
    command = (FIXTURES / "commands" / "run_drc.yaml").read_text()
    first = service.submit(command, request_id="req-retry-1")
    retry = service.submit(command, request_id="req-retry-1")
    assert retry["run_id"] == first["run_id"]
    with pytest.raises(Exception) as excinfo:
        service.submit(command.replace("run_drc", "run_lvs"), request_id="req-retry-1")
    assert _code(excinfo) == "request_conflict"


def test_stale_revision_write_rejected_without_effects():
    from rocket_engine.project import ProjectService  # RED: missing surface

    service = ProjectService(project_id="analog_demo", actor={"kind": "user"})
    before = service.snapshot()["event_cursor"]
    with pytest.raises(Exception) as excinfo:
        service.submit(
            (FIXTURES / "commands" / "run_drc.yaml").read_text(),
            request_id="req-stale-1",
            expected_revision="p11",
        )
    assert _code(excinfo) == "revision_conflict"
    assert service.snapshot()["event_cursor"] == before


def test_event_recovery_duplicate_gap_resync():
    from rocket_engine.project import ProjectService  # RED: missing surface

    service = ProjectService(project_id="analog_demo", actor={"kind": "user"})
    snapshot = service.snapshot()
    cursor = snapshot["event_cursor"]
    service.submit(
        (FIXTURES / "commands" / "run_drc.yaml").read_text(),
        request_id="req-events-1",
    )
    events = service.events_since(cursor)
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    replay = service.events_since(cursor)
    assert [e["seq"] for e in replay] == [e["seq"] for e in events]
    with pytest.raises(Exception) as excinfo:
        service.events_since(cursor=0, require_contiguous_from=10**9)
    assert _code(excinfo) == "resync_required"
