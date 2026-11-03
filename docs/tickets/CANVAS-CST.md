# CANVAS-CST: canvas.toml design intent, authored HDL and tool settings

*Status: Ready · Depends: none · Size: M ·
Roadmap: design intent (MVP track)*

## Why

Every lane needs stated design intent (clock, power,
gain, loss...) and today it lives nowhere
engine-side: fuel carries `constraints.yaml` checks
for the agent, tools take CLI args, and synthesis
flows take their own configs. The project canvas
needs one editable `canvas.toml` — human-writable,
agent-writable, UI-rendered, engine-consumed —
stating what the design must achieve across D/A/P.
It builds on PDK data (liberty, models, decks),
never regurgitates it. The agent loop becomes
{prompt + canvas.toml + PDK + tools}, all
client-agnostic.

## What

- `canvas.toml` in the project canvas: design
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
  engine ships a `canvas.toml` template per
  supported PDK (sane targets + knobs for that
  node), and project creation runs the generator
  (PDK → template → filled canvas.toml). This is
  the backend the project-creation wizard calls.
- Engine COMPILES it to tool-native forms —
  SDC for yosys/opensta/librelane, measure/corner
  decks for ngspice, config fragments for
  librelane — single source, adapters translate.
- Run targets (run_spice bounds today from
  fuel constraints.yaml) migrate to canvas.toml
  as the single source; fuel reads the same file
  (iteration config stays fuel-side).
- Validation: unknown metrics/knobs rejected,
  units checked, PDK revision pinned, refs
  contained; drift-safe like every project doc.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- A digital canvas.toml compiles to SDC that
  yosys+opensta accept; an analog one drives
  run_spice bounds end to end (tests pin both).
- Per-PDK generator output validates clean for
  every supported PDK; wizard path creates a
  project with a filled canvas.toml (tests pin).
- Path refs resolve + hash into run closure; a
  moved/edited ref re-verifies or fails loud,
  never silent.
- Fuel's opamp checks expressible 1:1 in
  canvas.toml (migration probe, no silent drops).
- UI can render + edit every section from the
  schema alone (schema-tested).

## V1 amendment — 2026-11-01

Ticket ID is retained for links; the new filename is **canvas.toml**. Use the
canonical v1 CanvasConfig schema and generated consumer types under ADR-014.
Add `[hdl].language` selecting one authored Verilog/SystemVerilog/VHDL/qualified
Amaranth dialect per canvas. Generated backend Verilog does not count as mixing;
foreign authored source requires explicit migration/interoperability qualification.
Inline registered tool knobs remain supported; optional contained delegated files
validate against the same tool schema. Duplicate inline/delegated values are an
error; defaults and explicit run overrides are resolved with provenance under I28.

Implement explicit atomic legacy canvas.cst -> canvas.toml migration; reject
conflicting active copies. Old run ingredients/snapshots retain the original
bytes and are not rewritten. Pin source/model/tool/port-map/testbench/technology
closure along with this file. Source/geometry stay outside TOML as managed assets.
Test selected language migration, generated backend HDL, conflicting filenames,
inline/delegated knob validation, contained refs and historical ingredient reads.

## Verdict (Wave-2, 2026-11-03) — Ready, to Wave-3 lanes

CANVAS-CST-CORE delivered the foundation (schema tables, validate,
closure, loader, UI descriptor — Done). Remain: canvas integration
into project/submit/I28 paths + per-PDK templates (Wave-3 lanes
ticket) + SDC/deck compiler (CANVAS-CST-COMPILE, Wave-4 terminal).

## Verdict (adapt lane, 2026-11-03) — integration + templates Done

`src/project/canvas/integrate.py` (wizard_create, canvas_run_closure,
validate_submit_canvas) plus `templates.py` (generate for 9 lanes,
all validate clean) land the Wave-3 lanes slice. Tests
`tests/test_canvas_compile.py` pin generator-per-PDK validation and
the wizard path (RED 6 failed, GREEN 75 passed / 2 skipped across
the lane). Composition/submit call-site wiring stays with the
owning surface (seam recorded, not touched here). Fuel 1:1 probe
and UI schema rendering remain open.
