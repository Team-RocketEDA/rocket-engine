"""LAYER-SERVING wiring verification (integrator-run, post-patch).

Exercises the six layer queries through `Engine.submit`:
get_layer_stackup, get_layer_rows, list_layer_presets,
save_layer_preset, delete_layer_preset, apply_layer_preset.

State contract: the catalog test FAILS while the wiring patch in
docs/work/LAYER-SERVING/report.md is unapplied (that failure is the
integrator's RED); every Engine-behavior test below SKIPS while
unwired. After the patch this file must run with ZERO skips and
zero failures. Fixtures are inline and tiny; no PDK tree needed.
"""

import pytest

WIRING_NAMES = (
    "get_layer_stackup",
    "get_layer_rows",
    "list_layer_presets",
    "save_layer_preset",
    "delete_layer_preset",
    "apply_layer_preset",
)

PATCH_POINTER = (
    "layer-serving wiring patch not applied; see "
    "docs/work/LAYER-SERVING/report.md (integrator applies, then re-runs)"
)

TINY_LYP = """<?xml version="1.0" encoding="utf-8"?>
<layer-properties>
 <properties>
  <frame-color>#112233</frame-color>
  <fill-color>#445566</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>poly.drawing - 66/20</name>
  <source>66/20@1</source>
 </properties>
 <properties>
  <frame-color>#0000ff</frame-color>
  <fill-color>#0000ff</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met1.drawing - 68/20</name>
  <source>68/20@1</source>
 </properties>
 <properties>
  <frame-color>#999999</frame-color>
  <fill-color>#999999</fill-color>
  <valid>false</valid>
  <visible>false</visible>
  <name>met1.fill - 68/30</name>
  <source>68/30@1</source>
 </properties>
</layer-properties>
"""

TINY_LYT = """<?xml version="1.0" encoding="utf-8"?>
<technology>
 <name>sky130</name>
 <dbu>0.001</dbu>
</technology>
"""

TINY_XS = """
poly = layer("66/20")
met1 = layer("68/20")
gox_thickness = 0.004
poly_thickness = 0.18
"""

RELS = {
    "lyp": "libs.tech/klayout/tech/sky130A.lyp",
    "lyt": "libs.tech/klayout/tech/sky130A.lyt",
    "xsect": "libs.tech/klayout/tech/xsect/sky130.xs",
}


def _register_layer_pdk(tmp_path):
    from rocket_engine.interfaces.pdks import register_pdk

    engine_root = tmp_path / "root"
    source = tmp_path / "src"
    for key, rel in RELS.items():
        target = source / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text({"lyp": TINY_LYP, "lyt": TINY_LYT, "xsect": TINY_XS}[key])
    register_pdk(source, "sky130A", "v9", engine_root=engine_root)
    return engine_root


def _engine():
    from rocket_engine.composition import Engine

    return Engine("layer-wiring", actor="layer-wiring")


def _submit(engine, name, arguments):
    return engine.submit({
        "project_id": "layer-wiring",
        "operation": name,
        "arguments": arguments,
        "request_id": f"wiring-{name}",
    })


def _require_wired(engine):
    from rocket_engine.project.errors import ProjectError

    try:
        _submit(engine, "list_layer_presets", {})
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip(PATCH_POINTER)
        raise


def test_layer_queries_are_cataloged_and_mapped():
    from rocket_engine.composition import QUERY_ENGINE_METHODS
    from rocket_engine.interfaces.vocabulary import QUERIES

    missing = [name for name in WIRING_NAMES if name not in QUERIES]
    assert missing == [], f"{PATCH_POINTER}: {missing}"
    unmapped = [name for name in WIRING_NAMES if name not in QUERY_ENGINE_METHODS]
    assert unmapped == [], f"{PATCH_POINTER}: {unmapped}"


