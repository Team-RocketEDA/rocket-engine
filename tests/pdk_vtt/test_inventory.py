"""Golden inventory checks on the vendored VTT layers fixture.

The fixture is a verbatim copy of upstream gvtt/layers.yaml (MIT,
see profile.yaml `fixture` block for provenance + sha256). These tests
pin its real content: view count, key (layer, datatype) pairs, and the
documented absence of the 89/x waveguide-marking layers from the views.
"""

import re

from tests.pdk_vtt import _profile

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Spot-check goldens: (view name, (layer, datatype)).
GOLDEN_LAYERS = {
    "WG_RIBS_ADD": (1, 10),
    "WG_MOST_ADD": (1, 11),
    "WG_LANE_ADD": (1, 12),
    "WG_DEOX_ADD": (1, 13),
    "WG_ARCO_ADD": (1, 14),
    "WG_SNGL_ADD": (1, 15),
    "WG_PEDE_ADD": (1, 16),
    "WG_RIBS_SUB": (1, 20),
    "WG_MOST_SUB": (1, 21),
    "WG_RIBS_DF": (1, 0),
    "ME_GOLD_LF_C": (2, 2),
    "ME_ALUM_LF": (2, 3),
    "NP_PIMP_DF": (5, 2),
    "NP_NIMP_DF": (5, 3),
    "AX_NOXX": (63, 0),
    "AX_INFO": (63, 63),
}


def test_fixture_provenance_and_integrity():
    profile = _profile.load_profile()
    fix = profile["fixture"]
    assert fix["path"] == "tests/pdk_vtt/fixtures/layers.yaml"
    assert fix["upstream_source"] == "gvtt/layers.yaml"
    assert fix["upstream_commit"] == profile["upstream_commit"]
    assert fix["license"] == "MIT"
    actual = _profile.sha256_of(_profile.LAYERS_FIXTURE_PATH)
    assert actual == fix["sha256"], "fixture drifted from the verified upstream copy"
    assert actual == "0735910f13c0f0d059bf609ddba9c2ae5896888036cd67c7f9e857c430e3b85e"


def test_layer_view_count_matches_profile():
    views = _profile.load_layers_fixture()["LayerViews"]
    profile = _profile.load_profile()
    assert len(views) == 67
    assert profile["variants"]["3umsoi"]["tech"]["layer_views"] == len(views)


def test_golden_layer_numbers():
    views = _profile.load_layers_fixture()["LayerViews"]
    for name, (layer, datatype) in GOLDEN_LAYERS.items():
        assert name in views, f"missing view {name}"
        assert views[name]["layer"] == [layer, datatype], name


def test_views_wellformed_and_unique():
    views = _profile.load_layers_fixture()["LayerViews"]
    seen = set()
    for name, view in views.items():
        layer, datatype = view["layer"]
        assert isinstance(layer, int) and isinstance(datatype, int), name
        assert (layer, datatype) not in seen, f"duplicate layer for {name}"
        seen.add((layer, datatype))
        assert COLOR_RE.match(view["color"]), f"bad color for {name}"
    # Waveguide-marking layers live in layers.py only, not in the views.
    in_views = {layer for (layer, _dt) in seen}
    assert 89 not in in_views
