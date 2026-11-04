"""Step 7A port bus RED — shared engine ports, QoS-1, quarantine ladder.

TDD RED: valid RED = `rocket_engine.execution.ports` (PortBus,
PositionGuard) plus the Engine/EngineRuntime port seams do not
exist yet, so every test fails on ImportError/AttributeError.
GREEN wires one shared Engine per process with port attach/detach
(boot profile stdio, local-only toggle), async per-port queues
with acks over the appended ledger event, the shared
position-check apply guard, and the staged 10/15/20s quarantine
ladder (flag-not-kill, engine-side bookkeeping) plus the
resync-flag directive.
"""

import threading
import time

import pytest


def _ports():
    import importlib

    return importlib.import_module("rocket_engine.execution.ports")


def _routing_ports():
    import importlib

    return importlib.import_module(
        "rocket_engine.execution.routing.ports")


def _engine_class():
    import importlib

    return importlib.import_module("rocket_engine.composition").Engine


def _runtime_class():
    import importlib

    return importlib.import_module(
        "rocket_engine.execution.runtime").EngineRuntime


class _Clock:
    """Manual clock so the quarantine ladder stays deterministic."""

    def __init__(self, now=1000.0):
        self.now = float(now)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += float(seconds)


def _bus(**overrides):
    ports = _ports()
    params = {"clock": _Clock()}
    params.update(overrides)
    return ports.PortBus(**params), params["clock"]


def _submit_entity(engine, tag):
    head = engine.snapshot()["current_revision"]
    return engine.submit({
        "project_id": "port-bus-demo",
        "operation": "create_entity",
        "arguments": {"kind": "wire",
                       "expected_revision": head},
        "request_id": f"req-{tag}",
    })


def test_ladder_defaults_match_adr017():
    ports = _ports()
    assert ports.WARN_AFTER_S == 10.0
    assert ports.QUARANTINE_AFTER_S == 15.0
    assert ports.RESYNC_AFTER_S == 20.0
    assert "stdio" in ports.BOOT_PROFILE


def test_cross_port_delivery_over_runtime_ledger():
    runtime_cls = _runtime_class()

    def runner(operation, arguments, snapshot_id, request_id,
               run_id):
        return {"run_id": run_id, "state": "completed",
                "operation": operation,
                "verdict": {"status": "PASS"}}

    runtime = runtime_cls("demo", runner, auto_dispatch=False)
    runtime.attach_port("stdio")
    runtime.attach_port("ide", push=True)
    handle = runtime.submit("run_drc", {"cell": "top"},
                            request_id="req-bus-1")
    runtime.pump()
    assert handle.wait(timeout=5)["state"] == "completed"
    stdio = runtime.port_pending("stdio")
    ide = runtime.port_pending("ide")
    assert stdio and ide
    assert stdio[-1]["seq"] == ide[-1]["seq"]
    assert ide[-1]["kind"] == "job_finished"


def test_engine_change_visible_on_other_port_queue():
    engine_cls = _engine_class()
    engine = engine_cls("port-bus-demo", "test")
    engine.attach_port("ide")
    _submit_entity(engine, "xport-1")
    other = engine.port_pending("ide")
    kinds = {event.get("event", event.get("kind"))
             for event in other}
    assert "entity_created" in kinds or "component_changed" in kinds


def test_same_position_redelivery_applies_once():
    routing = _routing_ports()
    bus, _ = _bus()
    bus.attach("ide")
    bus.ingest([{"seq": 7, "event": "component_changed",
                 "data": {"revision": "p13"}}])
    applied = []
    handler = routing.PortHandler(bus, "ide")
    first = handler.handle(bus.pending("ide")[0],
                           applied.append)
    bus.ingest([{"seq": 7, "event": "component_changed",
                 "data": {"revision": "p13"}}])
    assert bus.pending("ide") == []
    redelivered = {"seq": 7, "event": "component_changed",
                   "data": {"revision": "p13"}}
    second = handler.handle(redelivered, applied.append)
    assert first[0] is True
    assert second[0] is False
    assert len(applied) == 1