def test_wired_stackup_query_serves_store_stackup(tmp_path):
    engine = _engine()
    _require_wired(engine)
    engine_root = _register_layer_pdk(tmp_path)

    stackup = _submit(engine, "get_layer_stackup", {
        "pdk_id": "sky130A", "revision": "v9",
        "engine_root": str(engine_root),
    })
    assert stackup["stackup_version"] == 1
    assert [layer["name"] for layer in stackup["layers"]] == [
        "poly.drawing", "met1.drawing", "met1.fill",
    ]
    assert stackup["enabled"] == ["poly.drawing", "met1.drawing"]
    assert stackup["groups"]["metal"] == ["met1.drawing", "met1.fill"]
    assert stackup["source"]["kind"] == "pdk-store"


def test_wired_rows_default_and_preset(tmp_path):
    engine = _engine()
    _require_wired(engine)
    engine_root = _register_layer_pdk(tmp_path)
    base = {"pdk_id": "sky130A", "revision": "v9",
            "engine_root": str(engine_root)}

    default = _submit(engine, "get_layer_rows", dict(base))
    assert [row["name"] for row in default["rows"]] == [
        "poly.drawing", "met1.drawing", "met1.fill",
    ]
    assert default["flip"] is False
    metal = _submit(engine, "get_layer_rows", {**base, "preset": "All-metal"})
    visible = {row["name"]: row["visible"] for row in metal["rows"]}
    assert visible == {
        "poly.drawing": False, "met1.drawing": True, "met1.fill": False,
    }
    tuned = _submit(engine, "get_layer_rows", {
        **base, "preset": "None",
        "overrides": {"poly.drawing": True}, "active": "poly.drawing",
    })
    by_name = {row["name"]: row for row in tuned["rows"]}
    assert by_name["poly.drawing"]["visible"] is True
    assert by_name["poly.drawing"]["active"] is True
    assert tuned["active"] == "poly.drawing"


def test_wired_preset_save_apply_delete_round_trip(tmp_path):
    engine = _engine()
    _require_wired(engine)
    engine_root = _register_layer_pdk(tmp_path)
    base = {"pdk_id": "sky130A", "revision": "v9",
            "engine_root": str(engine_root)}

    saved = _submit(engine, "save_layer_preset", {
        **base, "name": "mine", "layers": {"met1.drawing": True},
        "flip": True, "active": "met1.drawing",
    })
    assert saved["builtin"] is False
    names = [entry["name"] for entry in
             _submit(engine, "list_layer_presets", {})["presets"]]
    assert names == ["All", "None", "All-metal", "Top", "Bottom", "mine"]
    applied = _submit(engine, "apply_layer_preset", {**base, "name": "mine"})
    assert applied["flip"] is True
    assert applied["layers"]["met1.drawing"] is True
    assert applied["layers"]["poly.drawing"] is False
    assert _submit(engine, "delete_layer_preset", {"name": "mine"}) == {
        "deleted": "mine",
    }


def test_wired_save_rejects_builtin_names(tmp_path):
    engine = _engine()
    _require_wired(engine)
    engine_root = _register_layer_pdk(tmp_path)

    with pytest.raises(Exception) as excinfo:
        _submit(engine, "save_layer_preset", {
            "pdk_id": "sky130A", "revision": "v9",
            "engine_root": str(engine_root),
            "name": "All", "layers": {},
        })
    assert getattr(excinfo.value, "code", None) == "preset_conflict"


def test_wired_unknown_pdk_and_preset_are_loud(tmp_path):
    from rocket_engine.interfaces.pdks import ensure_engine_root

    engine = _engine()
    _require_wired(engine)
    engine_root = ensure_engine_root(tmp_path / "root")

    with pytest.raises(Exception) as excinfo:
        _submit(engine, "get_layer_stackup", {
            "pdk_id": "noSuchPdk", "revision": "v1",
            "engine_root": str(engine_root),
        })
    assert getattr(excinfo.value, "code", None) == "unknown_pdk"
    _register_layer_pdk(tmp_path)
    with pytest.raises(Exception) as excinfo:
        _submit(engine, "apply_layer_preset", {
            "pdk_id": "sky130A", "revision": "v9",
            "engine_root": str(tmp_path / "root"), "name": "nope",
        })
    assert getattr(excinfo.value, "code", None) == "unknown_preset"
