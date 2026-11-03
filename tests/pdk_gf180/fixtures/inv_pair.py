"""GF180 inverter-class proof fixture (lane-owned layout script).

Builds ``gf180_inv_pair``: a guardless NFET (W/L = 0.5/0.28 um) plus a
guardless PFET (W/L = 1.0/0.28 um) with single-metal1 routing (common
gate strap, common drain strap, VSS/VDD source stubs), explicit bulk
taps (p-tap to VSS, n-tap in hand-drawn nwell to VDD), and IN/OUT/VDD/
VSS electrical ports.

Upstream source: device geometry comes from the gdsfactory/gf180mcu
parametric cells ``gf180mcu.cells.nfet`` / ``gf180mcu.cells.pfet``
(Apache-2.0, https://github.com/gdsfactory/gf180mcu); the composition,
straps, taps, and nwell rect are lane-authored for this proof (see
fixtures/README.md). Guard rings are intentionally omitted
(``grw=0``): the closed ring metal cannot be crossed on one layer, so
a guarded inverter needs a metal2 hop the stand-in deck cannot
qualify; bulk ties are explicit taps instead.

Run: ``python inv_pair.py [out.gds]`` (needs gf180mcu importable).
"""

import sys

import gdsfactory as gf

from gf180mcu import PDK
from gf180mcu.cells import nfet, pfet
from gf180mcu.layers import LAYER

CELL_NAME = "gf180_inv_pair"
DY = 3.0  # PFET origin above NFET origin (um)
W_N_UM = 0.5
W_P_UM = 1.0
L_UM = 0.28


@gf.cell
def build_cell() -> gf.Component:
    """Build the inverter-class fixture component."""
    PDK.activate()
    c = gf.Component()
    n = c << nfet(l_gate=L_UM, w_gate=W_N_UM, nf=1, grw=0)
    n.move((0, 0))
    p = c << pfet(l_gate=L_UM, w_gate=W_P_UM, nf=1, grw=0)
    p.move((0, DY))
    m1 = LAYER.metal1

    def rect(x0, y0, x1, y1, layer):
        c.add_polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer=layer)

    # N-well over PMOS + n-tap (generous hand enclosure; recipe caveats).
    rect(-1.1, 1.7, 1.9, 4.3, LAYER.nwell)
    # Gate strap: NFET gate-top (0, 0.53) to PFET gate-bottom (0, 2.22).
    rect(-0.115, 0.42, 0.115, 2.33, m1)
    # Drain net: vertical + jogs onto both Drain_0 metals (x = -0.4).
    rect(-1.15, -0.15, -0.85, 3.15, m1)
    rect(-1.15, -0.15, -0.30, 0.15, m1)
    rect(-1.15, 2.85, -0.30, 3.15, m1)
    # Source stubs (VSS bottom, VDD top) onto Source_0 metals (x = 0.4).
    rect(0.30, -0.15, 1.50, 0.15, m1)
    rect(0.30, 2.85, 1.50, 3.15, m1)
    # P-tap (NFET bulk to VSS) at (1.6, 0).
    rect(1.35, -0.25, 1.85, 0.25, LAYER.comp)
    rect(1.23, -0.37, 1.97, 0.37, LAYER.pplus)
    rect(1.49, -0.11, 1.71, 0.11, LAYER.contact)
    rect(1.40, -0.20, 1.80, 0.20, m1)
    # N-tap (PFET bulk to VDD) at (1.6, 3.0), inside the n-well.
    rect(1.35, 2.75, 1.85, 3.25, LAYER.comp)
    rect(1.23, 2.63, 1.97, 3.37, LAYER.nplus)
    rect(1.49, 2.89, 1.71, 3.11, LAYER.contact)
    rect(1.40, 2.80, 1.80, 3.20, m1)
    c.add_port("IN", center=(0, 1.375), width=0.23, layer=m1,
               port_type="electrical")
    c.add_port("OUT", center=(-1.0, 1.5), width=0.3, layer=m1,
               port_type="electrical")
    c.add_port("VSS", center=(0.9, 0), width=0.3, layer=m1,
               port_type="electrical")
    c.add_port("VDD", center=(0.9, 3.0), width=0.3, layer=m1,
               port_type="electrical")
    return c


def main(argv):
    """Build the cell and write GDS (argv: optional output path)."""
    PDK.activate()
    c = build_cell()
    out = argv[1] if len(argv) > 1 else "gf180_inv_pair.gds"
    path = c.write_gds(out)
    bb = c.bbox()
    print(f"cell: {CELL_NAME}")
    print(f"gds: {path}")
    print(f"bbox_um: [[{bb.left:.2f}, {bb.bottom:.2f}], "
          f"[{bb.right:.2f}, {bb.top:.2f}]]")
    print(f"layers: {sorted(tuple(layer) for layer in c.layers)}")
    print(f"ports: {sorted(port.name for port in c.ports)}")
    return path


if __name__ == "__main__":
    main(sys.argv)
