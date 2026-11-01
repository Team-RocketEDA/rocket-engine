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

- `canvas.cst` in the project canvas: design
  intent AND tooling knobs in one file. TOML
  with sections per concern — `[meta]` (pdk +
  revision pin), `[targets.*]` (clocks, area,
  power, analog specs, photonic targets, mixed
  bindings), `[tools.<tool>]` (per-tool knobs:
  density, effort, corners, sim options).
  TOML-first: sections stay flat, it stays
  readable; nesting that outgrows TOML is a
  smell that something belongs in its own file.
- Path references for delegated content: a knob
  or target may point at a project-relative path
  (`drc_deck = "./decks/m1_minimal.py"`, tcl
  scripts, SDC snippets) instead of inlining.
  Refs resolve contained in the project, hash
  into the run closure (I28), drift-checked
  like every project doc.
- Per-PDK default templates + generator: the
  engine ships a `canvas.cst` template per
  supported PDK (sane targets + knobs for that
  node), and project creation runs the generator
  (PDK → template → filled canvas.cst). This is
  the backend the project-creation wizard calls.
- Engine COMPILES it to tool-native forms —
  SDC for yosys/opensta/librelane, measure/corner
  decks for ngspice, config fragments for
  librelane — single source, adapters translate.
- Run targets (run_spice bounds today from
  fuel constraints.yaml) migrate to canvas.cst
  as the single source; fuel reads the same file
  (iteration config stays fuel-side).
- Validation: unknown metrics/knobs rejected,
  units checked, PDK revision pinned, refs
  contained; drift-safe like every project doc.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- A digital canvas.cst compiles to SDC that
  yosys+opensta accept; an analog one drives
  run_spice bounds end to end (tests pin both).
- Per-PDK generator output validates clean for
  every supported PDK; wizard path creates a
  project with a filled canvas.cst (tests pin).
- Path refs resolve + hash into run closure; a
  moved/edited ref re-verifies or fails loud,
  never silent.
- Fuel's opamp checks expressible 1:1 in
  canvas.cst (migration probe, no silent drops).
- UI can render + edit every section from the
  schema alone (schema-tested).
