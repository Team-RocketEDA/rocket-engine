"""HTTP-LOCALHOST RED — loopback trust boundary, loud and enforced.

ADR-006: the HTTP adapter binds 127.0.0.1 only, refuses any
non-loopback bind loudly, and serves the same caller-blind API
with no auth. The trust boundary is the loopback interface.
Valid RED = the serve surface does not exist yet.
"""

import contextlib
import json
import threading
import urllib.error
import urllib.request

import pytest

NON_LOOPBACK_HOSTS = ["0.0.0.0", "", "192.168.1.10", "10.0.0.5", "example.com"]


class FakeEngine:
    """In-test fake: admits everything with a canned ack."""

    def __init__(self):
        self.received = []

    def submit(self, command):
        self.received.append(command)
        return {"state": "queued", "run_id": "run_fake_001"}


def _request_body():
    return json.dumps(
        {
            "project_id": "demo",
            "operation": "get_capabilities",
            "arguments": {},
            "request_id": "request_http_localhost_001",
        }
    ).encode("utf-8")


def test_non_loopback_bind_refused_loudly():
    from rocket_engine.adapters.http import serve_http

    for host in NON_LOOPBACK_HOSTS:
        try:
            serve_http(FakeEngine(), host=host, port=0)
        except Exception as exc:
            assert getattr(exc, "code", None) == "non_loopback_bind_denied"
            assert "localhost-only" in str(exc)
        else:
            raise AssertionError(f"expected non_loopback_bind_denied for {host!r}")


def test_loopback_hosts_pass_the_guard():
    from rocket_engine.adapters.http import check_loopback_host

    for host in ("127.0.0.1", "localhost", "::1"):
        assert check_loopback_host(host) == host


def test_startup_banner_states_trust_model():
    from rocket_engine.adapters.http import trust_banner

    banner = trust_banner("127.0.0.1", 8000)
    for needle in ("localhost-only", "no auth", "caller-blind", "loopback"):
        assert needle in banner
    assert "127.0.0.1" in banner


def test_serve_http_binds_loopback_and_announces(monkeypatch, capsys):
    import uvicorn

    from rocket_engine.adapters.http import serve_http

    calls = []
    monkeypatch.setattr(
        uvicorn.Server, "run",
        lambda self: calls.append((self.config.host, self.config.port)),
    )
    serve_http(FakeEngine(), host="127.0.0.1", port=0)
    assert len(calls) == 1
    assert calls[0][0] == "127.0.0.1"
    out = capsys.readouterr().out
    for needle in ("localhost-only", "no auth", "caller-blind", "loopback"):
        assert needle in out


def test_loopback_listener_routes_post_through_transport():
    from rocket_engine.adapters.http import create_server

    engine = FakeEngine()
    server = create_server(engine, host="127.0.0.1", port=0)
    assert server.server_address[0] == "127.0.0.1"
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    server.wait_until_ready(timeout=10)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        request = urllib.request.Request(
            url, data=_request_body(), method="POST",
            headers={"Content-Type": "application/json"})
        # Loopback traffic bypasses proxies: a set http_proxy must not
        # route (or break) the localhost-only listener under test.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        worker.join(timeout=10)
        server.server_close()
    assert payload["run_id"] == "run_fake_001"
    assert engine.received[0]["request_id"] == "request_http_localhost_001"


def test_readme_states_trust_boundary():
    from pathlib import Path

    readme = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "adapters"
        / "http"
        / "README.md"
    ).read_text()
    for needle in ("localhost-only", "no auth", "caller-blind", "loopback"):
        assert needle in readme


class RaisingEngine(FakeEngine):
    """Fake whose submit always fails with one canned error."""

    def __init__(self, exc):
        super().__init__()
        self._exc = exc

    def submit(self, command):
        self.received.append(command)
        raise self._exc


