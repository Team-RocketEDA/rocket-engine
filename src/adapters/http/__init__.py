"""HTTP transport (duplex): JSON requests in, results and events out.

Loopback-only trust boundary (ADR-006): the listener binds the
loopback interface only and refuses any non-loopback bind loudly.
There is no auth — the loopback interface is the trust boundary —
and the API is the same caller-blind surface every transport serves.
"""

import ipaddress
import json
import socket
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ..base import enforce_scope, parse_json
from ..errors import AdapterError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class HttpTransport:
    """HTTP transport over an engine: requests in, results out.

    Args:
        engine: Engine the requests submit against.
        project_id: Optional scope; requests for another project
            are denied, never routed.
    """

    def __init__(self, engine, project_id=None):
        self._engine = engine
        self._project_id = project_id

    def handle(self, text):
        """Route one JSON request through the engine.

        Args:
            text: Raw JSON request with project_id, operation,
                arguments, and an optional request_id.

        Returns:
            Engine admission ack or query result for the request.

        Raises:
            AdapterError: invalid_command for a missing
                project_id, cross_project_denied for a request
                outside the bound scope.
        """
        request = parse_json(text)
        if request.get("project_id") is None:
            raise AdapterError("invalid_command", "Missing project_id in request.")
        enforce_scope(request.get("project_id"), self._project_id)
        return self._engine.submit(
            {
                "project_id": request["project_id"],
                "operation": request["operation"],
                "arguments": request.get("arguments", {}),
                "request_id": str(request.get("request_id") or uuid.uuid4().hex),
            }
        )


def check_loopback_host(host):
    """Accept loopback bind hosts; refuse everything else loudly.

    Args:
        host: Requested bind host.

    Returns:
        The host unchanged when it is loopback.

    Raises:
        AdapterError: non_loopback_bind_denied when the host is not
            loopback — the adapter is localhost-only with no auth.
    """
    if host in LOOPBACK_HOSTS:
        return host
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if loopback:
        return host
    raise AdapterError(
        "non_loopback_bind_denied",
        f"Refused non-loopback HTTP bind {host!r}: the engine HTTP "
        "adapter is localhost-only with no auth (ADR-006) — the trust "
        "boundary is the loopback interface. Bind 127.0.0.1 instead; "
        "remote access needs a separate authenticated adapter.",
    )


def trust_banner(host, port):
    """Startup banner stating the localhost-only trust model.

    Args:
        host: Bound loopback host.
        port: Bound port.

    Returns:
        Banner text: localhost-only, no auth, caller-blind API.
    """
    return (
        "rocket-engine HTTP adapter — localhost-only, no auth (ADR-006).\n"
        f"Listening on http://{host}:{port} — the trust boundary is the "
        "loopback interface.\n"
        "Serves the same caller-blind API as every other transport; "
        "remote/multi-user access needs a separate authenticated adapter, "
        "never this one with a flag."
    )


class _LoopbackRequestHandler(BaseHTTPRequestHandler):
    """POST envelopes to the bound engine; quiet, JSON in and out."""

    def __init__(self, transport, *args, **kwargs):
        self._transport = transport
        super().__init__(*args, **kwargs)

    def do_POST(self):
        """Route one POST body through the bound HttpTransport."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8", "replace")
        try:
            result = self._transport.handle(body)
        except AdapterError as exc:
            self._send(400, {"code": exc.code, "message": str(exc)})
        except Exception as exc:  # engine errors stay data, never tracebacks
            self._send(500, {"code": "engine_error", "message": str(exc)})
        else:
            self._send(200, result)

    def do_GET(self):
        """Answer the /health liveness probe; 404 otherwise."""
        if self.path.split("?", 1)[0] == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(
                404, {"code": "not_found", "message": f"No route {self.path}."}
            )

    def log_message(self, format, *args):
        """Drop per-request access logs; stdout carries the banner only.

        Args:
            format: Ignored log format string.
            args: Ignored log arguments.
        """

    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def create_server(engine, host="127.0.0.1", port=0, project_id=None):
    """Bind a loopback-only HTTP server around an engine.

    Args:
        engine: Engine the requests submit against.
        host: Bind host; must be loopback (default 127.0.0.1).
        port: Bind port; 0 picks an ephemeral port.
        project_id: Optional scope; requests for another project
            are denied, never routed.

    Returns:
        Bound ThreadingHTTPServer, not yet serving.

    Raises:
        AdapterError: non_loopback_bind_denied for a non-loopback host.
    """
    check_loopback_host(host)
    transport = HttpTransport(engine, project_id=project_id)

    def handler(*args, **kwargs):
        return _LoopbackRequestHandler(transport, *args, **kwargs)

    if host == "::1":
        address_family = socket.AF_INET6
    else:
        address_family = socket.AF_INET

    class _BoundServer(ThreadingHTTPServer):
        pass

    _BoundServer.address_family = address_family
    return _BoundServer((host, port), handler)


def serve_http(engine, host="127.0.0.1", port=8000, project_id=None):
    """Serve the caller-blind API over loopback HTTP until interrupted.

    Args:
        engine: Engine the requests submit against.
        host: Bind host; must be loopback (default 127.0.0.1).
        port: Bind port.
        project_id: Optional scope; requests for another project
            are denied, never routed.

    Raises:
        AdapterError: non_loopback_bind_denied for a non-loopback host.

    Caution: No auth by design (ADR-006) — the loopback interface is
        the only trust boundary. Never expose this listener remotely.
    """
    server = create_server(engine, host=host, port=port, project_id=project_id)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    print(trust_banner(bound_host, bound_port), flush=True)
    server.serve_forever()
