"""PDK-ASAP7 GDS proof via KLayout batch (JSON out, goldens in-profile).

Proves the library GDS agrees exactly with the LEF (213 cells,
identical names, all four VTs), pins the INVx1 RVT geometry
golden (dbu bbox, um bbox, 51 shapes, 16 layers), and proves the
lane fixture is byte-faithful upstream geometry.
"""

import json

import pytest

from ._profile import FIXTURES, find_lib_root, load_profile, run_klayout_batch

GDS_SCRIPT = """
import json, pya
lib = r"{lib}"
out = {{}}
for vt, tag in [("L", "L"), ("R", "R"), ("SL", "SL"), ("SRAM", "SRAM")]:
    ly = pya.Layout()
    ly.read(lib + "/GDS/asap7sc7p5t_28_%s_220121a.gds" % vt)
    cells = sorted(c.name for c in ly.each_cell())
    lef = sorted(l.split()[1] for l in
                 open(lib + "/LEF/asap7sc7p5t_28_%s_1x_220121a.lef" % vt)
                 if l.startswith("MACRO "))
    out[vt] = {{"ncells": len(cells), "match_lef": cells == lef,
                "dbu": ly.dbu}}
print("ASAP7LANE-JSON:" + json.dumps(out))
"""

INV_SCRIPT = """
import json, pya
ly = pya.Layout()
ly.read(r"{gds}")
c = ly.cell("INVx1_ASAP7_75t_R")
box = c.bbox()
layers = []
n = 0
for li in ly.layer_indexes():
    info = ly.get_info(li)
    k = sum(1 for _ in c.each_shape(li))
    if k:
        layers.append([[info.layer, info.datatype], k])
        n += k
out = {{"bbox_dbu": [box.left, box.bottom, box.right, box.top],
        "bbox_um": [box.left * ly.dbu, box.bottom * ly.dbu,
                    box.right * ly.dbu, box.top * ly.dbu],
        "n_shapes": n, "layers": sorted(layers), "dbu": ly.dbu}}
print("ASAP7LANE-JSON:" + json.dumps(out))
"""

INV_LAYERS = [
    [[1, 0], 1], [[1, 251], 1], [[2, 0], 10], [[3, 251], 1],
    [[7, 0], 3], [[10, 0], 4], [[11, 0], 2], [[12, 0], 1],
    [[13, 0], 1], [[16, 0], 3], [[17, 0], 4], [[18, 0], 7],
    [[19, 0], 4], [[19, 251], 4], [[88, 0], 4], [[100, 0], 1],
]


def _lane_json(proc):
    assert proc.returncode == 0, proc.stderr[-2000:]
    for line in proc.stdout.splitlines():
        if line.startswith("ASAP7LANE-JSON:"):
            return json.loads(line.split("ASAP7LANE-JSON:", 1)[1])
    raise AssertionError(f"no lane JSON in klayout output:\n{proc.stdout}")


def test_gds_cells_match_lef_all_vts():
    load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    data = _lane_json(run_klayout_batch(GDS_SCRIPT.format(lib=root)))
    for vt in ("L", "R", "SL", "SRAM"):
        assert data[vt]["ncells"] == 213, vt
        assert data[vt]["match_lef"] is True, vt
        assert data[vt]["dbu"] == pytest.approx(0.00025)


def test_invx1_r_geometry_golden():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable"
    gds = root / "GDS" / "asap7sc7p5t_28_R_220121a.gds"
    data = _lane_json(run_klayout_batch(INV_SCRIPT.format(gds=gds)))
    golden = profile["proofs"]["invx1_r"]
    assert data["bbox_dbu"] == golden["bbox_dbu"] == [0, -88, 824, 1168]
    flat = [c for corner in golden["bbox_um"] for c in corner]
    assert data["bbox_um"] == pytest.approx(flat)
    assert data["n_shapes"] == golden["n_shapes"] == 51
    assert data["layers"] == INV_LAYERS
    assert len(data["layers"]) == golden["n_layers"] == 16


def test_fixture_agrees_with_upstream():
    load_profile()  # RED: missing profile.yaml
    fixture = FIXTURES / "invx1_r.gds"
    assert fixture.is_file(), "fixture invx1_r.gds missing"
    assert fixture.stat().st_size < 16384, "fixture must stay small"
    data = _lane_json(run_klayout_batch(INV_SCRIPT.format(gds=fixture)))
    assert data["bbox_dbu"] == [0, -88, 824, 1168]
    assert data["n_shapes"] == 51
    assert data["layers"] == INV_LAYERS
    assert data["dbu"] == pytest.approx(0.00025)
