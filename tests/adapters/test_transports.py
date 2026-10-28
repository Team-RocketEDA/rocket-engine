"""B5+B9 RED — I05/I12 transport parity vs a fake engine, I19 harness
boundary, plus contract-level solver-port RED.

Transport tests assume one duplex class per submodule; solver tests
assume the `ToolAdapter` port on `rocket_engine.adapters`. Valid RED =
each import itself fails. No native tool is touched: any RED caused by
a missing tool would be invalid.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


class FakeEngine:
    """In-test fake: records the normalized command it received."""

    def __init__(self):
        self.received = []

    def submit(self, command):
        self.received.append(command)
        return {"state": "queued", "run_id": "run_fake_001"}


def test_api_ipc_mcp_submit_identical_commands():
    from rocket_engine.adapters.api import ApiTransport  # RED: missing surface
    from rocket_engine.adapters.ipc import IpcTransport  # RED: missing surface
    from rocket_engine.adapters.mcp import McpTransport  # RED: missing surface

    engine = FakeEngine()
    ApiTransport(engine).handle((FIXTURES / "api" / "request.json").read_text())
    IpcTransport(engine).handle((FIXTURES / "ipc" / "frame.json").read_text())
    McpTransport(engine).handle((FIXTURES / "mcp" / "tool_call.json").read_text())
    commands = engine.received
    assert len(commands) == 3
    normalized = [{k: c[k] for k in ("project_id", "operation")} for c in commands]
    assert normalized[0] == normalized[1] == normalized[2]


def test_transports_reject_cross_project_calls():
    from rocket_engine.adapters.ipc import IpcTransport  # RED: missing surface

    engine = FakeEngine()
    frame = json.loads((FIXTURES / "ipc" / "frame.json").read_text())
    frame["project_id"] = "other_project"
    try:
        IpcTransport(engine, project_id="analog_demo").handle(json.dumps(frame))
    except Exception as exc:
        assert getattr(exc, "code", None) == "cross_project_denied"
    else:
        raise AssertionError("expected cross_project_denied")


def test_mcp_never_substitutes_host_or_console_routes():
    from rocket_engine.adapters.mcp import McpTransport  # RED: missing surface

    engine = FakeEngine()
    transport = McpTransport(engine)
    assert transport.host_execution_enabled is False
    try:
        transport.handle(json.dumps({"method": "tools/call", "params": {"name": "host_shell"}}))
    except Exception as exc:
        assert getattr(exc, "code", None) in ("unsupported_operation", "unsupported_check")
    else:
        raise AssertionError("expected host_shell to be rejected")


def test_solver_port_exists_before_any_solver():
    from rocket_engine.adapters import ToolAdapter  # RED: missing surface

    assert {"capabilities", "preflight", "execute", "parse"} <= set(dir(ToolAdapter))
