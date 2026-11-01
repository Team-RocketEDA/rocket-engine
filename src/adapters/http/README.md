# HTTP JSON command transport

HttpTransport.handle parses one JSON object containing project_id, operation, optional arguments, and optional request_id. It enforces an optional bound project and delegates to Engine.submit.

This package is the request adapter only. It does not currently start an HTTP listener, expose FastAPI routes, stream events over SSE, or implement authentication. Clients can query get_events_since through the shared operation surface. The accepted [HTTP boundary decision](../../../docs/adr/006-localhost-only-http.md) describes the intended localhost deployment boundary; server wiring remains separate work.

## Boundaries

The adapter owns JSON parsing, request IDs, and project-scope checks. It does not own operation validation, state, solver selection, or verdicts. Command shapes are shared with [interfaces](../../interfaces/README.md); the parent transport map is in [adapters](../README.md).
