"""MCP-NOTIFY RED — lifecycle notifications appended to the MCP server.

TDD RED: valid RED = `build_lifecycle_notification` and
`subscribe_runtime` do not exist on
`rocket_engine.adapters.mcp.server`, so every test fails on
AttributeError. GREEN appends notification-only helpers without
changing any existing handler behavior.
"""

import json


def _load():
    import importlib

    return importlib.import_module("rocket_engine.adapters.mcp.server")


def _event(kind="job_queued", run_id="run-1", seq=1):
    return {"seq": seq, "kind": kind, "run_id": run_id,
            "request_id": "req-1", "operation": "run_drc"}


def test_lifecycle_event_maps_to_mcp_notification():
    server = _load()
    note = server.build_lifecycle_notification(_event())
    assert note["jsonrpc"] == "2.0"
    assert note["method"].startswith("notifications/")
    payload = json.dumps(note["params"])
    assert "run-1" in payload
    assert "job_queued" in payload


def test_progress_event_carries_progress_shape():
    server = _load()
    note = server.build_lifecycle_notification(
        _event(kind="job_progress", seq=3))
    params = note["params"]
    text = json.dumps(params)
    assert "run-1" in text
    assert "progress" in note["method"] or "progress" in text


def test_subscribe_runtime_delivers_ordered_notifications():
    server = _load()
    import importlib

    runtime_mod = importlib.import_module(
        "rocket_engine.execution.runtime")
    seen = []

    runtime = runtime_mod.EngineRuntime(
        project_id="demo",
        runner=lambda op, args, snap, req, run: {
            "run_id": run, "state": "completed",
            "verdict": {"status": "PASS"}, "operation": op},
        auto_dispatch=False,
    )
    server.subscribe_runtime(runtime, seen.append)
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    runtime.pump()
    kinds = [n["params"].get("kind", n["method"]) for n in seen]
    assert any("job_queued" in k for k in kinds)
    assert any("finished" in k or "job_finished" in k for k in kinds)
    assert handle.run_id in json.dumps(seen)


def test_existing_handlers_still_wired():
    server = _load()
    assert callable(server.make_handlers)
    assert callable(server.build_server)
    assert "run_drc" in [t.name for t in server.tool_definitions()]
