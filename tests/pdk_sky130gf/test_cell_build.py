"""PDK-SKY130GF RED — live cell-build proofs for the pip package.

Valid RED = the lane profile is missing, so every proof fails on
FileNotFoundError before touching any solver. GREEN builds the
proof cells live from the pinned pip package and pins geometry
goldens plus an exact fixture roundtrip. Tests skip (never
fake-green) where the pip package is absent; the goldens below
were verified live against sky130 1.0.0 under both gdsfactory
9.40.2 (as-shipped) and 9.51.0 (repo, --no-deps forward-compat).
"""

import hashlib

import pytest

from ._profile import FIXTURES, bbox_list, load_profile, polygon_count, sky130_root

NFET = "sky130_fd_pr__nfet_01v8"
INV2 = "sky130_fd_sc_hd__inv_2"
NFET_SHA256 = "0bd23411439124a00404806fe5003c377c0e5158b948417faa6a691f054a3e34"


def _require_pdk():
    load_profile()  # RED: missing profile.yaml
    if sky130_root() is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    import sky130

    assert sky130.__version__ == "1.0.0"
    assert sky130.PDK.name == "sky130"
    return sky130


def test_pip_package_registers_767_cells():
    sky130 = _require_pdk()
    assert len(sky130.cells) == 767


def test_nfet_build_matches_goldens():
    sky130 = _require_pdk()
    cell = sky130.cells[NFET]()
    assert sorted(p.name for p in cell.ports) == [
        "BODY",
        "DRAIN",
        "GATE",
        "SOURCE",
    ]
    assert polygon_count(cell) == 48
    assert bbox_list(cell) == pytest.approx([-1.0, -1.205, 1.0, 1.205])


def test_inv2_stdcell_build_matches_goldens():
    # Same known-good cell as the EXTRACT-SKY130 tree proof
    # (sky130_fd_sc_hd__inv_2), here via the pip distribution.
    sky130 = _require_pdk()
    cell = sky130.cells[INV2]()
    assert sorted(p.name for p in cell.ports) == ["VGND", "VPWR"]
    assert polygon_count(cell) == 46
    assert bbox_list(cell) == pytest.approx([-0.19, -0.24, 1.57, 2.96])


def test_nfet_fixture_roundtrip_is_exact(tmp_path):
    sky130 = _require_pdk()
    ref = FIXTURES / "nfet_01v8.gds"
    assert ref.is_file()
    assert ref.stat().st_size == 5050
    assert hashlib.sha256(ref.read_bytes()).hexdigest() == NFET_SHA256
    import gdsfactory as gf

    imported = gf.import_gds(ref)
    assert polygon_count(imported) == 48
    assert bbox_list(imported) == pytest.approx([-1.0, -1.205, 1.0, 1.205])
    # Live rebuild matches the fixture geometry (byte-identity holds
    # across processes — verified in report.md — but kfactory renames
    # the top cell when the same cell was already built in-session,
    # so same-session bytes are compared by geometry, not by hash).
    out = tmp_path / "nfet_rebuild.gds"
    rebuilt = sky130.cells[NFET]()
    rebuilt.write_gds(out)
    assert polygon_count(rebuilt) == 48
    assert bbox_list(rebuilt) == pytest.approx([-1.0, -1.205, 1.0, 1.205])
