# ADR-008: Concurrent collaboration via per-entity CAS

*Status: accepted (2026-11-01) | Tickets: [ENTITY-CAS](../tickets/ENTITY-CAS.md)*

## Context

One global project revision makes every concurrent
human+agent edit a `revision_conflict`
(last-writer-loses) — unworkable once fuel drives the
engine while the human watches. Entities already exist
(`engine_ecs_store`), and every mutation is already
idempotent + revision-gated; the conflict scope is
wrong, not the mechanism.

## Decision

Compare-and-swap per entity (postgres-rows shape):
writers on different entities never conflict; only
same-entity concurrent writes raise, with retry data.
The global revision stays as the coarse cursor for
events, coalescing, and replay. OT and CRDTs are
rejected (below); git-like branch/merge is backlogged
for "agent tries a risky restructure."

## Alternatives considered

1. **OT (overleaf-style).** Rejected: needs transform
   functions per op pair — every new op multiplies the
   matrix; built for text, not typed netlist mutations.
2. **CRDTs (automerge-style).** Rejected: eventual
   consistency is the wrong shape for deterministic
   signoff verdicts; heavy dependency for a problem
   CAS solves.
3. **Global revision + manual retry (status quo).**
   Rejected: conflict rate scales with collaboration;
   the agent would fight the human constantly.

## Consequences

- Positive: conflicts become rare (same entity only)
  instead of constant; retries stay safe via
  idempotent request_ids.
- Positive: deterministic verdicts untouched — no
  eventual consistency near signoff.
- Negative: same-entity races still need human/agent
  judgment on retry (structured conflict names the
  entity + expected vs actual).
