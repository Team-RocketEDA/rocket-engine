"""Pin the PDK-VTT profile: pins, variant, verdict, and repo-closure exclusion.

Golden expectations encode the verified upstream facts from
docs/pdk/vtt/report.md. Any change here must come with a re-verification
against the pre-cloned source, never an edit to make tests pass.
"""

import re

from tests.pdk_vtt import _profile


def _parse_bound(spec: str, op: str) -> tuple[int, ...]:
    m = re.search(rf"{re.escape(op)}\s*(\d+(?:\.\d+)*)", spec)
    assert m, f"no {op} bound in {spec!r}"
    return tuple(int(p) for p in m.group(1).split("."))


def test_profile_identity_and_schema():
    profile = _profile.load_profile()
    assert profile["schema"] == "rocketeda/pdk-profile/v0.1"
    assert profile["id"] == "vtt"
    assert profile["upstream"] == "https://github.com/gdsfactory/vtt.git"
    assert profile["license"] == "MIT"
    assert profile["package"] == "gvtt"


def test_profile_pins_match_upstream_lock():
    profile = _profile.load_profile()
    pins = profile["pins"]
    # gvtt/__init__.py __version__ and pyproject.toml version.
    assert pins["gvtt"] == "0.1.0"
    # pyproject.toml dependencies entry, verbatim.
    assert pins["gdsfactory_range"] == ">=9.0.1,<9.46.0"
    # uv.lock package entry for gdsfactory (what upstream CI installs).
    assert pins["uv_lock_gdsfactory"] == "9.0.1"
    assert profile["upstream_commit"] == "001df503792a0297165c239d3c63de1322add10a"


def test_profile_variant_inventory():
    profile = _profile.load_profile()
    variants = profile["variants"]
    assert sorted(variants) == ["3umsoi"]
    v = variants["3umsoi"]
    assert v["module"] == "gvtt"
    assert v["pdk_name"] == "VTT-3umSOI"
    assert v["status"] == "blocked"
    assert v["tech"]["klayout_dir"] == "gvtt/klayout"
    assert v["tech"]["lyt"] == "gvtt/klayout/tech.lyt"
    assert v["tech"]["lyp"] == "gvtt/klayout/layers.lyp"
    assert v["tech"]["layers_yaml"] == "gvtt/layers.yaml"
    assert v["tech"]["tech_name"] == "VTT"
    assert v["tech"]["layer_views"] == 67
    assert v["drc"]["deck"] is None
    assert "no" in v["drc"]["deck_reason"].lower()
    assert v["models"]["registry"] is None


def test_verdict_is_pinned_blocked():
    profile = _profile.load_profile()
    verdict = profile["verdict"]
    assert verdict["status"] == "blocked"
    assert verdict["reason"] == "stale-constants-import"
    # Evidence pointers must stay attached to the verdict.
    assert "ImportError" in verdict["import_error"]
    assert "constants" in verdict["import_error"]
    assert verdict["import_probe"]["gvtt_unmodified"] is False
    assert verdict["import_probe"]["shimmed_cells_built"] == 12


def test_repo_layout_closure_exclusion():
    """VTT's gdsfactory ceiling must stay below the repo layout floor.

    The repo ships gdsfactory>=9.51 (layout group); VTT caps at <9.46.0,
    so the two can never share one environment until upstream raises
    its bound (and fixes the stale import). If either side moves, this
    test forces the lane to re-verify instead of silently going stale.
    """
    profile = _profile.load_profile()
    ceiling = _parse_bound(profile["pins"]["gdsfactory_range"], "<")
    floor = _parse_bound(profile["verified_against"]["repo_layout_gdsfactory"], ">=")
    assert ceiling <= floor, (
        f"VTT ceiling {ceiling} no longer excludes repo floor {floor}; "
        "re-verify the lane against the new pins"
    )
    assert profile["verified_against"]["repo_layout_gdsfactory"] == ">=9.51,<10"
