"""PDK-SKY130GF RED — profile entry: decision, pins, tech/deck/model relpaths.

Valid RED = docs/pdk/sky130gf/profile.yaml does not exist yet, so
every test fails on FileNotFoundError. GREEN pins the onboarding
contract: the dual-scoped distribution decision (pip = layout
cells, open_pdks tree = decks authority), the proven pins
(sky130 1.0.0, gdsfactory 9.51.0 forward-compat), relpaths that
resolve against the real package, and the honest DRC position
(no runnable .lydrc ships — only a .lyd25 macro; upstream DRC CI
is the gdsfactoryplus cloud workflow, which the engine cannot
use; DRC authority stays with the sky130A tree deck).
"""

import pytest

from ._profile import FIXTURES, load_profile, sky130_root


def test_profile_identifies_sky130gf():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["id"] == "sky130gf"
    assert profile["package"] == "sky130"
    assert "skywater" in profile["label"].lower()
    assert profile["upstream"] == "https://github.com/gdsfactory/skywater130"
    assert "MIT" in profile["license"]
    assert "Apache-2.0" in profile["license"]


def test_profile_pins_proven_versions():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["pins"]["sky130"] == "1.0.0"
    assert profile["pins"]["gdsfactory"] == "9.51.0"
    assert profile["pins"]["klayout"] == "0.28.16"
    # As-shipped floor (pip metadata) vs verified: the lane verified
    # forward-compat, it did not re-pin upstream.
    assert profile["as_shipped"]["gdsfactory"] == "9.40.2"


def test_profile_records_dual_scoped_decision():
    # One process must never register two confusing ways: the pip
    # package is layout-cells convenience, the open_pdks tree stays
    # the decks/models authority, and runs pin the distribution.
    profile = load_profile()  # RED: missing profile.yaml
    decision = profile["decision"]
    assert decision["registration"] == "dual-scoped"
    assert decision["tree_authority"] == "sky130A"
    assert decision["pip_scope"] == ["layout", "cells", "klayout-tech"]
    assert decision["tree_scope"] == ["drc", "lvs", "extract", "sim"]
    assert "pin" in decision["no_mixing"].lower()
    assert "volare" in decision["rejected"].lower()


def test_profile_lists_single_proven_variant():
    profile = load_profile()  # RED: missing profile.yaml
    variants = profile["variants"]
    assert set(variants) == {"sky130"}
    variant = variants["sky130"]
    assert variant["module"] == "sky130"
    assert variant["pdk_name"] == "sky130"
    assert variant["status"] == "proven"


def test_profile_tech_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = sky130_root()
    if root is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    assert (root / "sky130" / "__init__.py").is_file()
    tech = profile["variants"]["sky130"]["tech"]
    for key in ("klayout_dir", "lyt", "lyp", "layers_yaml", "d25"):
        assert (root / tech[key]).exists(), (key, tech[key])
    assert tech["tech_name"] == "sky130"


def test_profile_drc_is_honest_about_no_local_deck():
    # The pip package ships NO runnable .lydrc — only a .lyd25 GUI
    # macro (batch run fails: "No layout loaded for running 2.5d
    # view"). Upstream DRC CI needs GFP_API_KEY (cloud). The profile
    # must say deck: null with a reason pointing at the tree deck.
    profile = load_profile()  # RED: missing profile.yaml
    drc = profile["variants"]["sky130"]["drc"]
    assert drc["deck"] is None
    assert "cloud" in drc["deck_reason"].lower()
    assert "sky130A.lydrc" in drc["deck_reason"]
    assert drc["d25_status"] == "inventoried-not-runnable"


def test_profile_ships_no_lydrc():
    profile = load_profile()  # RED: missing profile.yaml
    root = sky130_root()
    if root is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    found = sorted(
        str(p.relative_to(root)) for p in (root / "sky130").rglob("*.lydrc")
    )
    assert found == [], found
    assert profile["variants"]["sky130"]["drc"]["deck"] is None


def test_profile_model_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = sky130_root()
    if root is None:
        pytest.skip("sky130 pip package not installed (see recipe.md)")
    models = profile["variants"]["sky130"]["models"]
    assert (root / models["path"]).is_file()
    assert models["spice_file_count"] == 146
    assert "tree" in models["authority"].lower()


def test_profile_proof_goldens_match_fixture():
    profile = load_profile()  # RED: missing profile.yaml
    proof = profile["proofs"]["layout"]
    assert proof["variant"] == "sky130"
    assert proof["cell"] == "sky130_fd_pr__nfet_01v8"
    assert proof["ports"] == ["BODY", "DRAIN", "GATE", "SOURCE"]
    assert proof["n_polygons"] == 48
    ref = FIXTURES / proof["reference_gds"]
    assert ref.is_file()
    assert ref.stat().st_size == 5050
