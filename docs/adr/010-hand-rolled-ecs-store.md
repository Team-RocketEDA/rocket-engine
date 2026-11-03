# ADR-010: Hand-rolled stdlib ECS store, no ECS library

*Status: accepted (backfilled 2026-11-01; implementation:
`src/interfaces/engine_ecs_store.py`, ENGINE-ECS) | Tickets:
[ENTITY-CAS](../tickets/ENTITY-CAS.md)*

## Context

Every engine surface invented its own identity (doc paths
for sources, refs for blocks, names for nets). The ECS
ends that: engine-minted entity IDs, generic component
CRUD, uniform `component_changed` events, filter queries.
The question is why hand-rolled (1466 lines, stdlib +
`json` only) instead of a Python ECS library.

## Decision

The store is hand-rolled as a leaf module (no new deps,
no package-internal imports). Entities live as docs at
`entities/<id>.json` — the path derives from the id, so
existing `list_docs`/`read_doc`/`write_doc` work on them
with no second identity system. IDs are engine-minted
(`ent-<12hex>`, callers can never supply one); existing
docs backfill read-only `doc-<12hex>` ids without a
write. World snapshots are miniplex-shaped for direct
frontend mirroring. Every mutation gates on revision,
replays idempotently, advances once, and returns
approval-UI fields.

## Alternatives considered

1. **ECS library (e.g. esper).** Rejected: a library
   gives in-memory component bags — the thin part. The
   thick parts (doc-store projection, minted identity,
   ledger events, revision gating, backfill, miniplex
   snapshots) are engine semantics no library provides
   and would be hand-rolled anyway, plus a dependency
   and an impedance layer.
2. **Bespoke endpoints per feature.** Rejected: that
   was the status quo ante (N getters, N notifiers);
   the ECS exists to end it.
3. **Database-backed store.** Rejected: the doc store
   + ledger already persist; entities as docs keep one
   storage story (ADR-001).

## Consequences

- Positive: zero dependencies, zero import cycles,
  fully testable standalone (`EntityStore` reference
  implementation + wiring tests).
- Positive: identity, events, and queries cannot
  drift — one addressing scheme end to end.
- Negative: 1466 lines owned forever; component
  query power is exact-match predicates only.
