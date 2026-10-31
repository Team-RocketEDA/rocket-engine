# ADR-002: Engine owns the project ledger; ADR-001 owns the bytes

*Status: proposed (2026-10-30) | Predecessor: [ADR-001](001-engine-storage-boundary.md)*

## Context

Two writers are coming: a human in the IDE and rocket-fuel, an
opencode-based design agent over MCP. Both mutate projects. Without
a single arbiter of "what is true about this project," their views
diverge silently — stale reads, lost updates, and frontend/engine
disagreement discovered three steps too late. ADR-001 already split
*byte* ownership (managed vs linked trees); this decision assigns
*truth* ownership.

## Decision

The engine owns the project **ledger**: revisions, the ordered
event log, run evidence index, and capability/provision state —
for every project, managed or linked. File bytes keep ADR-001's
split: managed projects live under `ENGINE_ROOT/projects`
(engine-owned); linked caller trees stay caller-owned
(engine reads by path, writes only `.rocket/`).

Consequences:

- Every engine-mediated mutation advances the project revision;
  stale `expected_revision` fails with `revision_conflict` (lost
  updates become impossible, not merely unlikely).
- Every mutation appends an actor-attributed event
  (human / rocket-fuel / system) to the durable log; clients
  resync via cursor, never by re-fetched guesswork.
- The CRUD surface operates on ledger + managed bytes; linked
  trees get read access plus watcher-style resync, never
  engine-owned writes outside `.rocket/`.
- Verdicts and run results are engine-owned exclusively: no
  client, agent included, can write a result — it can only ask
  for a run and read back (mirrors rocket-fuel's no-fake-results
  guarantee from the provider side).

## Alternatives considered

1. **IDE owns project truth.** Rejected: headless clients (MCP,
   CLI, CI) and the agent have no IDE; truth would fork per
   client with no arbiter.
2. **Stateless engine, files are truth.** Rejected: concurrent
   writers with no revisioning replays every classic split-brain;
   the filesystem has no compare-and-swap.
3. **Agent writes straight to disk.** Rejected: bypasses
   revisions, events, approvals, and audit — unreviewable
   autonomy.
