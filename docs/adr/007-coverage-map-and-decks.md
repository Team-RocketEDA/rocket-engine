# ADR-007: Stage tables are the coverage map; adapters are the decks

*Status: accepted (2026-11-01) | Tickets: [WORKFLOW-COVERAGE](../tickets/WORKFLOW-COVERAGE.md), [DECK-XSCHEM](../tickets/DECK-XSCHEM.md)*

## Context

The workflow stage tables (D01-D30, A01-A23, P01-P23,
M01-M16) were written to answer "which provisioned
tools cover which steps" — librelane alone covers ~90%
of digital in one deck. But the tables name ops without
linking covering decks, so coverage is felt, not read.
Meanwhile multi-step flows already run behind single
ops (`digital_flow`, `cosim`), proving the deck pattern.

## Decision

Three layers, no more: (1) stage tables are the
tool-coverage map — every step names its covering
deck(s) or an explicit `uncovered` marker with reason;
(2) adapters are execution decks running fixed flows
behind one op; (3) the python console is the
bespoke-deck escape hatch for weird requirements.
There is no generic stage-walker op: fuel composes
ops into plans; the engine runs ops and decks.

## Alternatives considered

1. **`run_workflow(stage_list)` engine runner.**
   Rejected: duplicates fuel's planner and bypasses
   the deck pattern; ordering across ops is the
   planner's job, safety across ops is the gates'
   (ADR-004).
2. **Tables as pure docs.** Rejected: rots on contact;
   the map must be computed from tables + live setup
   probes (`plan_from_capabilities`), not prose.
3. **One mega-deck per lane.** Rejected: destroys the
   per-step evidence (verdicts, logs, margins) that
   planning, UI progress, and completion reports need.

## Consequences

- Positive: "what can run now" is always answerable
  from tables + probes; uncovered steps are named gaps.
- Positive: new tools land as decks with a coverage
  entry — the onboarding path is mechanical.
- Negative: every deck addition must update the map
  (enforced by WORKFLOW-COVERAGE acceptance tests).
