"""PDK-CSPDK lane proof: si340 MZI build with golden expectations (RED-first).

RED = the lane profile/fixture are missing, so the build fails before
any solver runs. GREEN = cspdk.si340 builds its default MZI with the
pinned ports, polygon count, and bbox, and a GDS write/read roundtrip
preserves the layout on GDS 3/0. Skips LOUDLY (never fake-green)
where gdsfactory/cspdk are uninstalled.
"""

import importlib.util

import pytest

from ._profile import FIXTURES, ensure_cspdk, load_profile

gf_present = importlib.util.find_spec("gdsfactory") is not None
needs_gf = pytest.mark.skipif(
    not gf_present, reason="gdsfactory not installed (uv sync --group layout)"
)

MZI_PORTS = ["o1", "o2", "o3"]
MZI_N_POLYGONS = 16
MZI_BBOX_UM = [[-20.0, -27.8], [181.3, 22.8]]


def _build_mzi():
    load_profile()  # RED gate: the lane profile owns this proof.
    cspdk = ensure_cspdk()
    from cspdk.si340 import PDK, cells

    PDK.activate()
    return cspdk, PDK, cells.mzi()


@needs_gf
def test_si340_mzi_builds_with_golden_ports():
    _, PDK, mzi = _build_mzi()
    assert PDK.name == "cornerstone_si340"
    assert sorted(p.name for p in mzi.ports) == MZI_PORTS


@needs_gf
def test_si340_mzi_builds_with_golden_geometry():
    _, _, mzi = _build_mzi()
    n_polygons = sum(len(polys) for polys in mzi.get_polygons().values())
    assert n_polygons == MZI_N_POLYGONS
    box = mzi.bbox()
    bbox = [float(box.left), float(box.bottom), float(box.right), float(box.top)]
    assert bbox == pytest.approx([-20.0, -27.8, 181.3, 22.8])


@needs_gf
def test_si340_mzi_gds_roundtrip_preserves_layout(tmp_path):
    pytest.importorskip("klayout.db")
    _, _, mzi = _build_mzi()
    gds = tmp_path / "mzi_built.gds"
    mzi.write(str(gds))
    assert gds.is_file()

    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(gds))
    top = layout.top_cell()
    layer = layout.layer(3, 0)
    shapes = list(top.begin_shapes_rec(layer))
    assert len(shapes) == MZI_N_POLYGONS
    assert top.name.startswith("mzi_")


def test_lane_reference_fixture_matches_upstream():
    load_profile()  # RED gate.
    ref = FIXTURES / "mzi_ref.gds"
    assert ref.is_file(), f"lane fixture missing: {ref}"
    provenance = (FIXTURES / "SOURCE.md").read_text()
    assert "3323b17" in provenance
    assert "MIT" in provenance
