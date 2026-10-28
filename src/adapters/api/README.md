# adapters/api — HTTP service surface

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
