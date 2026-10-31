"""Generate the ASAP7 KLayout tech files from PDK layer data.

Stdlib-only: embeds the drawing-layer table transcribed from the r1p7
PDK layermap (cdslib/asap7_TechLib_10/asap7_TechLib.layermap) and emits
asap7.lyt (technology; element schema mirrored from KLayout 0.28.16's
own Technology.save() output) plus asap7.lyp (display names, stream
numbers, and our own color assignment). Deterministic: no timestamps,
fixed layer order, so regeneration is byte-identical.

Usage: python3 gen_tech.py <outdir>  (also importable: main(outdir)).
"""

import os
import sys
import xml.etree.ElementTree as ET

# (name, stream number) transcribed from the r1p7 layermap, drawing
# purpose, datatype 0. Pad has no drawing stream in the layermap (DRM
# mask 96 unmapped), so it is absent here as well.
DRAWING_LAYERS = [
    {"name": "WELL", "stream": 1},
    {"name": "FIN", "stream": 2},
    {"name": "Gate", "stream": 7},
    {"name": "Dummy", "stream": 8},
    {"name": "GCut", "stream": 10},
    {"name": "Active", "stream": 11},
    {"name": "Nselect", "stream": 12},
    {"name": "Pselect", "stream": 13},
    {"name": "LIG", "stream": 16},
    {"name": "LISD", "stream": 17},
    {"name": "V0", "stream": 18},
    {"name": "M1", "stream": 19},
    {"name": "M2", "stream": 20},
    {"name": "V1", "stream": 21},
    {"name": "V2", "stream": 25},
    {"name": "M3", "stream": 30},
    {"name": "V3", "stream": 35},
    {"name": "M4", "stream": 40},
    {"name": "V4", "stream": 45},
    {"name": "M5", "stream": 50},
    {"name": "V5", "stream": 55},
    {"name": "M6", "stream": 60},
    {"name": "V6", "stream": 65},
    {"name": "M7", "stream": 70},
    {"name": "V7", "stream": 75},
    {"name": "M8", "stream": 80},
    {"name": "V8", "stream": 85},
    {"name": "SDT", "stream": 88},
    {"name": "M9", "stream": 90},
    {"name": "V9", "stream": 95},
    {"name": "SLVT", "stream": 97},
    {"name": "LVT", "stream": 98},
    {"name": "SRAMDRC", "stream": 99},
    {"name": "BOUNDARY", "stream": 100},
    {"name": "SRAMVT", "stream": 110},
]

# Our own display palette, cycled in table order (descending luminance
# pairs keep neighbors distinguishable; metals warm, vias cool).
PALETTE = [
    "#b03030", "#3060b0", "#30a030", "#b0b030", "#a030a0", "#30a0a0",
    "#d07020", "#7060d0", "#60a040", "#c04070", "#4080c0", "#80b040",
]

TECH_NAME = "ASAP7"
TECH_DESC = ("ASAP7 r1p7 predictive PDK: layer names/stream numbers "
             "transcribed from the PDK layermap (lane ASAP7-DRC-DECK).")
TECH_DBU_UM = 0.00025  # measured PDK GDS dbu (INVx1 fixture cell)
LYP_NAME = "asap7.lyp"


def _indent(elem, level=0):
    pad = "\n" + " " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + " "
        for child in elem:
            _indent(child, level + 1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = pad
    elif level and (not elem.tail or not elem.tail.strip()):
        elem.tail = pad


def build_lyt():
    root = ET.Element("technology")
    ET.SubElement(root, "name").text = TECH_NAME
    ET.SubElement(root, "description").text = TECH_DESC
    ET.SubElement(root, "group")
    ET.SubElement(root, "dbu").text = repr(TECH_DBU_UM)
    ET.SubElement(root, "base-path")
    ET.SubElement(root, "original-base-path")
    ET.SubElement(root, "layer-properties_file").text = LYP_NAME
    ET.SubElement(root, "add-other-layers").text = "true"
    ET.SubElement(root, "connectivity")
    _indent(root)
    return ET.ElementTree(root)


def build_lyp():
    root = ET.Element("layer-properties")
    for idx, layer in enumerate(DRAWING_LAYERS):
        color = PALETTE[idx % len(PALETTE)]
        props = ET.SubElement(root, "properties")
        ET.SubElement(props, "frame-color").text = color
        ET.SubElement(props, "fill-color").text = color
        ET.SubElement(props, "frame-brightness").text = "0"
        ET.SubElement(props, "fill-brightness").text = "0"
        ET.SubElement(props, "valid").text = "true"
        ET.SubElement(props, "visible").text = "true"
        ET.SubElement(props, "transparent").text = "false"
        ET.SubElement(props, "width").text = "1"
        ET.SubElement(props, "marked").text = "false"
        ET.SubElement(props, "animation").text = "0"
        ET.SubElement(props, "name").text = f"{layer['name']} - drawing"
        ET.SubElement(props, "source").text = f"{layer['stream']}/0@1"
    _indent(root)
    return ET.ElementTree(root)


def _write(tree, path):
    tree.write(path, encoding="utf-8", xml_declaration=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n")


def main(outdir):
    """Emit asap7.lyt + asap7.lyp into outdir (created if missing)."""
    os.makedirs(outdir, exist_ok=True)
    _write(build_lyt(), os.path.join(outdir, "asap7.lyt"))
    _write(build_lyp(), os.path.join(outdir, "asap7.lyp"))
    print("WROTE " + os.path.join(outdir, "asap7.lyt"))
    print("WROTE " + os.path.join(outdir, "asap7.lyp"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
