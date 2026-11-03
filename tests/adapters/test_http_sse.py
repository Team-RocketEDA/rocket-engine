"""HTTP SSE event stream (PUSH-EVENTS, HTTP slice).

Append-only: POST / and GET /health are untouched — GET /events
serves the runtime lifecycle log as Server-Sent Events (replay
since a cursor, then live push). Polling get_events_since stays
the watch path when no runtime is bound: the stream refuses
loudly instead of faking events.
"""

import json


class FakeRuntime:
    """In-memory EngineRuntime stand-in (watch + listeners)."""

    def __init__(self, events):
        self._events = list(events)
        self._listeners = []

    def watch(self, cursor):
        from rocket_engine.execution.errors import ExecutionError

        if not isinstance(cursor, int) or cursor < 0:
            raise ExecutionError("invalid_command", "Bad cursor.")
        if cursor > len(self._events):
            raise ExecutionError("cursor_expired", "Cursor past head.")
        return {
            "events": [dict(e) for e in self._events[cursor:]],
            "cursor": len(self._events),
        }

    def add_listener(self, callback):
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)
            return True

        return unsubscribe

    def emit(self, event):
        self._events.append(dict(event))
        for listener in list(self._listeners):
            listener(dict(event))


EVENTS = [
    {"seq": 1, "kind": "job_started", "run_id": "run_001"},
    {"seq": 2, "kind": "job_progress", "run_id": "run_001"},
]


def _app(runtime):
    from rocket_engine.adapters.http import create_app, HttpTransport

    return create_app(HttpTransport(FakeEngine()), runtime=runtime)


class FakeEngine:
    def __init__(self):
        self.received = []


def test_sse_frame_carries_id_and_json():
    from rocket_engine.adapters.http.events import format_frame

    frame = format_frame({"seq": 2, "kind": "job_progress"})
    assert frame.startswith("id: 2\n")
    assert "\ndata: " in frame
    assert frame.endswith("\n\n")
    payload = json.loads(frame.split("\ndata: ", 1)[1])
    assert payload["kind"] == "job_progress"


def test_events_replay_log_as_sse():
    from starlette.testclient import TestClient

    client = TestClient(_app(FakeRuntime(EVENTS)))
    with client.stream("GET", "/events?cursor=0") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = b""
        for chunk in response.iter_bytes():
            body += chunk
            if body.count(b"\n\n") >= 2:
                break
    frames = [f for f in body.decode().split("\n\n") if f.strip()]
    assert len(frames) == 2
    assert json.loads(frames[0].split("\ndata: ", 1)[1])["seq"] == 1


def test_events_without_runtime_refuses_loudly():
    from starlette.testclient import TestClient

    client = TestClient(_app(None))
    response = client.get("/events?cursor=0")
    assert response.status_code == 503
    assert response.json()["code"] == "runner_unavailable"


def test_events_reject_foreign_origin():
    from starlette.testclient import TestClient

    client = TestClient(_app(FakeRuntime(EVENTS)))
    response = client.get(
        "/events?cursor=0", headers={"Origin": "http://evil.example"}
    )
    assert response.status_code == 403


def test_event_source_pushes_live_frames():
    from rocket_engine.adapters.http.events import EventSource

    runtime = FakeRuntime(EVENTS)
    source = EventSource(runtime)
    seen = []
    unsubscribe = source.subscribe(seen.append)
    runtime.emit({"seq": 3, "kind": "job_done", "run_id": "run_001"})
    assert seen and seen[0].startswith("id: 3\n")
    assert unsubscribe() is True
