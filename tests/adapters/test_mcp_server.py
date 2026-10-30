"""MCP-SERVER RED — connectable stdio server over the MCP SDK.

Valid RED = rocket_engine.adapters.mcp.server does not exist, so
every test fails on ImportError. The transport unit (McpTransport)
already routes tools/call; this slice adds the wire server real
MCP clients speak: initialize + tools/list + tools/call over
stdio, one tool per cataloged operation/query.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

PROJECT = "analog_demo"


def _load():
    # RED: module missing.
    import importlib

    return importlib.import_module("rocket_engine.adapters.mcp.server")


def _fake_engine():
    class FakeEngine:
        def __init__(self):
            self.submitted = []

        def submit(self, command):
            self.submitted.append(command)
            return {"state": "queued", "run_id": "r1",
                    "snapshot_id": "s1", "event_cursor": 1}

    return FakeEngine()


def _call_params(name, arguments):
    from mcp.types import CallToolRequestParams

    return CallToolRequestParams(name=name, arguments=arguments)


def _text(result):
    return result.content[0].text


def test_server_lists_every_cataloged_operation_and_query():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    module = _load()
    tools = module.tool_definitions()
    names = {tool.name for tool in tools}
    assert set(OPERATIONS) <= names
    assert set(QUERIES) <= names


def test_server_call_routes_envelope_to_engine():
    module = _load()
    engine = _fake_engine()
    _, call = module.make_handlers(lambda project_id: engine)
    result = asyncio.run(_call(
        call, "run_drc",
        {"project_id": PROJECT, "expected_revision": "p12"},
    ))
    assert len(engine.submitted) == 1
    command = engine.submitted[0]
    assert command["project_id"] == PROJECT
    assert command["operation"] == "run_drc"
    assert command["arguments"]["expected_revision"] == "p12"
    assert command["request_id"]
    assert json.loads(_text(result))["state"] == "queued"


def _call(handler, name, arguments):
    return handler(None, _call_params(name, arguments))


def test_server_rejects_unknown_tool_without_routing():
    module = _load()
    engine = _fake_engine()
    _, call = module.make_handlers(lambda project_id: engine)
    result = asyncio.run(_call(call, "rm_rf", {"project_id": PROJECT}))
    assert engine.submitted == []
    assert "unsupported" in _text(result).lower()


def test_server_rejects_missing_project_id():
    module = _load()
    engine = _fake_engine()
    _, call = module.make_handlers(lambda project_id: engine)
    result = asyncio.run(_call(call, "run_drc", {}))
    assert engine.submitted == []
    assert "project_id" in _text(result).lower()


def test_server_returns_error_result_on_engine_project_error():
    from rocket_engine.project.errors import ProjectError

    module = _load()

    class _RaisingEngine:
        def submit(self, command):
            raise ProjectError(
                "revision_conflict", "Expected revision p12, got None."
            )

    _, call = module.make_handlers(lambda project_id: _RaisingEngine())
    result = asyncio.run(_call(call, "run_drc", {"project_id": PROJECT}))
    assert result.is_error is True
    payload = json.loads(_text(result))
    assert payload["ok"] is False
    assert payload["code"] == "revision_conflict"


def test_server_reports_unwired_operation_as_error():
    from rocket_engine.composition import Engine

    module = _load()
    _, call = module.make_handlers(
        lambda project_id: Engine(project_id, actor="test")
    )
    result = asyncio.run(
        _call(
            call,
            "run_syntax",
            {"project_id": PROJECT, "expected_revision": "p12"},
        )
    )
    assert result.is_error is True
    assert "unsupported_operation" in _text(result)


def test_stdio_smoke_initialize_list_call():
    proc = subprocess.Popen(
        [sys.executable, "-m", "rocket_engine.adapters.mcp.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, cwd=ROOT,
    )
    try:
        def _rpc(payload):
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            return json.loads(proc.stdout.readline())

        init = _rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2024-11-05",
                                "capabilities": {}, "clientInfo": {
                                    "name": "smoke", "version": "0"}}})
        assert "result" in init, init
        proc.stdin.write(json.dumps({"jsonrpc": "2.0",
                                      "method": "notifications/initialized"}) + "\n")
        proc.stdin.flush()
        listed = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert "run_drc" in names
        assert "get_capabilities" in names
    finally:
        proc.kill()
        proc.wait(timeout=10)
