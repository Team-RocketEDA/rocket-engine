"""CONSOLE-LIFECYCLE: open/reset/session ops on the shared envelope.

RED: `src/execution/console/lifecycle.py` does not exist yet — every
import below fails until the module lands. Approval binding itself
stays pinned by `tests/execution/test_console.py`; this file owns
identity (console_id), generations, workspace binding, and the
envelope convergence the adapt lane wires `python_open`/
`python_reset` through. No sandbox changes: nothing here spawns a
worker or touches the runner.
"""

import pytest

from rocket_engine.execution.errors import ExecutionError

CODE = "result = project.snapshot()\n"


def _lifecycle():
    from rocket_engine.execution.console.lifecycle import (  # RED
        ConsoleLifecycle,
    )

    return ConsoleLifecycle()


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_open_mints_identity_and_generation():
    service = _lifecycle()
    first = service.open_console(project_id="demo", actor="user")
    assert first["console_id"]
    assert first["generation"]
    assert first["project_id"] == "demo"
    second = service.open_console(project_id="demo", actor="user")
    assert second["console_id"] != first["console_id"]
    assert second["generation"] != first["generation"]


def test_open_reuses_console_for_one_workspace_root(tmp_path):
    """Single console per panel: one live handle per workspace root."""
    service = _lifecycle()
    first = service.open_console(
        project_id="demo", actor="user", workspace_root=str(tmp_path)
    )
    second = service.open_console(
        project_id="demo", actor="user", workspace_root=str(tmp_path)
    )
    assert second["console_id"] == first["console_id"]
    assert second["generation"] == first["generation"]


def test_reset_retires_generation_and_kills_approvals():
    service = _lifecycle()
    opened = service.open_console(project_id="demo", actor="user")
    session = service.session_for(opened["console_id"])
    approval = session.request_cell_approval(
        code=CODE, history_cursor=0, env_digest="env",
        expected_revision="p1",
    )
    reset = service.reset_console(opened["console_id"])
    assert reset["console_id"] == opened["console_id"]
    assert reset["generation"] != opened["generation"]
    status = service.status(opened["console_id"])
    assert status["generation"] == reset["generation"]
    with pytest.raises(ExecutionError) as excinfo:
        session.admit_cell(
            approval["approval_id"], code=CODE, history_cursor=0,
            env_digest="env", expected_revision="p1",
        )
    assert _code(excinfo) == "approval_invalid"


def test_unknown_console_fails_loud(tmp_path):
    service = _lifecycle()
    with pytest.raises(ExecutionError) as excinfo:
        service.status("no-such-console")
    assert _code(excinfo) == "unknown_console"
    with pytest.raises(ExecutionError) as excinfo:
        service.reset_console("no-such-console")
    assert _code(excinfo) == "unknown_console"
    with pytest.raises(ExecutionError) as excinfo:
        service.close_console("no-such-console")
    assert _code(excinfo) == "unknown_console"


def test_close_releases_workspace_root(tmp_path):
    service = _lifecycle()
    opened = service.open_console(
        project_id="demo", actor="user", workspace_root=str(tmp_path)
    )
    assert service.close_console(opened["console_id"])["closed"] is True
    reopened = service.open_console(
        project_id="demo", actor="user", workspace_root=str(tmp_path)
    )
    assert reopened["console_id"] != opened["console_id"]
    with pytest.raises(ExecutionError) as excinfo:
        service.status(opened["console_id"])
    assert _code(excinfo) == "unknown_console"


def test_console_envelopes_round_trip_on_shared_shape():
    """Lifecycle commands render through the shared envelope dumper."""
    from rocket_engine.execution.console.lifecycle import (  # RED
        console_envelope,
        parse_console_envelope,
    )

    for operation, arguments in [
        ("python_open", {"project_id": "demo"}),
        ("python_execute", {"console_id": "c1", "code": CODE}),
        ("python_reset", {"console_id": "c1"}),
    ]:
        text = console_envelope(operation, arguments)
        assert parse_console_envelope(text) == {
            "operation": operation,
            "arguments": arguments,
        }


def test_console_envelopes_reject_off_shape():
    from rocket_engine.execution.console.lifecycle import (  # RED
        console_envelope,
        parse_console_envelope,
    )

    with pytest.raises(ExecutionError) as excinfo:
        console_envelope("run_drc", {"target": "amp"})
    assert _code(excinfo) == "invalid_command"
    with pytest.raises(ExecutionError) as excinfo:
        parse_console_envelope("not: [valid, console")
    assert _code(excinfo) == "invalid_command"
    with pytest.raises(ExecutionError) as excinfo:
        parse_console_envelope("operation: run_drc\narguments: {}\n")
    assert _code(excinfo) == "invalid_command"
