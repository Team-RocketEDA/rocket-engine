"""ASAP7-DRC-DECK: tech files generated from PDK layer data (no klayout).

gen_tech.py embeds the drawing-layer table transcribed from the PDK
layermap and emits asap7.lyt (technology, schema mirrored from
KLayout 0.28.16's own Technology.save() output) plus asap7.lyp
(layer names + stream numbers for display). These tests pin
well-formedness, layer coverage, and byte-identical regeneration.
RED signal: the lane tech files are missing, so everything fails
on FileNotFoundError until they land.
"""

import importlib.util
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LANE = REPO_ROOT / "docs" / "work" / "ASAP7-DRC-DECK"
GEN_TECH = LANE / "tech" / "gen_tech.py"
LYT = LANE / "tech" / "asap7.lyt"
LYP = LANE / "tech" / "asap7.lyp"


def _load_gen():
    if not GEN_TECH.is_file():
        raise FileNotFoundError(f"tech generator not found: {GEN_TECH}.")
    spec = importlib.util.spec_from_file_location("asap7_gen_tech", GEN_TECH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tech_files_present_and_wellformed():
    for path in (GEN_TECH, LYT, LYP):
        assert path.is_file(), f"lane tech file missing: {path}"
    ET.parse(str(LYT))
    ET.parse(str(LYP))


def test_lyt_names_technology_and_points_at_lyp():
    root = ET.parse(str(LYT)).getroot()
    assert root.tag == "technology"
    assert (root.findtext("name") or "") == "ASAP7"
    assert (root.findtext("layer-properties_file") or "") == "asap7.lyp"
    assert (root.findtext("description") or "").strip() != ""


def test_lyp_covers_every_drawing_layer():
    gen = _load_gen()
    root = ET.parse(str(LYP)).getroot()
    assert root.tag == "layer-properties"
    have = set()
    for props in root.findall("properties"):
        name = (props.findtext("name") or "").strip()
        source = (props.findtext("source") or "").strip()
        assert name and source
        have.add((name, source.split("@")[0]))
    for layer in gen.DRAWING_LAYERS:
        key = (f"{layer['name']} - drawing", f"{layer['stream']}/0")
        assert key in have, f"lyp missing drawing layer: {key}"


def test_tech_regen_is_byte_identical(tmp_path):
    gen = _load_gen()
    assert hasattr(gen, "main"), "gen_tech.py must expose main(outdir)"
    gen.main(str(tmp_path))
    for name in ("asap7.lyt", "asap7.lyp"):
        assert (tmp_path / name).read_bytes() == (LANE / "tech" / name).read_bytes()


def test_gen_runs_as_script(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(GEN_TECH), str(tmp_path)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "asap7.lyt").is_file()
    assert (tmp_path / "asap7.lyp").is_file()
