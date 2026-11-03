"""RUNTIME RED — deferred EngineRuntime: prompt ack, coalescing, capacity.

TDD RED: valid RED = `rocket_engine.execution.runtime` does not
exist, so every test fails on ImportError. GREEN implements
`src/execution/runtime.py` (plus `src/execution/queue.py`)
standalone against injected ports — never against Engine.
"""

import pytest


def _load():
    import importlib

    runtime = importlib.import_module("rocket_engine.execution.runtime")
    return runtime.EngineRuntime


def _runtime(**overrides):
    engine_runtime = _load()
    calls = []

    def runner(operation, arguments, snapshot_id, request_id, run_id):
        calls.append((operation, dict(arguments), run_id))
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": {"status": "PASS"},
            "operation": operation,
        }

    params = {"project_id": "demo", "runner": runner,
              "auto_dispatch": False}
    params.update(overrides)
    return engine_runtime(**params), calls


def test_prompt_ack_carries_no_verdict():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert handle.run_id
    ack = handle.receipt
    assert ack["admitted"] is True
    assert ack["state"] == "queued"
    assert "verdict" not in ack
    assert ack["request_id"] == "req-1"


def test_deferred_handle_resolves_after_pump():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert handle.poll()["state"] == "queued"
    runtime.pump()
    done = handle.wait(timeout=5)
    assert done["state"] == "completed"
    assert done["verdict"] == {"status": "PASS"}


def test_same_request_id_retries_admit_exactly_once():
    runtime, calls = _runtime()
    first = runtime.submit("run_drc", {"cell": "top"},
                           request_id="req-1")
    second = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert second.run_id == first.run_id
    runtime.pump()
    assert len(calls) == 1


def test_same_request_id_new_content_conflicts():
    runtime, _ = _runtime()
    runtime.submit("run_drc", {"cell": "top"}, request_id="req-1")
    with pytest.raises(Exception) as excinfo:
        runtime.submit("run_drc", {"cell": "other"}, request_id="req-1")
    assert getattr(excinfo.value, "code", "") == "request_conflict"


def test_saturated_capacity_refuses_retryable_not_admitted():
    runtime, _ = _runtime(max_inflight=1)
    runtime.submit("run_drc", {"cell": "a"}, request_id="req-1")
    refused = runtime.submit("run_drc", {"cell": "b"}, request_id="req-2")
    assert refused.receipt["admitted"] is False
    assert refused.receipt["code"] == "pool_full"
    assert refused.receipt["retryable"] is True
    assert runtime.pause_visible() is True
    runtime.pump()
    assert runtime.pause_visible() is False
    retry = runtime.submit("run_drc", {"cell": "b"}, request_id="req-2")
    assert retry.receipt["admitted"] is True


def test_five_identical_inflight_share_one_execution():
    runtime, calls = _runtime()
    handles = [runtime.submit("run_drc", {"cell": "top"},
                              request_id=f"req-{i}")
                for i in range(5)]
    assert len({h.run_id for h in handles}) == 1
    runtime.pump()
    assert len(calls) == 1
    assert sorted(runtime.request_ids_for(handles[0].run_id)) == \
        sorted(f"req-{i}" for i in range(5))


def test_scripts_and_edits_never_coalesce():
    runtime, calls = _runtime()
    handles = [runtime.submit("python_execute", {"mode": "exec",
                                                 "lines": "x = 1"},
                              request_id=f"req-{i}")
                for i in range(2)]
    assert handles[0].run_id != handles[1].run_id
    edit_a = runtime.submit("write_doc", {"path": "a.txt",
                                          "content": "a"},
                            request_id="edit-1")
    edit_b = runtime.submit("write_doc", {"path": "a.txt",
                                          "content": "a"},
                            request_id="edit-2")
    assert edit_a.run_id != edit_b.run_id
    runtime.pump()
    assert len(calls) == 4


def test_intervening_edit_forces_separate_execution():
    runtime, calls = _runtime()
    runtime.submit("run_drc", {"cell": "top"}, request_id="req-1")
    runtime.apply_edit()
    runtime.submit("run_drc", {"cell": "top"}, request_id="req-2")
    runtime.pump()
    assert len(calls) == 2


def test_cancel_queued_is_truthful_and_attributed():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    outcome = runtime.cancel(handle.run_id, actor="human")
    assert outcome["state"] == "cancelled"
    assert outcome["actor"] == "human"
    kinds = [event["kind"] for event in runtime.watch(0)["events"]]
    assert "job_queued" in kinds
    assert "job_cancelled" in kinds


def test_watch_reconnect_repeats_and_expiry_fails_loud():
    runtime, _ = _runtime()
    runtime.submit("run_drc", {"cell": "top"}, request_id="req-1")
    runtime.pump()
    first = runtime.watch(0)
    again = runtime.watch(0)
    assert [e["seq"] for e in again["events"]] == \
        [e["seq"] for e in first["events"]]
    with pytest.raises(Exception) as excinfo:
        runtime.watch(10 ** 9)
    assert getattr(excinfo.value, "code", "") == "cursor_expired"


def test_survivors_report_without_autoexecution():
    runtime, calls = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    report = runtime.boot_report()
    assert handle.run_id in report["survivors"]
    assert calls == []
    resumed = runtime.resume(handle.run_id)
    assert resumed["state"] == "completed"


def test_discard_and_quarantine_need_explicit_override():
    runtime, _ = _runtime()
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-1")
    assert runtime.discard(handle.run_id)["state"] == "discarded"
    handle2 = runtime.submit("run_drc", {"cell": "top"},
                             request_id="req-2")
    runtime.note_interruption(handle2.run_id)
    runtime.note_interruption(handle2.run_id)
    with pytest.raises(Exception) as excinfo:
        runtime.resume(handle2.run_id)
    assert getattr(excinfo.value, "code", "") == "poison_quarantined"
    assert runtime.resume(handle2.run_id,
                          override_quarantine=True)["state"] == \
        "completed"


def test_host_tool_probe_is_loud_never_faked_green():
    runtime_mod = __import__("importlib").import_module(
        "rocket_engine.execution.runtime")
    probe = runtime_mod.probe_host_tool(
        "opensta", "BLOCKED-needs-host: sta lane needs OpenSTA")
    if probe["available"]:
        assert probe["path"]
    else:
        assert "BLOCKED-needs-host" in probe["reason"]
        assert probe["verdict"] == "BLOCKED-needs-host"


def test_timing_lane_loud_skips_without_sta():
    runtime_mod = __import__("importlib").import_module(
        "rocket_engine.execution.runtime")
    probe = runtime_mod.probe_host_tool(
        "opensta", "BLOCKED-needs-host: run_timing needs OpenSTA")
    if not probe["available"]:
        pytest.skip(f"Loud skip: {probe['reason']}")
    runtime, _ = _runtime()
    handle = runtime.submit("run_timing", {"cell": "top"},
                            request_id="timing-1")
    runtime.pump()
    assert handle.wait(timeout=5)["state"] == "completed"


def test_docker_lane_loud_skips_without_daemon():
    runtime_mod = __import__("importlib").import_module(
        "rocket_engine.execution.runtime")
    probe = runtime_mod.probe_host_tool(
        "docker", "BLOCKED-needs-host: container lane needs "
                   "a docker daemon")
    if not probe["available"]:
        pytest.skip(f"Loud skip: {probe['reason']}")
    runtime, _ = _runtime()
    handle = runtime.submit("run_digital_flow", {"cell": "top"},
                            request_id="flow-1")
    runtime.pump()
    assert handle.wait(timeout=5)["state"] == "completed"
