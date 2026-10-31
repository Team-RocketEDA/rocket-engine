# BLOCK-RUNS: Block-scoped run targets (run-from-block)

*Status: Ready · Size: M · Roadmap: convergence (MVP track)*

## Why

Hierarchical verification starts the day a user can
right-click a block and simulate just that block. Today
every `run_*` targets the project; the run system does not
know entities exist, so run-from-block, "rerun everything
affected by this edit," and per-block regression are all
unexpressible. The fix is small and surgical: teach run
targets an entity scope so `target: {scope: block, id}`
flows through submit → preflight → snapshot → verdict with
the same honesty as project runs. This is the seam where
the ECS world-view meets the execution substrate — do it
now while the verb surface is small, before new verbs
cement project-only targeting.

## What

- RED-first: `target.scope: block` accepted on run verbs
  (SPICE + syntax first, decks following); preflight
  resolves the entity, snapshots its component closure
  (sources, CellLink, params, constraints), and records
  scope in verdicts + provenance.
- Unknown block id fails submit with a named reason;
  block verdicts cite `(run_id, revision, block_id, deck)`.
- No new verbs: scope rides the existing `target` shape;
  any future verb ships with a scope parameter from birth.

## Acceptance

- Block SPICE run greens against a golden while a sibling
  block's breakage leaves it untouched; provenance cites
  the block; project runs unaffected.
- Contract + api_spec regen; full suite + gate green.
