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


def _build_server(engine):
    # RED: module missing.
    from rocket_engine.adapters.mcp.server import build_server

    return build_server(lambda project_id: engine)


def _fake_engine():
    class FakeEngine:
        def __init__(self):
            self.submitted = []

        def submit(self, command):
            self.submitted.append(command)
            return {"state": "queued", "run_id": "r1",
                    "snapshot_id": "s1", "event_cursor": 1}

    return FakeEngine()


def test_server_lists_every_cataloged_operation_and_query():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    server = _build_server(_fake_engine())
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert set(OPERATIONS) <= names
    assert set(QUERIES) <= names


def test_server_call_routes_envelope_to_engine():
    engine = _fake_engine()
    server = _build_server(engine)
    asyncio.run(server.call_tool(
        "run_drc",
        {"project_id": PROJECT, "expected_revision": "p12"},
    ))
    assert len(engine.submitted) == 1
    command = engine.submitted[0]
    assert command["project_id"] == PROJECT
    assert command["operation"] == "run_drc"
    assert command["arguments"]["expected_revision"] == "p12"
    assert command["request_id"]


def test_server_rejects_unknown_tool_without_routing():
    engine = _fake_engine()
    server = _build_server(engine)
    result = asyncio.run(server.call_tool("rm_rf", {"project_id": PROJECT}))
    assert engine.submitted == []
    assert "unsupported" in json.dumps(result).lower()


def test_server_rejects_missing_project_id():
    engine = _fake_engine()
    server = _build_server(engine)
    result = asyncio.run(server.call_tool("run_drc", {}))
    assert engine.submitted == []
    assert "project_id" in json.dumps(result).lower()


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
