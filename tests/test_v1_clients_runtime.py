"""V1 client migration: every transport serves one integrated runtime.

TDD RED: `rocket_engine.clients.runtime.RuntimeClient` does not
exist yet, and the transports expose sync submit only, so every
test below fails until the migration seam lands. GREEN proves the
CLIENTS migration without touching the Engine: one RuntimeClient
bound to one engine, served by the MCP/HTTP/IPC transports and
the stdio console, with identical runs, watch recovery, and
capacity pause/resume across all of them.
"""

import json
from pathlib import Path

import pytest

PROJECT = "v1-client-probe"

GAIN = {"name": "dc_gain_db", "expr": "vdb(out)[0]", "unit": "dB"}


class StandInSpice:
    """Fake only the ngspice process; parsing stays the real adapter."""

    def __init__(self, values):
        self.values = values

    def preflight(self, job):
        return job

    def execute(self, job):
        lines = ["ngspice-44 (stand-in)", "Circuit: opamp"]
        lines += [f"meas_{name} = {value}" for name, value in self.values.items()]
        return {
            "exit_code": 0, "stdout": "", "stderr": "",
            "log": "\n".join(lines),
            "sources": job.get("sources", []),
            "measurements": job["measurements"],
        }

    def parse(self, native):
        from rocket_engine.adapters.ngspice import NgspiceAdapter

        return NgspiceAdapter().parse(native)

    def capabilities(self, target=None):
        from rocket_engine.adapters.ngspice import NgspiceAdapter

        return NgspiceAdapter().capabilities(target)


def _engine(values=None):
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="v1-client-test")
    engine.register_solver(
        "run_spice", StandInSpice(values or {"dc_gain_db": 62.5}), tool="ngspice")
    return engine


def _spice_args(floor="p12"):
    return {"expected_revision": floor, "measurements": [dict(GAIN, min=60)]}


def _client_for(engine):
    from rocket_engine.clients.runtime import RuntimeClient

    return RuntimeClient(engine)


def test_runtime_client_submit_matches_engine_submit():
    engine = _engine()
    client = _client_for(engine)
    out = client.submit(PROJECT, "run_spice", _spice_args(), request_id="v1-sync-1")
    assert out["state"] == "completed"
    assert out["verdict"]["status"] == "PASS"


def test_each_transport_serves_the_same_runtime_client():
    from rocket_engine.adapters.http import HttpTransport
    from rocket_engine.adapters.ipc import IpcTransport
    from rocket_engine.adapters.mcp import McpTransport

    engine = _engine()
    clients = [
        McpTransport(engine).runtime_client(),
        HttpTransport(engine).runtime_client(),
        IpcTransport(engine).runtime_client(),
    ]
    receipts = [
        item.deferred_submit("run_spice", _spice_args(), request_id=f"v1-shared-{index}")
        for index, item in enumerate(clients)
    ]
    run_ids = [item.run_id for item in receipts]
    assert len(set(run_ids)) == 1
    clients[0].pump()
    completions = [item.wait_for(run_ids[0], timeout=10) for item in clients]
    assert all(item["state"] == "completed" for item in completions)
    assert completions[0] == completions[1] == completions[2]
    fetched = clients[2].fetch(run_ids[0])
    assert fetched["run_id"] == run_ids[0]
    assert fetched["verdict"]["status"] == "PASS"


def test_console_serves_the_same_runtime_client(tmp_path):
    from rocket_engine.adapters.stdio_console import StdioConsole

    engine = _engine()
    console = StdioConsole(engine=engine, project_id=PROJECT, root=tmp_path / "console")
    try:
        handle = console.runtime_client().deferred_submit(
            "run_spice", _spice_args(), request_id="v1-console-1")
        assert "verdict" not in handle.receipt
        _client_for(engine).pump()
        done = _client_for(engine).wait_for(handle.run_id, timeout=10)
        assert done["state"] == "completed"
        assert done["verdict"]["status"] == "PASS"
    finally:
        console.close()


def test_watch_recovers_from_an_expired_cursor():
    engine = _engine()
    client = _client_for(engine)
    handle = client.deferred_submit(
        "run_spice", _spice_args(), request_id="v1-watch-1")
    client.pump()
    client.wait_for(handle.run_id, timeout=10)
    page = client.watch(0)
    assert page["events"] and isinstance(page["cursor"], int)
    assert page.get("resynced", False) is False
    kinds = [item["kind"] for item in page["events"]]
    assert "job_queued" in kinds and "job_finished" in kinds
    recovered = client.watch(10 ** 9)
    assert recovered["resynced"] is True
    assert isinstance(recovered["cursor"], int)
    assert recovered["events"]


def test_capacity_refusal_pauses_and_drain_resumes():
    engine = _engine()
    client = _client_for(engine)
    assert client.paused is False
    queued = [
        client.deferred_submit(
            "run_spice", {"cell": f"top-{index}"}, request_id=f"v1-cap-{index}")
        for index in range(64)
    ]
    refused = client.deferred_submit(
        "run_spice", {"cell": "top-over"}, request_id="v1-cap-over")
    assert refused.receipt["admitted"] is False
    assert client.paused is True
    for item in queued:
        client.cancel(item.run_id)
    assert client.paused is False
    handle = client.deferred_submit(
        "run_spice", _spice_args(), request_id="v1-cap-again")
    assert handle.receipt["admitted"] is True
    client.cancel(handle.run_id)


def test_python_client_connect_serves_the_same_runtime():
    import importlib.util

    from rocket_engine.clients.runtime import RuntimeClient

    path = Path(__file__).resolve().parent.parent / "clients" / "python" / "client.py"
    spec = importlib.util.spec_from_file_location("v1_python_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = module.connect("v1-python-probe")
    assert isinstance(client, RuntimeClient)
    out = client.submit(
        "v1-python-probe", "get_project_snapshot", {}, request_id="v1-py-1")
    assert out["project_id"] == "v1-python-probe" or "current_revision" in out


def test_unknown_operation_is_refused_loudly_on_every_transport():
    from rocket_engine.adapters.http import HttpTransport
    from rocket_engine.adapters.ipc import IpcTransport
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.project.errors import ProjectError

    engine = _engine()
    with pytest.raises(ProjectError) as err:
        engine.submit({"project_id": PROJECT, "operation": "nope_op",
                       "arguments": {}, "request_id": "v1-nope-0"})
    assert err.value.code == "unsupported_operation"
    frames = [
        json.dumps({"method": "tools/call",
                    "params": {"name": "nope_op", "arguments": {"project_id": PROJECT}},
                    "id": "v1-nope-1"}),
        json.dumps({"project_id": PROJECT, "operation": "nope_op",
                    "arguments": {}, "request_id": "v1-nope-2"}),
        json.dumps({"project_id": PROJECT, "operation": "nope_op",
                    "arguments": {}, "request_id": "v1-nope-3"}),
    ]
    transports = [McpTransport(engine), HttpTransport(engine), IpcTransport(engine)]
    for transport, frame in zip(transports, frames):
        with pytest.raises(Exception) as exc:
            transport.handle(frame)
        assert "nope_op" in str(exc.value)
