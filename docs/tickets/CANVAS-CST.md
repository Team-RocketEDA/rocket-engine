# CANVAS-CST: single global canvas.cst design-intent file

*Status: Ready · Depends: none · Size: M ·
Roadmap: design intent (MVP track)*

## Why

Every lane needs stated design intent (clock, power,
gain, loss...) and today it lives nowhere
engine-side: fuel carries `constraints.yaml` checks
for the agent, tools take CLI args, and synthesis
flows take their own configs. The project canvas
needs one editable `canvas.cst` — human-writable,
agent-writable, UI-rendered, engine-consumed —
stating what the design must achieve across D/A/P.
It builds on PDK data (liberty, models, decks),
never regurgitates it. The agent loop becomes
{prompt + canvas.cst + PDK + tools}, all
client-agnostic.

## What

- `canvas.cst` in the project canvas, YAML under
  schema `rocketeda/canvas-cst/v0.1`: meta (pdk +
  revision pin), digital (clocks, IO, exceptions,
  area, power, corners), analog (spec table +
  corners + loads + supplies), photonic (grid,
  loss/crosstalk/bandwidth targets), mixed
  cross-domain bindings where needed.
- Engine COMPILES it to tool-native forms —
  SDC for yosys/opensta/librelane, measure/corner
  decks for ngspice, config fragments for
  librelane — single source, adapters translate.
  Flow knobs (density, effort) stay run params,
  never intent.
- Run targets (run_spice bounds today from
  fuel constraints.yaml) migrate to canvas.cst
  as the single source; fuel reads the same file
  (iteration config stays fuel-side).
- Validation: unknown metrics rejected, units
  checked, PDK revision pinned; drift-safe like
  every project doc.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- A digital canvas.cst compiles to SDC that
  yosys+opensta accept; an analog one drives
  run_spice bounds end to end (tests pin both).
- Fuel's opamp checks expressible 1:1 in
  canvas.cst (migration probe, no silent drops).
- UI can render + edit every section from the
  schema alone (schema-tested).
