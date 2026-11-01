"""HTTP-LOCALHOST RED — loopback trust boundary, loud and enforced.

ADR-006: the HTTP adapter binds 127.0.0.1 only, refuses any
non-loopback bind loudly, and serves the same caller-blind API
with no auth. The trust boundary is the loopback interface.
Valid RED = the serve surface does not exist yet.
"""

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

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
    from rocket_engine.adapters.http import serve_http

    calls = []
    monkeypatch.setattr(
        ThreadingHTTPServer, "serve_forever", lambda self: calls.append(self.server_address)
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
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        request = urllib.request.Request(url, data=_request_body(), method="POST")
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
