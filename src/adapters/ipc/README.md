# adapters/ipc — Electron stdio transport

## Responsibility (PRD)

The desktop wire: Electron main owns one engine child over stdio;
framed length-prefixed JSON envelopes carry commands, responses, and
async events with correlation IDs and project identity
([tech-stack](../PRD/tech-stack.md) "Desktop engine transport",
[frontend-tooling-spec §8](../PRD/tools-research/frontend-tooling-spec.md)).
One process owns engine stdin; independent clients must not write it.
Duplex: framed commands in, framed events out.

## Boundaries

Owns: framing, correlation, reconnect cursor handoff. Must not own:
business logic, evidence, or anything renderer-side (RocketIDE).

## Routing

- Command/event shapes → `../../interfaces/README.md`.
- Parent rules → `../README.md`.

## Status

Stub (empty). Slice 5. Invariants I05, I12. Tests:
`tests/adapters/` vs fake engine.
