# canvas compile — SDC, spice bounds, librelane fragments

Context: CANVAS-CST-COMPILE. The compiler is single-source: the
canvas never regurgitates PDK data; adapters translate. Code
`src/project/canvas/compile.py` (compiler),
`src/project/canvas/templates.py` (per-PDK generator),
`src/project/canvas/integrate.py` (wizard/project/submit/I28).

## Report inventory

- `compile_sdc(doc)`: digital canvas clock target (MHz) to SDC
  with `create_clock -period <1000/MHz>`, uncertainty, and
  input/output delays (yosys+opensta accept the shape).
- `compile_spice_bounds(doc)`: analog targets to run_spice
  `{metric: {min?, max?}}` bounds (ge/gt/eq → min, le/lt/eq →
  max; clocks excluded).
- `compile_librelane(doc)`: density/effort/corners fragment.
- `generate(pdk_id)` plus `wizard_create(root, pdk_id)`: filled
  canvas.toml per supported PDK (9 lanes) that validates clean;
  `canvas_run_closure` / `validate_submit_canvas` wire I28 and
  submit.

## Exit states

- No clock target: `bad_target`; non-positive limit:
  `bad_limit`.
- Unknown PDK: ValueError (never a silent default).
- sta/librelane absent on this host: live acceptance legs stay
  BLOCKED-needs-host; unit legs pin the emitted shapes.
