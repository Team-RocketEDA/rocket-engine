"""HTTP transport (duplex): JSON requests in, results and events out.

Loopback-only trust boundary (ADR-006): the listener binds the
loopback interface only and refuses any non-loopback bind loudly.
There is no auth — the loopback interface is the trust boundary —
and the API is the same caller-blind surface every transport serves.

The listener is a small FastAPI app on uvicorn: POST a JSON envelope
to `/`, GET `/health` for liveness. Hardening: JSON content-type
required, 1 MiB body cap, loopback-or-absent Origin only, bounded
concurrency, per-request audit log.
"""

import ipaddress
import json
import logging
import threading
import time
import urllib.parse
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import uvicorn

from .. import api
from ..base import enforce_scope, parse_json
from ..errors import (
    AdapterError,
    error_payload,
    retry_after_for,
    status_for_code,
)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Largest accepted POST body; larger reads refuse with 413.
MAX_BODY_BYTES = 1024 * 1024

#: Concurrent in-flight requests; overflow refuses with 503.
MAX_CONCURRENT = 32

#: Backoff advertised with 429/503 refusals.
RETRY_AFTER_SECONDS = 5

_LOG = logging.getLogger("rocket_engine.http")


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
        return api.submit(
            self._engine,
            request["project_id"],
            request["operation"],
            request.get("arguments", {}),
            request_id=str(request.get("request_id") or uuid.uuid4().hex),
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


def _is_loopback_origin(origin):
    """Accept a missing Origin or a loopback one; deny the rest.

    Browsers attach Origin on cross-origin POSTs, so a foreign
    Origin is a CSRF-shaped request and fails closed. Malformed
    origins fail closed too.

    Args:
        origin: Origin header value, or None when absent.

    Returns:
        True for absent/malformed-free loopback origins only.
    """
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname or ""
    except ValueError:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _refusal(code, message, headers=None):
    """JSON refusal with the tabled status for one v0 code.

    Args:
        code: Stable v0 error code.
        message: Human-readable detail.
        headers: Extra headers (Retry-After where owed).

    Returns:
        JSON response at the code's tabled status.
    """
    return JSONResponse(status_code=status_for_code(code),
                        content={"code": code, "message": message},
                        headers=headers)


def create_app(transport):
    """Build the loopback API app around one bound transport.

    Thin routes over the transport: POST `/` submits one JSON
    envelope, GET `/health` answers liveness. No docs routes —
    the engine-api reference is the contract, not OpenAPI pages.

    Args:
        transport: HttpTransport the routes submit against.

    Returns:
        Configured FastAPI app (unserved; see create_server).
    """
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    slots = threading.Semaphore(MAX_CONCURRENT)

    @app.middleware("http")
    async def _audit(request, call_next):
        response = await call_next(request)
        _LOG.info("%s %s -> %s", request.method,
                  request.url.path, response.status_code)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request, exc):
        if exc.status_code == 404:
            return _refusal("not_found", "No route for this request.")
        if exc.status_code == 405:
            return _refusal("method_not_allowed",
                             "Only POST / and GET /health exist.")
        return _refusal("internal_error", "Internal engine error.")

    @app.post("/")
    async def _rpc(request: Request):
        if not _is_loopback_origin(request.headers.get("origin")):
            _LOG.warning("POST / -> 403 cross_origin_denied")
            return _refusal("cross_origin_denied",
                             "Foreign Origin denied on loopback HTTP.")
        media = request.headers.get("content-type", "").split(";")[0]
        if media.strip().lower() != "application/json":
            return _refusal("unsupported_media_type",
                             "POST / needs Content-Type: application/json.")
        try:
            declared = int(request.headers.get("content-length") or 0)
        except ValueError:
            declared = 0
        if declared > MAX_BODY_BYTES:
            return _refusal("body_too_large",
                             f"Bodies over {MAX_BODY_BYTES} bytes refused.")
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return _refusal("body_too_large",
                             f"Bodies over {MAX_BODY_BYTES} bytes refused.")
        if not slots.acquire(blocking=False):
            _LOG.warning("POST / -> 503 server_busy")
            return _refusal("server_busy", "Server saturated; back off.",
                             headers={"Retry-After":
                                      str(RETRY_AFTER_SECONDS)})
        try:
            result = transport.handle(body.decode("utf-8", "replace"))
        except Exception as exc:  # coded errors stay data, never 500s
            payload = error_payload(exc)
            code = payload["code"]
            if code == "internal_error" and getattr(exc, "code", None) is None:
                _LOG.exception("POST / -> 500 uncoded crash")
            else:
                _LOG.info("POST / -> %s %s", status_for_code(code), code)
            headers = {}
            retry = retry_after_for(code, RETRY_AFTER_SECONDS)
            if retry is not None:
                headers["Retry-After"] = retry
            return JSONResponse(status_code=status_for_code(code),
                                content=payload, headers=headers or None)
        finally:
            slots.release()
        return JSONResponse(status_code=200, content=result)

    @app.get("/health")
    async def _health():
        return {"status": "ok"}

    return app


class _Serving:
    """Uvicorn listener with the stdlib server's duck shape.

    Args:
        app: FastAPI app to serve.
        host: Loopback bind host (already guarded).
        port: Bind port; 0 picks an ephemeral port.
    """

    def __init__(self, app, host, port):
        self._host = host
        self._port = port
        self._server = uvicorn.Server(uvicorn.Config(
            app, host=host, port=port, log_level="warning"))

    @property
    def server_address(self):
        """(host, port): the live port once bound, else configured.

        Returns:
            Host plus the bound port, or the configured port before
            the listener comes up.
        """
        servers = getattr(self._server, "servers", None) or []
        sockets = getattr(servers[0], "sockets", None) if servers else None
        if sockets:
            return (self._host, sockets[0].getsockname()[1])
        return (self._host, self._port)

    def wait_until_ready(self, timeout=10):
        """Block until the listener accepts, or raise on timeout.

        Args:
            timeout: Seconds to wait for the bound socket.

        Raises:
            TimeoutError: the listener never came up in budget.
        """
        deadline = time.time() + timeout
        while not getattr(self._server, "started", False):
            if time.time() > deadline:
                raise TimeoutError("HTTP listener never became ready.")
            time.sleep(0.01)

    def serve_forever(self):
        """Serve until shutdown (blocking, like serve_forever)."""
        self._server.run()

    def shutdown(self):
        """Ask the serving loop to exit."""
        self._server.should_exit = True

    def server_close(self):
        """Release the listener (uvicorn cleans up on exit)."""


def create_server(engine, host="127.0.0.1", port=0, project_id=None):
    """Bind a loopback-only HTTP server around an engine.

    Args:
        engine: Engine the requests submit against.
        host: Bind host; must be loopback (default 127.0.0.1).
        port: Bind port; 0 picks an ephemeral port.
        project_id: Optional scope; requests for another project
            are denied, never routed.

    Returns:
        Unserved _Serving listener (serve_forever/shutdown shape).

    Raises:
        AdapterError: non_loopback_bind_denied for a non-loopback host.
    """
    check_loopback_host(host)
    transport = HttpTransport(engine, project_id=project_id)
    return _Serving(create_app(transport), host, port)


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
