# HTTP JSON command transport

HttpTransport.handle parses one JSON object containing project_id, operation, optional arguments, and optional request_id. It enforces an optional bound project and delegates to Engine.submit. `serve_http` wraps the same transport in a FastAPI app on uvicorn: POST a JSON envelope to `/` for an admission ack or query result, GET `/health` for a liveness probe, GET `/events` for the runtime lifecycle log as Server-Sent Events (PUSH-EVENTS; pass a runtime to `serve_http`/`create_server`/`create_app` to bind it — replay since `cursor`, then live frames with heartbeat comments). Without a bound runtime `/events` refuses loudly with `runner_unavailable` (503); polling get_events_since stays the watch path there.

## Listener hardening

POST `/` requires `Content-Type: application/json` (415 otherwise), refuses bodies over 1 MiB (413), accepts a missing Origin or a loopback one only (403 for foreign origins — the browser-CSRF class), and bounds concurrency at 32 in-flight requests (503 + Retry-After on overflow). Engine errors serialize with their v0 code, message, and fields at the status from the shared code table (`adapters/errors.py`, pinned to the v1 errors catalog); uncoded crashes become a generic 500 with the traceback server-side only. Every request writes one audit line (`METHOD /path -> status`) to the `rocket_engine.http` logger.

## Trust boundary (ADR-006)

This adapter is localhost-only with no auth, serving the same caller-blind API as every other transport. The trust boundary is the loopback interface: `serve_http`/`create_server` bind loopback hosts only (127.0.0.1 by default; any 127/8 address, `localhost`, or `::1`) and refuse any non-loopback bind with `non_loopback_bind_denied`. Startup prints a banner stating the model. Remote/multi-user access needs a separate authenticated adapter — never this one with a flag. See the [HTTP boundary decision](../../../docs/adr/006-localhost-only-http.md) and the [provision plan](../../../docs/provision-plan.md#loopback-only-http-no-remote-deploy).

## Boundaries

The adapter owns JSON parsing, request IDs, and project-scope checks. It does not own operation validation, state, solver selection, or verdicts. Command shapes are shared with [interfaces](../../interfaces/README.md); the parent transport map is in [adapters](../README.md).
