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
