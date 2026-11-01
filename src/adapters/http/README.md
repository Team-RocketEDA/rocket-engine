# HTTP JSON command transport

HttpTransport.handle parses one JSON object containing project_id, operation, optional arguments, and optional request_id. It enforces an optional bound project and delegates to Engine.submit. `serve_http` wraps the same transport in a stdlib listener: POST a JSON envelope to `/` for an admission ack or query result, GET `/health` for a liveness probe. SSE event streams are not implemented; clients query get_events_since through the shared operation surface.

## Trust boundary (ADR-006)

This adapter is localhost-only with no auth, serving the same caller-blind API as every other transport. The trust boundary is the loopback interface: `serve_http`/`create_server` bind loopback hosts only (127.0.0.1 by default; any 127/8 address, `localhost`, or `::1`) and refuse any non-loopback bind with `non_loopback_bind_denied`. Startup prints a banner stating the model. Remote/multi-user access needs a separate authenticated adapter — never this one with a flag. See the [HTTP boundary decision](../../../docs/adr/006-localhost-only-http.md) and the [provision plan](../../../docs/provision-plan.md#loopback-only-http-no-remote-deploy).

## Boundaries

The adapter owns JSON parsing, request IDs, and project-scope checks. It does not own operation validation, state, solver selection, or verdicts. Command shapes are shared with [interfaces](../../interfaces/README.md); the parent transport map is in [adapters](../README.md).
