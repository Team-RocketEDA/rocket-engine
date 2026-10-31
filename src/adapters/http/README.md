# adapters/http — HTTP service surface

## Responsibility (PRD)

The engine's HTTP face: commands and artifact fetch over HTTP, project
events over SSE ([tech-stack](../PRD/tech-stack.md) "Web service":
FastAPI + Uvicorn; separate UI and agent streams). Duplex: requests in
through the `interfaces/` command port, events and results out.

## Boundaries

Owns: routes, SSE resume, auth/project scope, request limits. Must not
own: preflight, evidence, solver knowledge of any kind.

## Routing

- Command/event shapes → `../../interfaces/README.md`.
- Parent rules → `../README.md`.

## Status

Stub (empty). Slice 5. Invariants I05 (caller parity), I12 (transport
identity). Tests: `tests/adapters/` vs fake engine.

## Authentication (deferred, mandatory)

HTTP senders are untrusted: anyone can reach this surface, so nothing
in the envelope proves who approved what. The content hashes
(`interfaces/`) only cover data already in hand — they say nothing
about the sender. This adapter therefore MUST grow authentication
before any backend wiring: human vs agent credentials with different
power (agent credentials request and observe; only human credentials
approve), actor identity from trusted auth context, never from the
payload. Deferred until the engine core is done — cross this bridge
when we get there, not before.
