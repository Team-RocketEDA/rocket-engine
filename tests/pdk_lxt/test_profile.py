"""PDK-LXT profile tests: docs/pdk/lxt/profile.yaml is the lane contract.

Valid RED = the profile does not exist yet, so every test fails on
the missing file. GREEN = the profile exists and pins the exact
upstream revision, variants, and tech/deck/model relpaths the recipe
and proofs consume. Runs in the repo env (ruamel only, no PDK deps).
"""

from pathlib import Path

from ruamel.yaml import YAML

LANE = Path(__file__).resolve().parent
PROFILE = LANE / ".." / ".." / "docs" / "pdk" / "lxt" / "profile.yaml"
RECIPE = LANE / ".." / ".." / "docs" / "pdk" / "lxt" / "recipe.md"

UPSTREAM_REPO = "https://github.com/Luxtelligence/lxt_pdk_gf.git"
UPSTREAM_REV = "d16db6a4882657feb1ce696c16c604ff6cb7ccfa"
FETCH_URL = "https://resources.luxtelligence.ai/request-access?resource=drc"


def _load_profile():
    assert PROFILE.is_file(), f"missing lane profile: {PROFILE} (see PDK-LXT recipe)"
    return YAML(typ="safe").load(PROFILE.read_text())


def test_profile_exists_and_identifies_lane():
    profile = _load_profile()
    assert profile["schema"] == "rocketeda/pdk-profile/v0.1"
    assert profile["id"] == "lxt"
    assert profile["display_id"] == "lxt_pdk_gf"
    for field in ("upstream", "revision", "variants", "pins", "capabilities"):
        assert field in profile, f"profile misses field: {field}"


def test_profile_pins_upstream_revision():
    profile = _load_profile()
    assert profile["upstream"] == UPSTREAM_REPO
    rev = profile["revision"]
    assert rev == UPSTREAM_REV, f"profile pins {rev!r}, want {UPSTREAM_REV}"
    assert len(rev) == 40 and all(c in "0123456789abcdef" for c in rev)
    assert profile["package"] == "lxt_pdk_gf"
    assert profile["package_version"] == "2.0"
    assert profile["license"] == "MIT"


def test_profile_pins_solver_deps_from_upstream_pyproject():
    profile = _load_profile()
    pins = profile["pins"]
    assert pins["python"] == "3.12"
    # Verbatim requirement strings from upstream pyproject at the
    # pinned revision: gdsfactory~=9.34, gplugins>=1.4,<2, sax~=0.16.3.
    assert pins["gdsfactory"] == "~=9.34"
    assert pins["gplugins"] == ">=1.4,<2"
    assert pins["sax"] == "~=0.16.3"


def test_profile_variants_cover_both_stacks():
    profile = _load_profile()
    variants = profile["variants"]
    assert set(variants) == {"ltoi300", "lnoi400"}
    ltoi = variants["ltoi300"]
    assert ltoi["module"] == "ltoi300"
    assert "tantalate" in ltoi["process"].lower()
    assert ltoi["tech"]["klayout_dir"] == "ltoi300/klayout"
    assert ltoi["tech"]["lyp"] == "ltoi300/klayout/ltoi300.lyp"
    assert ltoi["tech"]["lyt"] is None  # ships no .lyt (verified in clone)
    assert ltoi["tech"]["layers_yaml"] == "ltoi300/layers.yaml"
    assert ltoi["models"]["path"] == "ltoi300/models.py"
    assert ltoi["models"]["count"] == 13
    assert ltoi["cells"]["count"] == 26
    assert ltoi["cells"]["proof_cell"] == "straight_rwg900_cband"
    assert ltoi["models"]["proof_model"] == "straight_rwg900_cband"
    assert ltoi["status"] == "proven"
    lnoi = variants["lnoi400"]
    assert lnoi["module"] == "lnoi400"
    assert "niobate" in lnoi["process"].lower()
    assert lnoi["tech"]["klayout_dir"] == "lnoi400/klayout"
    assert lnoi["tech"]["lyt"] == "lnoi400/klayout/tech.lyt"
    assert lnoi["tech"]["lyp"] == "lnoi400/klayout/lnoi400.lyp"
    assert lnoi["tech"]["layers_yaml"] == "lnoi400/layers.yaml"
    assert lnoi["models"]["path"] == "lnoi400/models.py"
    assert lnoi["models"]["count"] == 9
    assert lnoi["cells"]["count"] == 23
    assert lnoi["cells"]["proof_cell"] == "straight_rwg1000"
    assert lnoi["status"] == "proven"


def test_profile_records_tech_install_gap():
    # Upstream install_tech.py links ONLY lnoi400; the profile must
    # record that ltoi300 needs the manual link step (see recipe).
    profile = _load_profile()
    install = profile["tech_install"]
    assert install["script"] == "install_tech.py"
    assert install["covers"] == ["lnoi400"]
    assert "ltoi300" in install["manual_variant"]


def test_profile_marks_drc_gated_with_fetch_recipe():
    profile = _load_profile()
    for variant in ("ltoi300", "lnoi400"):
        drc = profile["variants"][variant]["drc"]
        assert drc["deck"] is None, f"{variant}: no in-repo deck exists"
        assert drc["deck_status"] == "gated"
        assert drc["fetch_url"] == FETCH_URL
        assert "request" in drc["gate_requirement"].lower()
        assert drc["deck_glob"] == "*.lydrc"
        assert "one .lydrc at a time" in drc["caveats"]
    caps = profile["capabilities"]["drc"]
    assert caps["status"] == "gated"
    assert caps["deck_kind"] == "user-supplied"
    assert caps["fetch_url"] == FETCH_URL


def test_profile_sim_path_is_sax():
    profile = _load_profile()
    sim = profile["capabilities"]["optical_sim"]
    assert sim["status"] == "supported"
    assert sim["path"] == "sax"
    assert "SDict" in sim["evidence"]
    layout = profile["capabilities"]["layout"]
    assert layout["status"] == "supported"
    assert layout["path"] == "gdsfactory"


def test_recipe_doc_exists_and_names_provision_commands():
    assert RECIPE.is_file(), f"missing lane recipe: {RECIPE}"
    text = RECIPE.read_text()
    for needle in (
        "git clone https://github.com/Luxtelligence/lxt_pdk_gf.git",
        "pip install -e .",
        "python install_tech.py",
        "resources.luxtelligence.ai",
    ):
        assert needle in text, f"recipe misses required command/text: {needle}"
