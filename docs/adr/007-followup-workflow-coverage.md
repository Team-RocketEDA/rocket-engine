# ADR-007 followup: the coverage map is computed, not written

*Follows [007-coverage-map-and-decks](007-coverage-map-and-decks.md)
| Tickets: [COVERAGE-MAP](../tickets/COVERAGE-MAP.md),
[WORKFLOW-COVERAGE](../tickets/WORKFLOW-COVERAGE.md),
[DUMP-PROOFS-WAVE1](../tickets/DUMP-PROOFS-WAVE1.md)*

## What landed

ADR-007 said the map "must be computed from tables + live setup
probes (`plan_from_capabilities`), not prose". The mechanism:

- `src/workflows/stages.py` gains the deck join: a curated
  `DECKS` table (op -> deck-tool plus provision need) pinned
  mechanically to the live Engine solver registry and
  `SOLVER_DEPS` by `tests/test_stages_decks.py`, plus
  `covering_decks` / `flow_cover` / `render_lane`. Every stage
  entrypoint resolves to a deck, a probe-gated deck, or an
  explicit `uncovered` marker with a reason — `run_thermal`
  (mixed M14, photonic P19) is the only uncovered entrypoint,
  and it says so out loud.
- `src/workflows/capability_plan.py`: every planned stage now
  carries `decks` cites, so each blocker resolves to the same
  deck/probe-gap naming the completion report needs.
- `coverage/map.json` + `coverage/check.py`: the committed
  op x PDK x tool matrix (9 wave-1 cells across D/A/P/M lanes,
  correct plus mutated fixtures per lane) with a fingerprint
  over the workflow tables plus the v1 task/tool catalogs.
  `coverage/check.py` re-runs every cell through the real
  adapter parse in both directions and rejects a stale map.
- `docs/tool-outputs/`: per-tool output notes for the wave-1
  kept set (magic, klayout, netgen, slang, connectgraph, sby)
  with grammars, exit states, and fixture paths; determinism
  is pinned by `tests/test_coverage_wave1.py`.

## Consequences (additive to ADR-007)

- Positive: "what can run now" stays answerable after every
  deck addition — the freshness tests fail when a new solver
  lands without a `DECKS` entry, and the map check fails when
  tables or catalogs move without a restamp.
- Negative: the curated `DECKS` table duplicates the registry
  by design; the duplication is load-bearing (pure planning
  inputs, no imports) and checked, not trusted.
- Out of scope: deck lanes owned by sibling tickets
  (librelane digital flow, xschem, ngspice-class sims, yosys,
  icarus, gdsfactory) join the same tables with their waves;
  the map's `scope` field says which waves are claimed.
