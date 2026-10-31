# POSTLAYOUT: run_post_layout via ngspice on extracted netlists

*Status: Ready · Depends: none · Size: M ·
Roadmap: to-GDS lane (MVP track, serves D28/A19/P18/M12/M13)*

## Why

Five PRD stages across all four domains end at
`run_post_layout` — repeat the sims on the EXTRACTED
implementation and report pre/post deltas — and no
adapter serves it. Without this op every flow stops at
"layout exists" and never closes the loop to "layout
still meets spec." ngspice is already live; this binds
it to extracted netlists with provenance instead of
ideal schematics.

## What

- RED-first: `run_post_layout` ToolAdapter (deck.tool
  `ngspice`): takes extracted_netlist + compatible
  models + testbench + extraction_provenance; outputs
  measurements, waveforms, and pre/post comparison
  against the schematic run referenced by run_id.
- Provenance enforced: refuses to run when the
  extraction record is missing or stale (no silent
  schematic-as-extracted substitution, ever).
- Bandgap + sigma-delta fixtures: post-layout deltas
  green and nonzero-proven (a zero delta on a lossy
  extraction fails the test, not the design).

## Acceptance

- One call replays an analog block post-layout with a
  pre/post delta table; stale provenance refused loudly.
- Contract + api_spec regen; full suite + gate green.