def test_quarantine_ladder_fires_then_resync_converges():
    bus, clock = _bus()
    bus.attach("slow")
    bus.ingest([{"seq": 1, "event": "component_changed",
                 "data": {}}])
    clock.advance(11)
    assert bus.port_evaluate()[0]["directive"] == "warn"
    clock.advance(5)
    directives = bus.port_evaluate()
    assert directives[0]["directive"] == "quarantine"
    assert bus.pending("slow") == []
    clock.advance(5)
    directives = bus.port_evaluate()
    assert directives[0]["directive"] == "resync_required"
    state = bus.port_state("slow")
    assert state["resync_required"] is True
    assert state["state"] == "quarantined"
    receipt = bus.port_resync("slow", head=42)
    assert receipt["cursor"] == 42
    state = bus.port_state("slow")
    assert state["state"] == "active"
    assert state["resync_required"] is False


def test_toggle_mid_run_disables_like_dead_ship():
    engine_cls = _engine_class()
    engine = engine_cls("port-bus-demo", "test")
    engine.attach_port("ide")
    _submit_entity(engine, "toggle-1")
    assert engine.port_pending("ide")
    engine.set_port_enabled("ide", False, local=True)
    state = engine.port_state("ide")
    assert state["enabled"] is False
    assert state["resync_required"] is True
    assert engine.port_pending("ide") == []
    _submit_entity(engine, "toggle-2")
    assert engine.port_pending("stdio")
    with pytest.raises(Exception):
        engine.set_port_enabled("ide", True, local=False)
    engine.set_port_enabled("ide", True, local=True)
    engine.port_resync("ide")
    assert engine.port_state("ide")["resync_required"] is False


def test_slow_port_never_stalls_writers():
    runtime_cls = _runtime_class()

    def runner(operation, arguments, snapshot_id, request_id,
               run_id):
        return {"run_id": run_id, "state": "completed",
                "operation": operation,
                "verdict": {"status": "PASS"}}

    runtime = runtime_cls("demo", runner, auto_dispatch=False)
    runtime.attach_port("slow", max_depth=2)
    runtime.attach_port("fast")
    for idx in range(6):
        handle = runtime.submit("run_drc", {"cell": f"top-{idx}"},
                                request_id=f"req-slow-{idx}")
        assert handle.receipt["admitted"] is True
    runtime.pump()
    state = runtime.port_state("slow")
    assert state["state"] == "quarantined"
    assert state["resync_required"] is True
    assert len(runtime.port_pending("fast")) == 24


def test_boot_profile_is_stdio_only():
    engine_cls = _engine_class()
    engine = engine_cls("port-bus-demo", "test")
    assert engine.port_pending("stdio") == []
    with pytest.raises(Exception):
        engine.port_pending("mcp")


def test_queue_depth_ceiling_quarantines_engine_side():
    bus, _ = _bus(max_depth=2)
    bus.attach("deep")
    bus.ingest([{"seq": 1, "event": "component_changed",
                 "data": {}}])
    bus.ingest([{"seq": 2, "event": "component_changed",
                 "data": {}}])
    bus.ingest([{"seq": 3, "event": "component_changed",
                 "data": {}}])
    state = bus.port_state("deep")
    assert state["state"] == "quarantined"
    assert state["resync_required"] is True
    assert bus.pending("deep") == []


def test_background_push_delivers_without_writer_wait():
    bus, _ = _bus()
    bus.attach("live")
    seen = []
    done = threading.Event()

    def handler(event):
        seen.append(event["seq"])
        if len(seen) >= 2:
            done.set()

    bus.start("live", handler)
    try:
        bus.ingest([{"seq": 1, "event": "component_changed",
                     "data": {}},
                    {"seq": 2, "event": "component_changed",
                     "data": {}}])
        assert done.wait(timeout=5)
    finally:
        bus.stop("live")
    assert seen == [1, 2]
    assert bus.port_state("live")["acked"] == 2
    deadline = time.time() + 5
    while bus.pending("live") and time.time() < deadline:
        time.sleep(0.01)
    assert bus.pending("live") == []
