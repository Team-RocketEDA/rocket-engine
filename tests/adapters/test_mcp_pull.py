"""MCP-PULL RED — pull-by-default cursor path over the existing event log.

TDD RED: valid RED = `rocket_engine.adapters.mcp.pull` does not
exist, so every test fails on ImportError. GREEN contracts the
MCP pull path (poll-from-cursor over the wired get_events_since
query, same-position redelivery applies once, push opt-in only)
per ADR-017 D7 and the MCP-CONTRACT/MCP-SCHEMA D7 amendments.
"""

import uuid

PROJECT = "mcp-pull-demo"


def _load():
    # RED: module missing.
    import importlib

    return importlib.import_module("rocket_engine.adapters.mcp.pull")


class _FakeEngine:
    """Stand-in recording submit envelopes, serving pages by cursor."""

    def __init__(self, pages=None, failures=None):
        self.commands = []
        self._pages = dict(pages or {})
        self._failures = list(failures or [])

    def submit(self, command):
        self.commands.append(command)
        if self._failures:
            raise self._failures.pop(0)
        cursor = command["arguments"].get("cursor", 0)
        return self._pages.get(cursor, {"events": [], "cursor": cursor})


def _event(seq, kind="component_changed"):
    return {
        "seq": seq,
        "event": kind,
        "request_id": f"req-{seq}",
        "project_id": PROJECT,
        "actor": "test",
        "data": {"revision": f"p{12 + seq}"},
    }


def _real_engine(pid):
    from rocket_engine.composition import Engine

    return Engine(pid, actor="mcp-pull-test")


def _create(engine, pid):
    head = engine.snapshot()["current_revision"]
    return engine.submit(
        {
            "project_id": pid,
            "operation": "create_entity",
            "arguments": {"kind": "block", "expected_revision": head},
            "request_id": uuid.uuid4().hex,
        }
    )


def test_poll_routes_get_events_since_with_cursor():
    pull = _load()
    engine = _FakeEngine(pages={2: {"events": [_event(3)], "cursor": 3}})
    page = pull.poll_events(engine, PROJECT, 2)
    assert engine.commands[-1]["operation"] == "get_events_since"
    assert engine.commands[-1]["project_id"] == PROJECT
    assert engine.commands[-1]["arguments"]["cursor"] == 2
    assert [e["seq"] for e in page["events"]] == [3]
    assert page["cursor"] == 3


def test_pull_from_stale_cursor_converges():
    pull = _load()
    pid = f"{PROJECT}-stale"
    engine = _real_engine(pid)
    _create(engine, pid)
    _create(engine, pid)
    client = pull.McpPullClient(engine, pid, cursor=0)
    page = client.poll()
    assert len(page["events"]) == 2
    assert page["resynced"] is False
    assert client.cursor == engine.snapshot()["event_cursor"]
    assert page["cursor"] == client.cursor


def test_second_poll_returns_only_new_events():
    pull = _load()
    pid = f"{PROJECT}-incr"
    engine = _real_engine(pid)
    _create(engine, pid)
    client = pull.McpPullClient(engine, pid, cursor=0)
    first = client.poll()
    assert len(first["events"]) == 1
    _create(engine, pid)
    second = client.poll()
    assert [e["seq"] for e in second["events"]] == [
        first["events"][0]["seq"] + 1
    ]
    assert client.cursor == engine.snapshot()["event_cursor"]


def test_same_position_redelivery_applies_once():
    pull = _load()
    pid = f"{PROJECT}-dedupe"
    engine = _real_engine(pid)
    _create(engine, pid)
    _create(engine, pid)
    client = pull.McpPullClient(engine, pid, cursor=0)
    page = client.poll()
    seen = []
    applied = client.apply(page["events"], seen.append)
    assert applied == 2
    assert [e["seq"] for e in seen] == [
        e["seq"] for e in page["events"]
    ]
    redelivered = client.apply(page["events"], seen.append)
    assert redelivered == 0
    assert len(seen) == 2
    assert client.applied_position == page["events"][-1]["seq"]


def test_push_requires_explicit_opt_in():
    pull = _load()
    from rocket_engine.adapters.errors import AdapterError

    added = []

    class _Runtime:
        def add_listener(self, callback):
            added.append(callback)
            return lambda: added.remove(callback)

    runtime = _Runtime()
    seen = []
    try:
        pull.subscribe_push(runtime, seen.append)
    except AdapterError as exc:
        assert exc.code == "unsupported_operation"
    else:  # pragma: no cover - GREEN must refuse
        raise AssertionError("push without opt-in was not refused")
    assert added == []
    unsubscribe = pull.subscribe_push(
        runtime, seen.append, enable_push=True
    )
    assert len(added) == 1
    added[0]({"seq": 1, "kind": "job_queued", "run_id": "run-1"})
    assert "run-1" in str(seen)
    assert callable(unsubscribe)


def test_pull_reuses_shared_position_guard():
    pull = _load()
    from rocket_engine.execution.ports import PositionGuard

    guard = PositionGuard()
    port = "mcp"
    # A position the push path already applied must not re-apply
    # through pull: one shared dedupe record across both paths.
    guard.record(port, 8)
    retained = {"events": [_event(8), _event(9)], "cursor": 9}
    engine = _FakeEngine(pages={0: retained})
    client = pull.McpPullClient(
        engine, PROJECT, cursor=0, guard=guard, port=port
    )
    page = client.poll()
    seen = []
    assert client.apply(page["events"], seen.append) == 1
    assert [e["seq"] for e in seen] == [9]
    assert guard.applies(port, 9) is False
    assert guard.applies(port, 10) is True


def test_contiguity_demand_resyncs_and_converges():
    pull = _load()
    from rocket_engine.project.errors import ProjectError

    retained = {"events": [_event(8), _event(9)], "cursor": 9}
    engine = _FakeEngine(
        pages={0: retained},
        failures=[ProjectError("resync_required", "trimmed")],
    )
    client = pull.McpPullClient(engine, PROJECT, cursor=5)
    page = client.poll(require_contiguous=True)
    assert page["resynced"] is True
    assert [e["seq"] for e in page["events"]] == [8, 9]
    assert client.cursor == 9
    seen = []
    assert client.apply(page["events"], seen.append) == 2
    assert [e["seq"] for e in seen] == [8, 9]
