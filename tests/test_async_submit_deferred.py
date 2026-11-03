"""ASYNC-SUBMIT RED — prompt ack plus deferred handle plus events.

TDD RED: valid RED = `rocket_engine.execution.runtime` does not
exist, so every test fails on ImportError. GREEN proves the
RULING-02 contract: submit acknowledges promptly without a
verdict, the run id arrives with job_queued/started/progress/
finished lifecycle events, and the deferred handle watches the
run to completion.
"""

EXPECTED_ORDER = ["job_queued", "job_started", "job_progress",
                  "job_finished"]


def _runtime(**overrides):
    import importlib

    runtime_mod = importlib.import_module(
        "rocket_engine.execution.runtime")
    progress_calls = []

    def runner(operation, arguments, snapshot_id, request_id, run_id):
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": {"status": "PASS"},
            "operation": operation,
        }

    params = {"project_id": "demo", "runner": runner,
              "auto_dispatch": False}
    params.update(overrides)
    runtime = runtime_mod.EngineRuntime(**params)
    return runtime, progress_calls


def test_submit_ack_has_no_verdict_but_watchable_run_id():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert handle.run_id
    assert handle.receipt["admitted"] is True
    assert "verdict" not in handle.receipt
    assert runtime.status(handle.run_id)["state"] == "queued"


def test_lifecycle_events_arrive_in_frontend_order():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    runtime.report_progress(handle.run_id, 0.5)
    runtime.pump()
    kinds = [event["kind"] for event in
             runtime.watch(0)["events"]]
    positions = [kinds.index(kind) for kind in EXPECTED_ORDER]
    assert positions == sorted(positions)


def test_deferred_handle_poll_then_wait():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert handle.poll()["state"] in ("queued", "running")
    runtime.pump()
    assert handle.wait(timeout=5)["state"] == "completed"


def test_ipc_stream_sees_same_lifecycle():
    import importlib

    runtime, _ = _runtime()
    ipc = importlib.import_module("rocket_engine.adapters.ipc")
    stream = ipc.EventStream(runtime)
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    runtime.pump()
    events = stream.since(0)["events"]
    kinds = [event["kind"] for event in events]
    assert "job_queued" in kinds
    assert handle.run_id in {event["run_id"] for event in events}
