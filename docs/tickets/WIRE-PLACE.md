# WIRE-PLACE: Wire/junction entities + connect ops + stable net IDs

*Status: Ready · Depends: ENGINE-ECS, CONNECT-GRAPH · Size: L ·
Roadmap: convergence (MVP track, agent-drawn connectivity)*

## Why

`place_cell` lets an agent place components — but a pile of
unplaced-together blocks is not a circuit. Nothing in the
engine today can draw a wire, tap a net, or durably record
"pin A connects to pin B," so the agent loop stops one step
short of a real chip: it can author netlists as text, but it
cannot construct connectivity as data. Wires must be
first-class entities (placeable, movable, splittable,
deletable, rewindable) with endpoints terminating on stable
pin/port/junction IDs — and inferred nets must materialize
with stable IDs too, or the agent can never say "the net I
just made." This is the load-bearing half of placement.

## What

- RED-first: Wire entity (segments, layer, endpoints) +
  Junction entity (explicit dots, never accidental
  crossings); ops `place_wire`, `connect_endpoint`,
  `move_wire`, `split_wire`, `delete_wire` as durable
  attributed revisions through the entity store.
- Endpoints reference pin/port/junction/net entity IDs
  (ENGINE-ECS); dangling endpoints allowed transiently,
  flagged by ERC, never silently dropped.
- Nets derived from CONNECT-GRAPH extraction, then
  materialized as Net entities with stable IDs under the
  shared `net_name()` authority — emitters, ERC, and
  agents all read the same net identity.
- Agent loop shape: place → wire → simulate → verdict,
  all durable, all rewindable.

## Acceptance

- Place 2 blocks → wire pin-to-pin → Net entity appears
  with a stable ID → SPICE emitter names it identically →
  ERC sees it → rewind removes wire + net cleanly.
- Full place→wire→simulate→verdict loop green through
  the duplex channel, no console needed.
- Contract + api_spec regen; full suite + gate green.
