# ENGINE-ECS: Entity store + component CRUD + addressing + events

*Status: Done · Depends: none · Size: L ·
Roadmap: convergence (MVP track, agent-drawn connectivity)*

## Why

Every new engine surface invents its own identity: doc
paths for sources, refs for blocks, names for nets — and
the miniplex mirror was promised engine schemas with no
engine mirror-source behind them. An entity store ends
this: ONE identity per thing, generic component CRUD
instead of N bespoke endpoints, uniform
`component_changed` events instead of per-feature
notification plumbing, and filter queries instead of
one-off getters. The clincher is wires: endpoints must
terminate on stable pin entities, and only an engine-owned
store can mint those IDs. Built as a projection over the
existing doc store + ledger (not a rewrite), this is
moderate effort that deletes whole categories of future
endpoints.

## What

- RED-first: entity store (entities + components JSON,
  engine-provisioned IDs only) projected over docs/ledger;
  ops `create_entity`, `get_component`, `set_component`,
  `attach_component`, `detach_component`, `delete_entity`.
- `entity.component` canonical addressing; doc paths stay
  as the storage projection with a documented mapping —
  no second identity system, ever.
- `component_changed(entity, component, revision)` events
  in the ledger/event stream; miniplex-shape world
  snapshot query for mirrors.
- Filter queries: `components_of(entity)`,
  `entities_with(component, predicate)` — nets-of-block,
  pins-of-net, open-problems become filters, not
  endpoints.
- Existing CRUD keeps working throughout; backfill maps
  current project docs onto entities without breaking
  revisions.

## Acceptance

- Create block entity → attach sources → wire references
  pin IDs → event stream shows each component change →
  world snapshot mirrors it; agent edits and human edits
  share the verbs.
- No path/entity drift: addressing tests prove one
  identity across CRUD, events, and queries.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
