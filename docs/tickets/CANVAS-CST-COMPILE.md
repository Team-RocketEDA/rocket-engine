# CANVAS-CST-COMPILE: canvas compiler, per-PDK templates, fuel probe

*Status: Ready · Depends: CANVAS-CST-CORE · Size: M · Roadmap: design intent (MVP track) · Parent: CANVAS-CST (Step 6b)*

## Why

A validated `canvas.toml` that nothing consumes is a declaration without
force. The engine must COMPILE it to tool-native forms — SDC for
yosys/opensta/librelane, measure/corner decks for ngspice, config fragments
for librelane — single source, adapters translate. And project creation needs
a starting point: per-PDK templates with sane targets + knobs for that node,
so the creation wizard fills a canvas that already validates.

The fuel migration probe closes the loop the other way: today's
`constraints.yaml` opamp checks must be expressible 1:1 in canvas.toml, so
run_spice bounds (today from fuel) migrate to canvas as the single source
with no silent drops.

## What

- Canvas → SDC / measure-corner decks / librelane config fragments;
  adapters translate, canvas never regurgitates PDK data.
- Per-PDK `canvas.toml` templates + generator backing the creation wizard.
- Fuel `constraints.yaml` checks expressed 1:1 in canvas.toml (probe).

## Acceptance

- A digital canvas.toml compiles to SDC that yosys+opensta accept; an analog
  one drives run_spice bounds end to end (tests pin both).
- Per-PDK generator output validates clean for every supported PDK; wizard
  path creates a project with a filled canvas.toml (tests pin).
- Contract + api_spec regen if surfaces change; suite green.

## Verdict (adapt lane, 2026-11-03) — compiler Done, live legs gated

`src/project/canvas/compile.py` lands canvas→SDC (create_clock from
the clock target), →run_spice bounds (analog targets), →librelane
fragments (density/effort/corners). Tests pin all three shapes plus
the fuel-migration shape (bounds mapping). sta/librelane absent on
this host: yosys+opensta SDC acceptance and end-to-end run_spice
legs stay BLOCKED-needs-host; unit legs pin the emitted text.
Note `docs/tool-outputs/canvas-compile.md`.
