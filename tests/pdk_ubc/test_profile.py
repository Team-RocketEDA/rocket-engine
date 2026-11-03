"""PDK-UBC RED — profile entry: variants, pins, tech/deck/model relpaths.

Valid RED = docs/pdk/ubc/profile.yaml does not exist yet, so
every test fails on FileNotFoundError. GREEN pins the onboarding
contract: the single ebeam variant, the proven pins (ubcpdk
3.3.5, gdsfactory 9.51.0, sax 0.18.2, KLayout 0.28.16), relpaths
that resolve against the real package, the runnable PDK DRC deck
(+ its batch-harness note), and the 32-model SAX registry.
"""

import pytest

from ._profile import find_ubc_root, load_profile

EXPECT_VARIANTS = {"ebeam"}


def test_profile_identifies_ubc():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["id"] == "ubc"
    assert profile["package"] == "ubcpdk"
    assert "siepic" in profile["label"].lower() or "ebeam" in profile["label"].lower()
    assert profile["upstream"] == "https://github.com/gdsfactory/ubc"
    assert profile["license"] == "MIT"


def test_profile_pins_proven_versions():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["pins"]["ubcpdk"] == "3.3.5"
    assert profile["pins"]["gdsfactory"] == "9.51.0"
    assert profile["pins"]["sax"] == "0.18.2"
    assert profile["pins"]["klayout"] == "0.28.16"


def test_profile_lists_single_ebeam_variant():
    profile = load_profile()  # RED: missing profile.yaml
    assert set(profile["variants"]) == EXPECT_VARIANTS
    variant = profile["variants"]["ebeam"]
    assert variant["module"] == "ubcpdk"
    assert variant["pdk_name"] == "ubcpdk"
    assert variant["status"] == "proven"


def test_profile_tech_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_ubc_root()
    assert root is not None, "ubc source tree unavailable for relpath check"
    assert (root / "ubcpdk" / "__init__.py").is_file()
    tech = profile["variants"]["ebeam"]["tech"]
    for key in ("klayout_dir", "lyt", "lyp", "layers_yaml"):
        assert (root / tech[key]).exists(), (key, tech[key])
    assert tech["tech_name"] == "UBCPDK"


def test_profile_deck_is_present_and_runnable():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_ubc_root()
    assert root is not None, "ubc source tree unavailable for deck check"
    drc = profile["variants"]["ebeam"]["drc"]
    deck_rel = drc["deck"]
    assert deck_rel == "ubcpdk/klayout/tech/drc/SiEPIC_EBeam_DRC.lyp"
    deck_text = (root / deck_rel).read_text()
    # Batch anchor (harness hook) + headline Si rules ship in the deck.
    assert 'report("SiEPIC-EBeam-PDK DRC")' in deck_text
    assert "LayerSi.width(0.06" in deck_text
    assert "LayerSi.space(0.06" in deck_text
    assert drc["deck_status"] == "proven"
    assert "batch" in drc["deck_note"].lower()
    # Teaching decks are inventoried, not proven.
    for rel in drc["inventoried_decks"]:
        assert (root / rel).is_file(), rel


def test_profile_model_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = find_ubc_root()
    assert root is not None, "ubc source tree unavailable for model check"
    models = profile["variants"]["ebeam"]["models"]
    assert (root / models["path"]).exists()
    assert models["registry"] == "get_models"
    assert models["count"] == 32
    assert models["status"] == "proven"


def test_profile_proof_layout_matches_reference():
    profile = load_profile()  # RED: missing profile.yaml
    proof = profile["proofs"]["layout"]
    assert proof["variant"] == "ebeam"
    assert proof["cell"] == "mzi"
    assert proof["ports"] == ["o1", "o2", "o3", "o4"]
    assert proof["n_polygons"] == 34
    flat = [c for corner in proof["bbox_um"] for c in corner]
    assert flat == pytest.approx([-10.0, -29.4, 99.1, 25.1])
    assert proof["reference_gds"] == "tests/gds_ref_si220/mzi.gds"


def test_profile_proof_optical_and_drc_recorded():
    profile = load_profile()  # RED: missing profile.yaml
    optical = profile["proofs"]["optical"]
    assert optical["model"] == "ubcpdk PDK.models"
    assert optical["circuit"] == "mzi"
    assert optical["at_nm"] == 1550.0
    drc = profile["proofs"]["drc"]
    assert drc["reference_total"] == 6
    assert drc["reference_rules"] == {"Boundary": 6}
    assert drc["bad_total"] == 5
