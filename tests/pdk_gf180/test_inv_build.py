"""PDK-GF180 RED — lane proof: inverter build with golden expectations.

Valid RED = the lane profile does not exist yet, so the proof
fails on FileNotFoundError before touching any solver. GREEN
builds the profile's proof cell and pins the goldens: gf180mcu
active, IN/OUT/VDD/VSS ports, the 7-layer CMOS stack, the
reference bbox, and deterministic rebuild (same geometry twice —
GDS bytes are NOT golden: timestamps/cell order differ across
gdsfactory versions). Skips LOUDLY (never fake-green) where the
PDK is absent.
"""

from . _profile import load_profile, require_pdk


def test_lane_inv_build_matches_goldens(tmp_path):
    profile = load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    from .fixtures.inv_pair import build_cell

    from gf180mcu import PDK

    proof = profile["proofs"]["layout"]
    PDK.activate()
    assert PDK.name == "gf180mcu"
    cell = build_cell()
    assert sorted(port.name for port in cell.ports) == proof["ports"]
    assert sorted(tuple(layer) for layer in cell.layers) == [
        tuple(layer) for layer in proof["layers"]
    ]
    bbox = cell.bbox()
    assert round(bbox.left, 2) == proof["bbox_um"][0][0]
    assert round(bbox.bottom, 2) == proof["bbox_um"][0][1]
    assert round(bbox.right, 2) == proof["bbox_um"][1][0]
    assert round(bbox.top, 2) == proof["bbox_um"][1][1]
    assert round(cell.xsize, 2) == proof["xsize_um"]
    assert round(cell.ysize, 2) == proof["ysize_um"]
    out = cell.write_gds(str(tmp_path / "lane_inv.gds"))
    assert str(out).endswith("lane_inv.gds")


def test_lane_inv_rebuild_is_deterministic():
    profile = load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    from .fixtures.inv_pair import build_cell

    first, second = build_cell(), build_cell()
    for cell in (first, second):
        bbox = cell.bbox()
        assert (round(bbox.left, 2), round(bbox.bottom, 2)) == (-1.15, -0.71)
        assert (round(bbox.right, 2), round(bbox.top, 2)) == (1.97, 4.3)
    assert profile["proofs"]["layout"]["cell"] == "gf180_inv_pair"