@contextlib.contextmanager
def _serving(engine):
    from rocket_engine.adapters.http import create_server

    server = create_server(engine, host="127.0.0.1", port=0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    server.wait_until_ready(timeout=10)
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        worker.join(timeout=10)
        server.server_close()


def _post(port, body, path="/", headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    request = urllib.request.Request(
        url, data=body, method="POST", headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _json_post(port, body=None, path="/", headers=None):
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    return _post(port, body or _request_body(), path=path, headers=merged)


def _status_cases():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.execution.errors import ExecutionError, UsageError
    from rocket_engine.project.errors import ProjectError

    return [
        (AdapterError("cross_project_denied", "foreign"), 403, False),
        (ProjectError("revision_conflict", "stale"), 409, False),
        (ExecutionError("pool_full", "backlog"), 429, True),
        (ProjectError("unknown_run", "no such run"), 404, False),
        (AdapterError("invalid_command", "bad"), 400, False),
        (UsageError("unsupported_operation", "nope"), 422, False),
        (ExecutionError("missing_dependency", "no ngspice"), 422, False),
        (ExecutionError("runner_unavailable", "no bwrap"), 503, False),
    ]


@pytest.mark.parametrize(
    "exc,status,wants_retry", _status_cases(),
    ids=[case[0].code for case in _status_cases()],
)
def test_error_status_map(exc, status, wants_retry):
    with _serving(RaisingEngine(exc)) as port:
        got, headers, raw = _json_post(port)
    assert got == status
    body = json.loads(raw.decode("utf-8"))
    assert body["code"] == exc.code
    assert body["message"] == str(exc)
    lowered = {key.lower() for key in headers}
    if wants_retry:
        assert "retry-after" in lowered
    else:
        assert "retry-after" not in lowered


def test_error_body_carries_fields():
    from rocket_engine.project.errors import ProjectError

    exc = ProjectError("invalid_run_param", "bad deck", fields=["deck_opts"])
    with _serving(RaisingEngine(exc)) as port:
        got, _, raw = _json_post(port)
    assert got == 400
    body = json.loads(raw.decode("utf-8"))
    assert body == {"code": "invalid_run_param", "message": "bad deck",
                    "fields": ["deck_opts"]}


def test_uncoded_crash_is_generic_500():
    with _serving(RaisingEngine(ValueError("boom-raw-secret"))) as port:
        got, _, raw = _json_post(port)
    assert got == 500
    body = json.loads(raw.decode("utf-8"))
    assert body["code"] == "internal_error"
    assert "boom-raw-secret" not in json.dumps(body)


def test_post_rejects_unknown_path():
    with _serving(FakeEngine()) as port:
        got, _, raw = _json_post(port, path="/nope")
    assert got == 404
    assert json.loads(raw.decode("utf-8"))["code"] == "not_found"


def test_post_requires_json_content_type():
    with _serving(FakeEngine()) as port:
        got, _, _ = _post(port, _request_body())
        assert got == 415
        ok, _, _ = _post(
            port, _request_body(),
            headers={"Content-Type": "application/json; charset=utf-8"})
        assert ok == 200


def test_post_rejects_oversize_body():
    with _serving(FakeEngine()) as port:
        got, _, raw = _json_post(port, body=b"x" * (2 * 1024 * 1024))
    assert got == 413
    assert json.loads(raw.decode("utf-8"))["code"] == "body_too_large"


def test_post_rejects_foreign_origin():
    with _serving(FakeEngine()) as port:
        got, _, _ = _json_post(
            port, headers={"Origin": "http://evil.example:8080"})
        assert got == 403
        ok, _, _ = _json_post(
            port, headers={"Origin": "http://127.0.0.1:3000"})
        assert ok == 200
        bare, _, _ = _json_post(port)
        assert bare == 200


def test_audit_log_records_requests(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="rocket_engine.http"):
        with _serving(FakeEngine()) as port:
            _json_post(port)
    assert "POST / -> 200" in [r.getMessage() for r in caplog.records]


def test_server_saturation_returns_503(monkeypatch):
    import rocket_engine.adapters.http as http_module

    monkeypatch.setattr(http_module, "MAX_CONCURRENT", 0)
    with _serving(FakeEngine()) as port:
        got, headers, raw = _json_post(port)
    assert got == 503
    assert json.loads(raw.decode("utf-8"))["code"] == "server_busy"
    assert "retry-after" in {key.lower() for key in headers}
