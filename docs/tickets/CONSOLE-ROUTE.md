# CONSOLE-ROUTE: Console mutations route to golden recipe via admission

*Status: Ready · Depends: none · Size: M ·
Roadmap: convergence (MVP track, I28 ingredients)*

## Why

A user in the scripting terminal adds a cell and wires
stuff — by corpus and engine design, that MUST land in
the golden recipe (non-gitignored describing state), not
in some console-local shadow. I28 says a script that
edits the project is an ingredient; the console is
therefore a client of the same admission every other
adapter uses. Any side-channel write path forks the
source of truth and breaks determinism, rewind, and the
agent's ability to trust what it reads back.

## What

- RED-first: console tier-2 effectful mutations (cell
  add/place, wire ops, doc writes) route through
  ProjectService admission: expected_revision gating,
  ledger events with actor + revision, idempotency —
  identical verbs to CRUD/MCP, shared with ENGINE-ECS
  and WIRE-PLACE addressing.
- Console namespace exposes the ECS/wire verbs (or
  thin wrappers naming them); zero direct doc-store
  writes from console tier-2 paths, proven by tests.
- Effects keep structured replay-with-run_ids reporting
  (report, never re-execute — see REPLAY-SAFE).

## Acceptance

- Terminal session adds cell + wires net → revision
  bumps, ledger shows actor + events, rewind covers it,
  fresh checkout regenerates identically.
- Contract + api_spec regen; full suite + gate green.
