# ENTITY-CAS: per-entity revisions + compare-and-swap

*Status: Ready · Depends: none · Size: M ·
Roadmap: human+agent collaboration (MVP track)*

## Why

One global revision per project makes every
concurrent human+agent edit a `revision_conflict`
(last-writer-loses) — unworkable once fuel drives
the engine while the human watches. OT (overleaf)
needs per-op-pair transforms; CRDTs bring
eventual consistency to deterministic signoff.
Both rejected. The right shape is postgres rows:
writers on different entities never conflict;
same-entity concurrent writes conflict with retry.
Entities already exist (`engine_ecs_store`); every
mutation is already idempotent + revision-gated —
this narrows the conflict scope, not the mechanism.

## What

- Each entity (cell, wire, doc, setting) carries
  its own revision; mutations CAS against it.
- Different-entity concurrent writes both land;
  same-entity concurrent writes raise
  `revision_conflict` naming the entity + expected
  vs actual, safe to retry after re-read.
- Global project revision stays as the coarse
  cursor (events, coalescing, replay); entity
  revisions gate writes.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Human + agent editing different entities
  concurrently: zero conflicts (test pins).
- Same-entity race: exactly one wins, the loser
  gets a structured conflict with retry data —
  never a silent overwrite.
