"""Generate the drc_kl GDS fixtures. Run: klayout -b -r make_cells.py

Layer 1/0 is M1, dbu 0.001 (3000 dbu = 3um). Rules assumed by the
tests: width >= 3um, space >= 3um.
"""

import pya

CELLS = {
    "good": [(0, 0, 3000, 3000), (6000, 0, 9000, 3000)],
    "bad_space": [(0, 0, 3000, 3000), (4000, 0, 7000, 3000)],
    "bad_width": [(0, 0, 1000, 5000)],
}

for name, boxes in CELLS.items():
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    layer = layout.layer(1, 0)
    for x0, y0, x1, y1 in boxes:
        top.shapes(layer).insert(pya.Box(x0, y0, x1, y1))
    layout.write(f"{name}.gds")
    print(f"WROTE {name}.gds")
