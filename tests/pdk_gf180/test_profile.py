"""PDK-GF180 RED — profile entry: variants, pins, tech/deck/model relpaths.

Valid RED = docs/pdk/gf180/profile.yaml does not exist yet, so
every test fails on FileNotFoundError. GREEN pins the onboarding
contract: the gf180mcu package pin, the gdsfactory pins for both
provision paths (PyPI release vs post-release source tree),
relpaths that resolve against the real package, and the honest DRC
position (no PDK deck ships — the wrapper's DRC runs through the
gdsfactoryplus cloud workflow, which the engine cannot use; engine
KLayout batch rules stand in, with sources cited).
"""

from . _profile import load_profile, require_pdk


def test_profile_identifies_gf180():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["id"] == "gf180"
    assert profile["package"] == "gf180mcu"
    assert "globalfoundries" in profile["label"].lower()
    assert profile["upstream"] == "https://github.com/gdsfactory/gf180mcu"
    assert profile["license"] == "Apache-2.0"


def test_profile_pins_proven_versions():
    profile = load_profile()  # RED: missing profile.yaml
    pins = profile["pins"]
    assert pins["gf180mcu"] == "1.0.0"
    # Release 1.0.0 needs gdsfactory~=9.40.0; the post-release source
    # tree (d422b86) allows <=9.51. Both provision paths are proven.
    assert pins["gdsfactory_release"] == "9.40.2"
    assert pins["gdsfactory_sourcetree"] == "9.51.0"
    assert pins["source_rev"].startswith("d422b86")


def test_profile_lists_mcu_variant():
    profile = load_profile()  # RED: missing profile.yaml
    variants = profile["variants"]
    assert set(variants) == {"mcu"}
    mcu = variants["mcu"]
    assert mcu["module"] == "gf180mcu"
    assert mcu["pdk_name"] == "gf180mcu"
    assert mcu["status"] == "proven"


def test_profile_tech_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    tech = profile["variants"]["mcu"]["tech"]
    assert tech["tech_name"] == "gf180mcu"
    for key in ("klayout_dir", "lyt", "lyp", "map", "layers_yaml"):
        assert (root / tech[key]).exists(), (key, tech[key])


def test_profile_models_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    models = profile["variants"]["mcu"]["models"]
    assert models["simulator"] == "ngspice"
    assert models["corner"] == "typical"
    assert (root / models["dir"]).is_dir()
    for rel in models["vendor_files"]:
        assert (root / rel).is_file(), rel
    # Corner wrappers exist in the post-release source tree only.
    assert models["corner_wrappers"] == [
        "models/ngspice/fets.lib",
        "models/ngspice/settings.inc",
    ]


def test_profile_states_honest_drc_position():
    profile = load_profile()  # RED: missing profile.yaml
    drc = profile["variants"]["mcu"]["drc"]
    assert drc["deck"] is None
    assert "gdsfactoryplus" in drc["deck_reason"]
    assert "cloud" in drc["deck_reason"]
    rules = drc["engine_rules"]
    assert len(rules) >= 1
    assert rules[0]["layer"] == [34, 0]
    assert rules[0]["width_um"] == 0.23
    assert rules[0]["space_um"] == 0.23
    assert rules[0]["ref"]


def test_profile_names_uninitialized_libraries():
    profile = load_profile()  # RED: missing profile.yaml
    libs = profile["libraries"]
    assert set(libs) == {"sc_7t5v0", "sc_9t5v0", "io", "pr"}
    for name, lib in libs.items():
        assert lib["status"] == "submodule-uninitialized", name
        assert "globalfoundries-pdk-libs" in lib["submodule"], name


def test_profile_carries_proof_goldens():
    profile = load_profile()  # RED: missing profile.yaml
    layout = profile["proofs"]["layout"]
    assert layout["cell"] == "gf180_inv_pair"
    assert layout["ports"] == ["IN", "OUT", "VDD", "VSS"]
    assert layout["bbox_um"] == [[-1.15, -0.71], [1.97, 4.3]]
    sim = profile["proofs"]["sim"]
    assert sim["corner"] == "typical"
    assert sim["vdd_V"] == 3.3
