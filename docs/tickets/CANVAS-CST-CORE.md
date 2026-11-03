# CANVAS-CST-CORE: canvas.toml schema, validation, project integration

*Status: Ready · Depends: none · Size: M · Roadmap: design intent (MVP track) · Parent: CANVAS-CST (Step 6a)*

## Why

Every lane needs stated design intent (clock, power, gain, loss) and today it
lives nowhere engine-side: fuel carries `constraints.yaml` checks for the
agent, tools take CLI args, synthesis flows take their own configs. The
project canvas needs one editable `canvas.toml` — human-writable,
agent-writable, UI-rendered, engine-consumed — stating what the design must
achieve across D/A/P/M. It builds on PDK data (liberty, models, decks), never
regurgitates it. The agent loop becomes {prompt + canvas.toml + PDK + tools},
all client-agnostic.

This slice lays the foundation without the compiler: the file exists, it is
versioned and closure-hashed, and anything violating it fails loudly naming
the rule. The compiler (SDC/decks) and templates come next in
CANVAS-CST-COMPILE; without this slice they would have nothing stable to
compile from.

## What

- `canvas.toml` at the project canvas root: `[meta]` (pdk + revision pin),
  `[targets.*]` (clocks, area, power, analog specs, photonic targets, mixed
  bindings), `[tools.<tool>]` (per-tool knobs), path refs for delegated
  content (`drc_deck = "./decks/m1_minimal.py"`, tcl, SDC snippets).
- Versioned, non-gitignored, hashed into the I28 run closure; refs resolve
  contained in the project and drift-check like every project doc.
- Validation on submit and at creation: unknown metrics/knobs rejected, units
  checked, PDK revision pinned.

## Acceptance

- Constraint violations fail loudly naming the rule and section (tests pin).
- Path refs resolve + hash into the run closure; a moved/edited ref
  re-verifies or fails loud, never silent.
- UI can render + edit every section from the schema alone (schema-tested).
- Contract + api_spec regen if surfaces change; suite green.

## Delivery verdict (2026-11-02)

DELIVERED (TDD RED→GREEN, 13 new tests in
`tests/test_canvas_core.py`; both shipped demo canvases validate:
`waveform-generator/canvas.toml` full, `photonic_matmul/
canvas.toml` photonic-only).

- New module `src/project/canvas/` (`schema.py` tables +
  `CANVAS_SCHEMA` UI descriptor, `validate.py` load/validate/
  closure/emission): schema pin, one-dialect `hdl`, PDK revision
  pins, known-metrics/units/operator checks, per-tool knob
  schemas with `duplicate_configuration` refusal, contained
  refs hashed into a content-addressed closure, conflicting
  `canvas.cst` rejected, `dump_canvas_toml` for the creation
  wizard (round-trip tested).
- Metric/unit tables are evidence-backed (demo canvases + fuel
  flat names `dc_gain_db`/`ugbw_mhz`/`phase_margin_deg` for the
  1:1 migration); new names register as table edits, never
  silent accepts.
- No contract/api_spec regen: validation mirrors the frozen
  `contracts/v1/schemas/canvas.schema.json`; no Engine surface
  changed.

Judgment calls (documented in code): empty `[technology]`/`[hdl]`
tables read as absent (commented placeholders carry no claim);
the `[meta]` section from early prose is superseded by the
frozen contract (`technology`/`pdks` pin revisions, unknown
top-level sections rejected); Amaranth profile qualification
stays COMPILE scope (the frozen `hdl` shape has no profile slot).

Seam for adapt lane: wire `load_project_canvas`/
`validate_canvas`/`canvas_closure` into project creation +
submit validation + the I28 run closure (project service and
composition are out of owned set). BLOCKED-needs-host: none —
this slice is pure Python (tomllib + stdlib); SDC/yosys/ngspice
acceptance belongs to CANVAS-CST-COMPILE.
