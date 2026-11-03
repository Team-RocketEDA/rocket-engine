# COVERAGE-MAP: D/A/P/M coverage-map decks committed

*Status: Ready · Depends: API-GENERALIZE · Size: S · Roadmap: coverage (MVP track) · Parent: CANVAS-CST (Step 6d)*

## Why

The engine claims D/A/P/M coverage but has no single artifact saying which
operation × PDK × tool combinations actually verify green. A coverage map
turns the claim into a checkable deck: deploy/test bench running every
supported combo against the committed design files (pico core, sigma-delta,
photonic/pdk fixtures already in the tree), recording pass/fail per cell.
Frontend and harness teams read the map to know what is real; gaps become
tickets instead of surprises.

This is also the demo ledger: "natural language to GDS" is credible only
where the map is green, and the map is what the November demo walks.

## What

- Committed `coverage/` map: operation × PDK × tool matrix with per-cell
  verdicts from the committed fixtures, re-runnable in one command.
- Correct AND incorrect (mutated) fixtures per lane so the map proves the
  engine distinguishes good designs from bad, not just that good ones pass.
- Map regen is deterministic; stale cells fail the check rather than
  silently going red.

## Acceptance

- Coverage decks run green on all claimed combos; a mutated fixture flips
  its cell to fail (tests pin both directions).
- The committed map file is current with the tree — CI or a check command
  rejects a stale map.
- Contract + api_spec regen if surfaces change; suite green.
