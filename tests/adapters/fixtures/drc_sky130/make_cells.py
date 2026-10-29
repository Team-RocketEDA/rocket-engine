"""Generate the drc_sky130 GDS fixtures. Run: klayout -b -r make_cells.py

Sky130 met1 is 68/20, dbu 0.001 (140 dbu = 0.14um). Rules from
sky130A.lydrc (verified vs KLayout 0.28.16 + sky130A deck):
- m1.1: min m1 width 0.14um
- Good: 0.5um square -> 0 violations (clean)
- Bad: 0.05um x 2um wire -> 1x m1.1 (min-width violation)

Provenance: hand-built minimal. Fixture mining explored first:
bandgap trivial_mos_array.gds (4.9K) verified clean (0 violations)
against the real deck, and sigma-delta GDS (2.8M) shows 10x m4.5ab,
but *.gds is git-ignored so committed fixtures follow the drc_kl
pattern (generator only, binaries local). The mined good is cited
here; the suite uses these minimal cells for speed and isolation.
"""

import pya

CELLS = {
    # name -> list of (x0, y0, x1, y1) in dbu on 68/20
    "good": [(0, 0, 500, 500)],
    "bad": [(0, 0, 50, 2000)],
}

for name, boxes in CELLS.items():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    layer = layout.layer(68, 20)
    for x0, y0, x1, y1 in boxes:
        top.shapes(layer).insert(pya.Box(x0, y0, x1, y1))
    layout.write(f"{name}.gds")
    print(f"WROTE {name}.gds")
