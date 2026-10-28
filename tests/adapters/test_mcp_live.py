"""B9 MCP-LIVE RED — McpTransport wired to the real engine root.

Valid RED = `rocket_engine.composition.Engine` does not exist yet, so
every test fails on ImportError. No native tool is touched: any RED
caused by a missing tool would be invalid.
"""

import json

PROJECT = "analog_demo"


def _call(name, arguments, call_id="req_live_001"):
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )


def _submit_args(**over):
    args = {"project_id": PROJECT, "expected_revision": "p12"}
    args.update(over)
    return args


def _transport(engine):
    from rocket_engine.adapters.mcp import McpTransport  # live surface

    return McpTransport(engine, project_id=PROJECT)


def test_mcp_submit_round_trips_through_real_engine():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    ack = _transport(engine).handle(_call("run_drc", _submit_args()))
    assert ack["state"] == "queued"
    assert {"run_id", "snapshot_id", "event_cursor"} <= set(ack)
    assert engine.snapshot()["event_cursor"] == 1


def test_mcp_submit_is_idempotent_on_envelope_id():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    text = _call("run_drc", _submit_args())
    first = _transport(engine).handle(text)
    second = _transport(engine).handle(text)
    assert first == second


def test_mcp_submit_rejects_stale_revision():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    try:
        _transport(engine).handle(_call("run_drc", _submit_args(expected_revision="p11")))
    except Exception as exc:
        assert getattr(exc, "code", None) == "revision_conflict"
    else:
        raise AssertionError("expected revision_conflict")


def test_mcp_query_snapshot_reads_real_state():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    transport = _transport(engine)
    transport.handle(_call("run_drc", _submit_args(), call_id="req_live_010"))
    snap = transport.handle(
        _call("get_project_snapshot", {"project_id": PROJECT}, call_id="req_live_011")
    )
    assert snap["current_revision"] == "p12"
    assert snap["event_cursor"] == 1


def test_mcp_live_enforces_scope():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    try:
        _transport(engine).handle(
            _call("run_drc", _submit_args(project_id="other_project"))
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "cross_project_denied"
    else:
        raise AssertionError("expected cross_project_denied")


def test_mcp_rejects_envelope_without_project():
    from rocket_engine.composition import Engine  # RED: missing root

    engine = Engine(PROJECT, actor="tester")
    args = _submit_args()
    del args["project_id"]
    try:
        _transport(engine).handle(_call("run_drc", args))
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command, not a bare KeyError")
