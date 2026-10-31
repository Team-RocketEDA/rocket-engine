"""PDK-CSPDK profile entry: variant -> tech/DRC relpaths resolve (RED-first).

RED = docs/pdk/cspdk/profile.yaml does not exist yet, so every test
fails on FileNotFoundError. GREEN = the profile pins cspdk 2.1.0 and
each variant's tech/deck/model relpaths exist against the resolved
cspdk tree (installed, vendored, or pre-cloned). Existence checks
skip LOUDLY where no cspdk tree is available; pin/shape checks need
no PDK.
"""

import pytest

from ._profile import find_cspdk_root, load_profile

CSPDK_PIN = "2.1.0"
PROVEN_VARIANT = "si340"


def test_profile_pins_cspdk_version():
    profile = load_profile()
    assert profile["id"] == "cspdk"
    assert profile["pins"]["cspdk"] == CSPDK_PIN


def test_profile_proven_variant_shape():
    profile = load_profile()
    si340 = profile["variants"][PROVEN_VARIANT]
    assert si340["status"] == "proven"
    assert si340["module"] == "cspdk.si340"
    assert si340["tech"]["lyt"].endswith("tech.lyt")
    assert si340["tech"]["lyp"].endswith("layers.lyp")
    assert si340["models"]["registry"] == "get_models"


def test_profile_covers_all_upstream_variants():
    profile = load_profile()
    assert sorted(profile["variants"]) == [
        "ge_on_si",
        "si220",
        "si220_ebeam_event",
        "si340",
        "si500",
        "si_sus",
        "sin200",
        "sin300",
    ]


def test_profile_engine_rules_cite_guideline():
    profile = load_profile()
    rules = profile["variants"][PROVEN_VARIANT]["drc"]["engine_rules"]
    assert rules, "si340 needs engine DRC rules (no shippable deck)"
    rule = rules[0]
    assert rule["layer"] == [3, 0]
    assert rule["width_um"] == pytest.approx(0.35)
    assert rule["space_um"] == pytest.approx(0.2)
    assert "49th" in rule["ref"]


def test_profile_relpaths_exist_against_cspdk_tree():
    profile = load_profile()
    root = find_cspdk_root()
    if root is None:
        pytest.skip(
            "no cspdk tree (pip install cspdk==2.1.0 or "
            "scripts/fetch_fixtures.py --only cspdk)"
        )
    missing = []
    for variant, entry in profile["variants"].items():
        for key in ("lyt", "lyp", "layers_yaml"):
            rel = (entry.get("tech") or {}).get(key)
            if key == "layers_yaml" and not rel:
                rel = entry.get("layers_yaml")
            if rel and not (root / rel).is_file():
                missing.append(f"{variant}.{key} -> {rel}")
        decks = (entry.get("drc") or {}).get("deck") or []
        for rel in decks:
            if not (root / rel).is_file():
                missing.append(f"{variant}.drc.deck -> {rel}")
        script = (entry.get("drc") or {}).get("script")
        if script and not (root / script).is_file():
            missing.append(f"{variant}.drc.script -> {script}")
        model_path = (entry.get("models") or {}).get("path")
        if model_path and not (root / model_path).exists():
            missing.append(f"{variant}.models.path -> {model_path}")
    assert not missing, "profile relpaths missing: " + "; ".join(missing)


def test_profile_pin_matches_importable_package():
    profile = load_profile()
    root = find_cspdk_root()
    if root is None:
        pytest.skip(
            "no cspdk tree (pip install cspdk==2.1.0 or "
            "scripts/fetch_fixtures.py --only cspdk)"
        )
    from . import _profile as lane

    cspdk = lane.ensure_cspdk()
    assert cspdk.__version__ == profile["pins"]["cspdk"] == CSPDK_PIN
