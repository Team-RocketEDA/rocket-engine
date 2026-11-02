# GENERATE-VIEWS: Graduate gdsfactory smoke to a real generate_views op

*Status: Done · Depends: none · Size: M ·
Roadmap: to-GDS lane (MVP track, serves layout construction)*

## Why

Same class as the Circulax finding: the gdsfactory
adapter is a smoke (`run_layout_smoke`, fixed MZI +
roundtrip) with its own docstring admitting "a full
layout Engine adapter is follow-up" — and `generate_views`
has no adapter at all. Layout import, device
construction, and GDS export through registered recipes
currently require hand-written console scripts; the PRD's
registered-recipe button path doesn't exist.

## What

- RED-first: `generate_views` ToolAdapter over the real
  installed gdsfactory: registered recipes (import GDS,
  build PDK cells, export GDS/OASIS) with identity
  mappings + diagnostics; sources are project inputs,
  never hardcoded cells.
- The MZI smoke demotes to a qualification fixture;
  PDK-cell coverage rides the PDK lanes (cell catalogue
  already serves discovery via list_cells).
- Macro pin/obstruction mapping published as artifacts
  per the PRD boundary note (import alone doesn't
  reconstruct them).

## Acceptance

- generate_views builds a cspdk MZI from project
  sources with identity mappings; GDS roundtrip is an
  artifact, not the test.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
