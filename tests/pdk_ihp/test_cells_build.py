"""PDK-IHP RED — live cell builds: BiCMOS core + RF flavors + HBT.

Valid RED = profile missing (FileNotFoundError) or ihp/gdsfactory
unimportable (loud skip). GREEN builds one cell per flavor group
from the profile's cell lists and pins golden ports/bbox/polygons
captured from ihp-gdsfactory 2.0.1 + gdsfactory 9.51.0.
"""

import importlib.util

import pytest

from ._profile import load_profile

gf_present = importlib.util.find_spec("gdsfactory") is not None


def _ihp_cells_present():
    try:
        return importlib.util.find_spec("ihp.cells") is not None
    except (ImportError, AttributeError, ValueError):
        return False


ihp_present = _ihp_cells_present()
needs_live = pytest.mark.skipif(
    not (gf_present and ihp_present),
    reason="live build needs gdsfactory + ihp-gdsfactory==2.0.1",
)

# Goldens: (ports, bbox_um [[x0,y0],[x1,y1]], n_polygons).
GOLDENS = {
    "nmos": {
        "kwargs": {"width": 1.0, "length": 0.13, "nf": 4},
        "ports": ["D", "G", "S"],
        "bbox": [[0.0, -0.155], [2.58, 0.455]],
        "npolygons": 7,
    },
    "rfnmos": {
        "kwargs": {"width": 1.0, "length": 0.13, "nf": 1},
        "ports": ["D", "G", "S", "TIE"],
        "bbox": [[0.0, 0.0], [3.28, 3.32]],
        "npolygons": 8,
    },
    "npn13G2": {
        "kwargs": {},
        "ports": ["B", "C", "E"],
        "bbox": [[-3.35, -3.33], [3.35, 3.78]],
        "npolygons": 13,
    },
    "rsil": {
        "kwargs": {},
        "ports": ["P1", "P2"],
        "bbox": [[-0.18, -0.53], [0.68, 1.03]],
        "npolygons": 8,
    },
    "cmim": {
        "kwargs": {},
        "ports": ["MINUS", "PLUS"],
        "bbox": [[-3.96, -3.96], [3.96, 3.96]],
        "npolygons": 12,
    },
}


def _check_cell(factory, golden):
    cell = factory(**golden["kwargs"])
    assert sorted(p.name for p in cell.ports) == golden["ports"]
    box = cell.bbox()
    got = [[box.left, box.bottom], [box.right, box.top]]
    for row_got, row_exp in zip(got, golden["bbox"]):
        assert row_got == pytest.approx(row_exp, abs=1e-9)
    assert len(cell.get_polygons()) == golden["npolygons"]
    return cell


@needs_live
def test_bicmos_nmos_builds_to_golden():
    profile = load_profile()  # RED: missing profile.yaml
    assert "nmos" in profile["variants"]["bicmos"]["cells"]
    from ihp import PDK
    from ihp.cells import nmos

    PDK.activate()
    cell = _check_cell(nmos, GOLDENS["nmos"])
    assert cell.name.startswith("nmos_")


@needs_live
def test_rf_rfnmos_builds_to_golden():
    profile = load_profile()  # RED: missing profile.yaml
    assert "rfnmos" in profile["variants"]["rf"]["cells"]
    from ihp import PDK
    from ihp.cells import rfnmos

    PDK.activate()
    cell = _check_cell(rfnmos, GOLDENS["rfnmos"])
    assert cell.name.startswith("rfnmos_")


@needs_live
def test_bicmos_hbt_builds_to_golden():
    profile = load_profile()  # RED: missing profile.yaml
    assert "npn13G2" in profile["variants"]["bicmos"]["cells"]
    from ihp import PDK
    from ihp.cells import npn13G2

    PDK.activate()
    cell = _check_cell(npn13G2, GOLDENS["npn13G2"])
    assert cell.name.startswith("npn13G2_")


@needs_live
def test_bicmos_passives_build_to_golden():
    profile = load_profile()  # RED: missing profile.yaml
    assert "rsil" in profile["variants"]["bicmos"]["cells"]
    assert "cmim" in profile["variants"]["bicmos"]["cells"]
    from ihp import PDK
    from ihp.cells import cmim, rsil

    PDK.activate()
    _check_cell(rsil, GOLDENS["rsil"])
    _check_cell(cmim, GOLDENS["cmim"])


@needs_live
def test_stdcell_imports_with_ports():
    profile = load_profile()  # RED: missing profile.yaml
    assert "sg13g2_buf_1" in profile["variants"]["bicmos"]["cells"]
    from ihp import PDK
    from ihp.cells import sg13g2_buf_1

    PDK.activate()
    cell = sg13g2_buf_1()
    ports = sorted(p.name for p in cell.ports)
    assert ports, "stdcell imports with zero ports"
    assert len(cell.get_polygons()) > 0
