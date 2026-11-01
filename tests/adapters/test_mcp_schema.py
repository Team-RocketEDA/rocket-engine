"""MCP-SCHEMA: every MCP tool carries its real generated input schema.

Single source: docstrings -> scripts/api_spec.py -> MCP wire. No
hand-maintained second schema set lives in the server; the
generic-object fallback survives only for tools the generator cannot
describe, loudly marked. python_execute keeps its richer validation
schema (pinned by tests/execution/test_python_exec_wiring.py) until
API-V1-CLIENTS retires this wire.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

_RICH_OVERRIDE = {"python_execute"}


def _generated():
    return json.loads((ROOT / "docs" / "api-schema.json").read_text())


def _tools():
    from rocket_engine.adapters.mcp.server import tool_definitions

    return {tool.name: tool for tool in tool_definitions()}


def test_wire_schemas_match_generated_api_schema():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    generated = _generated()
    tools = _tools()
    checked = 0
    for name in sorted(OPERATIONS):
        if name in _RICH_OVERRIDE:
            continue
        entry = generated["operations"][name]
        if not entry["wired"]:
            continue
        wire = tools[name].input_schema
        assert wire["properties"] == entry["properties"], name
        assert wire["required"] == entry["required"], name
        checked += 1
    for name in sorted(QUERIES):
        entry = generated["queries"][name]
        if not entry["wired"]:
            continue
        wire = tools[name].input_schema
        assert wire["properties"] == entry["properties"], name
        assert wire["required"] == entry["required"], name
        checked += 1
    assert checked > 50


def test_described_tools_carry_non_generic_schemas():
    generated = _generated()
    tools = _tools()
    described = [
        name for section in ("operations", "queries")
        for name, entry in generated[section].items()
        if entry["wired"] and entry["properties"]
    ]
    assert described != []
    for name in described:
        if name in _RICH_OVERRIDE:
            continue
        wire = tools[name].input_schema
        assert wire.get("properties"), name
        assert wire != {"type": "object"}, name


def test_new_op_gains_wire_schema_without_server_edit(monkeypatch):
    import rocket_engine.adapters.mcp.server as server

    synthetic = {
        "operations": {
            "run_fake_new": {
                "wired": True,
                "properties": {"cell": {"description": "Cell name."}},
                "required": ["cell"],
            }
        },
        "queries": {},
    }
    monkeypatch.setattr(
        server, "OPERATIONS", server.OPERATIONS | {"run_fake_new"}
    )
    monkeypatch.setattr(server, "_API_SCHEMAS", synthetic)
    tools = {tool.name: tool for tool in server.tool_definitions()}
    assert tools["run_fake_new"].input_schema == {
        "type": "object",
        "properties": {"cell": {"description": "Cell name."}},
        "required": ["cell"],
    }


def test_unwired_tools_keep_loud_generic_fallback():
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    generated = _generated()
    tools = _tools()
    unwired = [
        name for name in sorted(OPERATIONS)
        if not generated["operations"][name]["wired"]
    ] + [
        name for name in sorted(QUERIES)
        if not generated["queries"][name]["wired"]
    ]
    assert unwired != []
    for name in unwired:
        wire = tools[name].input_schema
        assert wire["type"] == "object", name
        assert not wire.get("properties"), name
        assert name in wire.get("description", ""), name


def test_python_execute_keeps_rich_schema():
    from rocket_engine.execution.python_exec import MCP_INPUT_SCHEMA

    tools = _tools()
    assert tools["python_execute"].input_schema == MCP_INPUT_SCHEMA
