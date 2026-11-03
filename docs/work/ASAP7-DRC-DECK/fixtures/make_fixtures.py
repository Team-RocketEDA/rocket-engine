"""Generate ASAP7-DRC-DECK GDS fixtures. Run: klayout -b -r make_fixtures.py

Reads fixtures/spec.json (SPEC_PATH env or alongside this script) and
writes one <id>.gds per breaker/clean entry into OUT_DIR env (default
./generated). Layer keys map to PDK stream numbers transcribed from
the r1p7 layermap (see inventory.md sourcing note). Boxes and polygon
vertices are in nm; layout dbu is 0.25nm per the spec.
"""

import json
import os
import sys

import pya

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.environ.get("SPEC_PATH", os.path.join(HERE, "spec.json"))
OUT_DIR = os.environ.get("OUT_DIR", os.path.join(HERE, "generated"))

# Stream numbers transcribed from the r1p7 PDK layermap
# (cdslib/asap7_TechLib_10/asap7_TechLib.layermap, drawing purpose).
LAYERS = {
    "WELL": (1, 0), "FIN": (2, 0), "GATE": (7, 0), "DUMMY": (8, 0),
    "GCUT": (10, 0), "ACTIVE": (11, 0), "NSELECT": (12, 0),
    "PSELECT": (13, 0), "LIG": (16, 0), "LISD": (17, 0), "V0": (18, 0),
    "M1": (19, 0), "M2": (20, 0), "V1": (21, 0), "V2": (25, 0),
    "M3": (30, 0), "V3": (35, 0), "M4": (40, 0), "V4": (45, 0),
    "M5": (50, 0), "V5": (55, 0), "M6": (60, 0), "V6": (65, 0),
    "M7": (70, 0), "V7": (75, 0), "M8": (80, 0), "V8": (85, 0),
    "SDT": (88, 0), "M9": (90, 0), "V9": (95, 0), "SLVT": (97, 0),
    "LVT": (98, 0), "SRAMDRC": (99, 0), "BOUNDARY": (100, 0),
    "SRAMVT": (110, 0),
}


def _to_dbu(nm, scale):
    return int(round(nm * scale))


def main():
    with open(SPEC_PATH) as fh:
        spec = json.load(fh)
    dbu_um = spec["dbu_um"]
    scale = 0.001 / dbu_um  # nm per dbu
    os.makedirs(OUT_DIR, exist_ok=True)
    entries = spec["breakers"] + spec["cleans"]
    for entry in entries:
        layout = pya.Layout()
        layout.dbu = dbu_um
        top = layout.create_cell("TOP")
        for key, boxes in entry.get("shapes", {}).items():
            layer = layout.layer(*LAYERS[key])
            for x0, y0, x1, y1 in boxes:
                top.shapes(layer).insert(pya.Box(
                    _to_dbu(x0, scale), _to_dbu(y0, scale),
                    _to_dbu(x1, scale), _to_dbu(y1, scale)))
        for key, polys in entry.get("polygons", {}).items():
            layer = layout.layer(*LAYERS[key])
            for pts in polys:
                top.shapes(layer).insert(pya.Polygon(
                    [pya.Point(_to_dbu(x, scale), _to_dbu(y, scale))
                     for x, y in pts]))
        path = os.path.join(OUT_DIR, entry["id"] + ".gds")
        layout.write(path)
        print("WROTE " + path)


main()
