# KLayout batch DRC probe (DRC-GREEN input, 2026-10-28)

Second-opinion DRC path beside Magic. Tool: KLayout 0.28.16,
`klayout -b -r script.py` with the pya API. No GUI, no extra deps.

## Negative result: Ruby DRC DSL does not run under `-r`

- `klayout -b -r deck.rb` executes plain Ruby: `source`/`report`/`input`
  raise `NoMethodError`.
- Renaming to `.lydrc` fails differently: the runner expects XML macro
  format (`XML parser error ... line 1, column 1`).

sky130A Ruby decks will need a DRC driver macro or a GUI-run recipe.
That is PROV/B10 scope, not this probe. The probe below uses pya
geometry checks instead — the same engine the DSL calls.

## Verified protocol: pya width/space checks

Cells on layer 1/0, dbu 0.001 (units below are dbu; 3000 = 3um):

| Cell | Geometry | width>=3um | space>=3um |
|---|---|---|---|
| good | 3um wires, 3um gap | 0 | 0 |
| bad_space | 3um wires, 1um gap | 0 | 1 @ (3000,0;4000,3000) |
| bad_width | 1um wire | 1 @ (0,0;1000,5000) | 0 |

Script shape: `pya.Region(top.begin_shapes_rec(layer))`, then
`region.width_check(3000)` / `region.space_check(3000)`; each
violation yields `pair.bbox()`. Exit code is 0 regardless — parse
counts, never trust the exit.

## Adapter sketch (next: KLayoutDrcAdapter RED)

- `preflight`: klayout on PATH, GDS readable, rules sane.
- `execute`: render the check script from the rule table (layer,
  width/space values), run `klayout -b -r`, capture stdout.
- `parse`: per-rule counts + bboxes into
  `violations[] {rule, bbox_um, area?}`.
- Fixtures: `tests/adapters/fixtures/drc_kl/{good,bad_space,
  bad_width}.gds` (tiny binaries) plus the generator script for
  provenance, mirroring the Magic `.mag` fixtures.
- Skip guard: tests skip where klayout is absent, same as Magic.
