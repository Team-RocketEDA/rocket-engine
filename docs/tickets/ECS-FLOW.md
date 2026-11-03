Why: the user wants the ECS flow stated as law (change -> world
manager -> modify -> notify subscribers) and asked whether the
`esper` Python ECS library can replace our handrolled
`src/stores/ecs.py`.

Docs read (esper README + API reference, esper 3.x): MIT, pure
Python, zero dependencies; module-level functions (the World
object is gone in 3.x, named contexts switch process-global
state); integer entity IDs; `get_component`/`get_components`
queries; processors with `process()`; pub/sub is stringly-named
`dispatch_event(name, *args)` + `set_handler(name, func)` with
minimal error checking.

Verdict: do NOT wholesale-replace. esper is in-memory only — no
stable string IDs (it mints ints; the engine needs `ent-<12hex>`
for docs/ledger/rewind), no doc projection, no revision gates,
no idempotent replay, no ledger, no backfill. Adopting it as the
core would delete the durability story and add a second identity
system, which `ecs.py`'s own header forbids. Its event dispatch
is also untyped by-name, weaker than our ledger events.

Do instead, in order:

1. Split `src/stores/ecs.py` (1508 lines, 3x the 500-line module
   rule) into one-word-per-level submodules (e.g. stores/ecs/
   with addressing, records, queries, backfill separated), no
   behavior change, honesty scan kept green.
2. Add the missing half of ENGINE-ECS-FLOW: an in-process
   synchronous subscriber registry beside the ledger. Mutations
   already modify-then-append-`component_changed`; the registry
   delivers exactly that appended event to subscribers (adapters,
   watch fan-out) instead of forcing every consumer to poll.
   Same event shape, never a second invention.
3. Revisit esper only for processor-style passes behind the seam
   (if ever), never as the entity manager.

Record the flow as ENGINE-ECS-FLOW in behavior-invariants.yaml
(done with this ticket's first commit).

## Grill Record — Final (accepted by owner 2026-11-03, see ADR-017)

- D1 (settled): One shared Engine instance per process, many
  ports attached at the same time. One dock, many ships — not a
  dock per ship. Adapters (stdio, HTTP, in-process MCP, console
  sessions) attach as ports to the single world; a change through
  any port modifies the world once and the bus re-emits the
  appended event to the other ports. Cross-process notification
  keeps riding the durable ledger (`get_events_since` polling);
  esper never crosses a process boundary.
- D2 (settled): Async push with client acks, NATS-JetStream style —
  sync fan-out rejected. Rationale: high-frequency IDE updates and
  concurrent AI scripting on the same world would stall each other
  under synchronous delivery; one slow ship must never block the
  dock. Mutation still lands synchronously through the manager
  (admission + ledger append stay on the writer's path); only
  *notification* fans out async.
- D3 (settled): QoS-1 is the mental model for port delivery.
  At-least-once with acks; duplicates possible on redelivery and
  collapsed by ledger position (revision + event id is the packet
  ID); every port handler applies idempotently (position check,
  then apply). QoS-2-style exactly-once handshakes rejected:
  notify events are statements of fact, never instructions to
  act, so receiving one twice re-renders the same state. Acting
  (mutation landing, solver runs) stays on the synchronous
  admission path with request ids — a separate channel.
- D4 (settled): Slow-consumer policy is restart-and-resync, not
  redelivery-forever. A port that goes without ack past the
  threshold is quarantined: the dock stops flooding it, drops its
  backlog, and bubbles a restart directive into the adapter. The
  client re-runs its onboarding ritual (enumerate current project
  state, resubscribe from the current cursor) to resync without
  needing history. Requires idempotent initiation: running the
  onboarding ritual twice against the same state must be safe.
- D5 (settled): No-ack escalation is staged and tunable,
  default 10/15/20s (warn, quarantine backlog, resync directive).
  The engine never kills the client: a hung-but-recovering
  process comes back to find a resync flag waiting, drops its
  stale view, and re-runs the idempotent onboarding ritual from
  the current cursor. Thresholds are per-port tunable; the flag
  is engine-side state, never the client's word.
- D6 (settled): Boot-time default port profile plus a runtime
  config menu. The default profile is stdio alone; a local-only
  control call toggles ports live (e.g. stdio asks the engine to
  turn on MCP when the agent arrives, loopback HTTP when the IDE
  wants network). Disabling a port quarantines it like a dead
  ship: backlog dropped, resync flag set if it returns.
- D7 (settled): The MCP port is pull-by-default, never push. A
  server-initiated push would wake the AI on every UI change and
  spam it; wake-up hooks or observers are the fuel client's job,
  not the engine's. Push stays available as a per-port opt-in.
  Pull reuses the existing cursor event log (accumulate, not
  reconstruct): the client polls from its cursor and the ledger
  returns what it missed — no new diff func, no snapshot pinning,
  no concurrent-mutation races. D4/D5 apply unchanged: a client
  that never pulls is quarantined and resyncs on return.

## Build (Ready, needs own RED per slice)

1. Single shared `Engine` per process with port attach/detach;
   adapters stop constructing private engines (D1, D6).
2. Async per-port queues with acks over the appended ledger
   event; shared position-check apply guard all ports use
   (D2, D3). Queue-depth ceiling beside the time threshold.
3. Quarantine ladder: staged 10/15/20s tunable escalation, drop
   backlog, set engine-side resync flag, never kill (D4, D5).
4. Boot default stdio; local-only runtime toggle; disable path
   quarantines like a dead ship (D6).
5. MCP pull path over the existing cursor log; push opt-in only
   (D7).
6. Split `src/stores/ecs.py` (1508 lines) into one-word-per-level
   submodules first if the bus touches it — no behavior change,
   honesty scan kept green.

Validation (RED before each): cross-port delivery test, same-
position redelivery applies once, staged quarantine fires with
flag + resync convergence, toggle mid-run, MCP pull catches up
from a stale cursor. Gates: api_spec, docstrings, extended
no-private-writers scan over the bus.
