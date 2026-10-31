"""PDK-ASAP7 RED — profile entry: predictive-only flag, pins, relpaths.

Valid RED = docs/pdk/asap7/profile.yaml does not exist yet, so
every test fails on FileNotFoundError. GREEN pins the onboarding
contract: the predictive-only identity (never manufacturable, never
better-proven than measured silicon), the verified source revs and
tool pins, the four-Vt 7.5-track variant with relpaths resolving
against the pre-cloned trees, and the proof goldens recorded in
the profile.
"""

import pytest

from ._profile import find_lib_root, find_wrapper_root, load_profile

EXPECT_VARIANTS = {"sc7p5t_28"}

EXPECT_GROUP_COUNTS = {
    "AO": 42,
    "INVBUF": 37,
    "OA": 34,
    "SEQ": 33,
    "SIMPLE": 56,
    "TBUF": 1,
}


def test_profile_identifies_asap7_predictive_only():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["id"] == "asap7"
    assert profile["predictive_only"] is True
    assert profile["manufacturable"] is False
    assert "predictive" in profile["label"].lower()
    assert profile["upstream"] == "https://github.com/The-OpenROAD-Project/asap7"
    assert profile["license"] == "BSD-3-Clause"


def test_profile_pins_verified_revs_and_tools():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["source"]["wrapper_rev"] == (
        "d24f8b857ff74cf5b21ab18a7e1b11a3954c449b"
    )
    assert profile["source"]["lib_rev"] == (
        "e5bd25da72cd297b8c0ec6f77600e0cbaa1124d0"
    )
    assert profile["source"]["r1p7_rev"] == (
        "58d72c9d291e186a77468586ab0c43d8a21eda6a"
    )
    assert profile["pins"]["klayout"] == "0.28.16"
    assert profile["pins"]["ngspice"] == "42"
    assert profile["pins"]["xschem"] == "3.4.8RC"
    assert profile["spike"]["gdsfactory_covers_asap7"] is False
    assert profile["spike"]["openroad_installed"] is False
    assert profile["spike"]["openvaf_installed"] is False


def test_profile_lists_single_variant_four_vts():
    profile = load_profile()  # RED: missing profile.yaml
    assert set(profile["variants"]) == EXPECT_VARIANTS
    variant = profile["variants"]["sc7p5t_28"]
    assert variant["library"] == "asap7sc7p5t_28"
    assert variant["lib_version"] == 28
    assert variant["track"] == "7.5t"
    assert variant["vts"] == ["LVT", "RVT", "SLVT", "SRAM"]
    assert variant["status"] == "predictive-proof"


def test_profile_wrapper_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_wrapper_root()
    assert root is not None, "asap7 wrapper tree unavailable for relpath check"
    wrapper = profile["wrapper"]
    for key in ("readme", "license", "gitmodules"):
        assert (root / wrapper[key]).is_file(), (key, wrapper[key])
    # Submodules are NOT initialized in the pre-cloned wrapper.
    assert wrapper["submodules_initialized"] is False
    for sub in wrapper["submodule_dirs"]:
        assert (root / sub).is_dir(), sub


def test_profile_lib_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_lib_root()
    assert root is not None, "asap7 lib tree unavailable for relpath check"
    tech = profile["variants"]["sc7p5t_28"]["tech"]
    assert (root / tech["techlef"]).is_file()
    assert (root / tech["verilog_dir"]).is_dir()
    assert (root / tech["lef_dir"]).is_dir()
    assert (root / tech["gds_dir"]).is_dir()
    assert (root / tech["lib_ccs_dir"]).is_dir()
    assert (root / tech["lib_nldm_dir"]).is_dir()
    assert tech["n_verilog_files"] == 24
    assert tech["n_lef_files"] == 4
    assert tech["n_gds_files"] == 4


def test_profile_deck_is_honestly_missing_open_source():
    profile = load_profile()  # RED: missing profile.yaml
    drc = profile["variants"]["sc7p5t_28"]["drc"]
    assert drc["deck_status"] == "missing-open-source"
    assert "calibre" in drc["deck_note"].lower()
    assert "asap.asu.edu" in drc["deck_note"]


def test_profile_models_are_hspice_only():
    profile = load_profile()  # RED: missing profile.yaml
    models = profile["variants"]["sc7p5t_28"]["models"]
    assert models["format"] == "hspice-bsimcmg-l72"
    assert models["bsimcmg_version"] == 107
    assert models["status"] == "blocked-openvaf-missing"


def test_profile_proof_goldens_recorded():
    profile = load_profile()  # RED: missing profile.yaml
    proofs = profile["proofs"]
    assert proofs["verilog_total_modules"] == 812
    assert proofs["verilog_group_counts"] == EXPECT_GROUP_COUNTS
    assert proofs["lef_macros_per_file"] == 213
    assert proofs["gds_cells_per_file"] == 213
    assert proofs["gds_dbu"] == pytest.approx(0.00025)
    inv = proofs["invx1_r"]
    assert inv["bbox_dbu"] == [0, -88, 824, 1168]
    flat = [c for corner in inv["bbox_um"] for c in corner]
    assert flat == pytest.approx([0.0, -0.022, 0.206, 0.292])
    assert inv["n_shapes"] == 51
    assert inv["n_layers"] == 16
    assert proofs["techlef_n_layers"] == 24
    assert proofs["lib_nldm_archives"] == 73
    assert proofs["lib_ccs_archives"] == 218
