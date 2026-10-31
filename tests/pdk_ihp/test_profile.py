"""PDK-IHP RED — profile entry: flavors, pins, tech/deck/model relpaths.

Valid RED = docs/pdk/ihp/profile.yaml does not exist yet, so every
test fails on FileNotFoundError. GREEN pins the onboarding contract:
the BiCMOS vs RF flavor split, the proven pins (ihp-gdsfactory
2.0.1 @ d7643aa, gdsfactory 9.51.0, sax 0.18.2), relpaths that
resolve against the real tree, and the honest gaps (no LVS/Magic/
xschem/LEF in the wrapper; PDK deck needs newer KLayout; MOS sim
needs Verilog-A).
"""

import importlib.util

from ._profile import require_ihp_root, load_profile

EXPECT_FLAVORS = {"bicmos", "rf"}


def test_profile_identifies_ihp():
    profile = load_profile()  # RED: missing profile.yaml
    assert profile["id"] == "ihp"
    assert profile["package"] == "ihp-gdsfactory"
    assert "sg13g2" in profile["label"].lower()
    assert profile["upstream"] == "https://github.com/gdsfactory/ihp"
    assert profile["license"] == "Apache-2.0"


def test_profile_pins_proven_versions():
    profile = load_profile()  # RED: missing profile.yaml
    pins = profile["pins"]
    assert pins["ihp-gdsfactory"] == "2.0.1"
    assert pins["ihp_rev"] == "d7643aafba2c610ea752a9b8fc2958de3e98ee87"
    assert pins["gdsfactory"] == "9.51.0"
    assert pins["sax"] == "0.18.2"
    assert pins["ngspice"] == "42"


def test_profile_splits_bicmos_vs_rf_flavors():
    profile = load_profile()  # RED: missing profile.yaml
    assert set(profile["variants"]) == EXPECT_FLAVORS
    bicmos = profile["variants"]["bicmos"]
    rf = profile["variants"]["rf"]
    # BiCMOS core: LV/HV CMOS + HBTs, no RF-only cells.
    for cell in ("nmos", "pmos", "nmos_hv", "pmos_hv", "npn13G2", "pnpMPA"):
        assert cell in bicmos["cells"]
    for cell in ("rfnmos", "rfpmos", "rfcmim", "inductor2", "inductor3"):
        assert cell not in bicmos["cells"]
    # RF flavors: guard-ring FETs + RF passives, no plain-CMOS dupes.
    for cell in (
        "rfnmos",
        "rfpmos",
        "rfnmos_hv",
        "rfpmos_hv",
        "rfcmim",
        "inductor2",
        "inductor3",
        "svaricap",
    ):
        assert cell in rf["cells"]
    for cell in ("nmos", "pmos", "npn13G2"):
        assert cell not in rf["cells"]
    assert bicmos["status"] == "proven"
    assert rf["status"] == "proven"


def test_profile_tech_relpaths_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = require_ihp_root()
    for name, variant in profile["variants"].items():
        tech = variant["tech"]
        for key in ("klayout_dir", "lyt", "lyt_alt", "lyp", "layers_yaml"):
            assert (root / tech[key]).exists(), (name, key)
        assert tech["tech_names"] == ["IHP", "sg13g2"]


def test_profile_deck_and_models_resolve():
    profile = load_profile()  # RED: missing profile.yaml
    root = require_ihp_root()
    for name, variant in profile["variants"].items():
        drc = variant["drc"]
        for key in ("deck", "runner", "defaults"):
            assert (root / drc[key]).is_file(), (name, key)
        assert drc["deck_status"] == "needs-newer-klayout"
        for relpath in variant["models"]["ngspice_libs"]:
            assert (root / relpath).is_file(), (name, relpath)


def test_profile_declares_honest_gaps():
    profile = load_profile()  # RED: missing profile.yaml
    gaps = profile["gaps"]
    for key in ("lvs", "magic", "xschem", "lef_liberty", "mos_ngspice_va"):
        assert gaps[key]["status"] == "n/a"
        assert gaps[key]["reason"], key


def test_profile_cells_exist_in_package():
    try:
        cells_spec = importlib.util.find_spec("ihp.cells")
    except (ImportError, AttributeError, ValueError):
        cells_spec = None
    if cells_spec is None:
        import pytest

        pytest.skip("ihp package not importable here")
    from ihp import cells as ihp_cells

    profile = load_profile()  # RED: missing profile.yaml
    for name, variant in profile["variants"].items():
        for cell in variant["cells"]:
            assert hasattr(ihp_cells, cell), (name, cell)
