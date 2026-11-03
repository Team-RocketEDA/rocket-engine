# ADR-017: Shared-engine port bus with async QoS-1 delivery

*Status: accepted (2026-11-03) | Ticket: [ECS-FLOW](../tickets/ECS-FLOW.md) | Grill: accepted by owner, D1–D7*

## Context

Every adapter builds its own `Engine` today (MCP server, stdio,
HTTP, plus a help engine), so a change through one port notifies
nobody on the others. The durable ledger already orders every
mutation (`component_changed` with entity/component/revision) and
serves catch-up reads (`get_events_since`, cursor `watch`), but
nothing pushes: consumers poll, and there is one in-memory world
per `Engine`, not one world per process. High-frequency IDE
updates and concurrent AI scripting on the same project need a
bus that never lets one slow consumer stall the writers.
ENGINE-ECS-FLOW (`behavior-invariants.yaml`) already requires
change → manager → modify → notify with no direct doc writes;
this ADR settles the notify half. ADR-010 (hand-rolled stdlib ECS
store) stands: the store stays the entity manager.

## Decision

One shared `Engine` per process with many ports attached at once —
one dock, many ships. Adapters (stdio, MCP, loopback HTTP,
console sessions) attach as ports to the single world; a change
through any port modifies the world once and the bus re-emits the
appended ledger event to the other ports:

- D1: single shared `Engine` per process; cross-process
  notification keeps riding the durable ledger (polling).
- D2: async push with client acks, NATS-JetStream style. Mutation
  landing stays synchronous on the writer's path; only
  notification fans out async. Sync fan-out rejected: one blocked
  port would freeze every writer.
- D3: QoS-1 is the delivery model. At-least-once with acks;
  duplicates collapse by ledger position (revision + event id is
  the packet ID); port handlers apply idempotently (position
  check, then apply). QoS-2 handshakes rejected: notify events
  are statements of fact, never instructions to act.
- D4: slow consumers get restart-and-resync. Past the threshold
  the port is quarantined (backlog dropped) and handed a resync
  flag; the client re-runs its onboarding ritual from the current
  cursor. Requires idempotent initiation.
- D5: staged tunable escalation, default 10/15/20s
  (warn, quarantine, resync directive). The engine flags, never
  kills, the client.
- D6: boot-time default profile is stdio alone; a local-only
  control call toggles ports live (MCP when the agent arrives,
  loopback HTTP when the IDE wants network).
- D7: the MCP port is pull-by-default (cursor polls over the
  existing event log), never push — pushes would wake the AI on
  every UI change. Push stays a per-port opt-in; wake-up hooks
  are the fuel client's job.

## Alternatives Considered

### Alternative 1: One Engine per adapter, ledger polling only
- **Pros**: no new machinery; matches current construction.
- **Cons**: no push path exists at all; every consumer polls.
- **Why not**: the requested flow (a port's change re-emitted to
  other ports) cannot exist without a shared world.

### Alternative 2: Synchronous ordered fan-out
- **Pros**: trivial ordering, one mechanism, deterministic.
- **Cons**: slowest port sets the pace; a wedged port freezes
  writers and every other port.
- **Why not**: fails the stated high-frequency IDE + AI
  scripting scenario by construction.

### Alternative 3: esper as the entity manager
- **Pros**: MIT, pure Python, zero deps; real ECS queries and
  `dispatch_event`/`set_handler` pub/sub.
- **Cons**: in-memory only; integer IDs (engine needs
  `ent-<12hex>`); no doc projection, revision gates, replay, or
  ledger; 3.x module-global state fights multi-project use.
- **Why not**: adopting it deletes the durability story and adds
  a second identity system (see ADR-010). Revisit only for
  processor-style passes behind the seam, never as the manager.

### Alternative 4: QoS-2 exactly-once notify handshake
- **Pros**: protocol-level no-dupe guarantee.
- **Cons**: double the round trips for every event.
- **Why not**: nothing in the notify path acts twice badly;
  redelivery of a fact re-renders the same state.

### Alternative 5: Reconstruct diffs on pull instead of accumulating
- **Pros**: stateless ports, no backlog.
- **Cons**: needs snapshot pinning against concurrent mutation,
  pin retention and expiry — new races throughout.
- **Why not**: the cursor log already accumulates; a range read
  has none of the reconstruction races.

## Consequences

### Positive
- Cross-port awareness with one mechanism: same event shape to
  every subscriber, ledger position as the universal dedupe key.
- Writers never stall on readers; slow consumers degrade to
  resync instead of dragging the engine.
- MCP stays quiet by default; the AI wakes on its own polls and
  fuel-owned hooks, never on UI churn.
- Existing cursor reads (`get_events_since`, `watch`) become the
  pull path and the late-joiner path with no new API shape.

### Negative
- A per-port queue/dispatcher subsystem must be built, with
  ack tracking, thresholds, and quarantine directives.
- At-least-once obligates every current and future port handler
  to the position-check-then-apply contract.
- Reconnects must come back as new ports with fresh cursors, or
  quarantine becomes dodgeable.

### Risks
- A port that acks slowly but never trips the threshold grows
  its queue without bound — mitigate with a queue-depth ceiling
  beside the time threshold, tuned from measured client behavior.
- Position checks implemented per-port by hand will drift —
  mitigate with one shared apply-guard helper all ports use.
- The runtime toggle is a new local control surface — mitigate
  by keeping it local-only under the LOCAL-SINGLE-USER boundary
  (no remote reachability, same as every other endpoint).
