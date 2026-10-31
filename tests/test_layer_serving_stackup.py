"""LAYER-SERVING RED — layer stackup + preset serving for viewer + 3D.

Tests assume `rocket_engine.interfaces.layer_serving_stackup` with:
  LayerServingError, STACKUP_VERSION, PRESET_VERSION, BUILTIN_PRESETS,
  parse_lyp, parse_lyt, parse_xsect, build_stackup,
  get_stackup_from_dir, get_stackup, builtin_preset, PresetStore,
  viewer_rows, viewer_rows_for_preset.
Valid RED = the import itself fails: the surface does not exist yet.

Policy under test (docs/tickets/LAYER-SERVING.md): the engine serves
per-PDK Stackup (ordered layers, metal/tech grouping, enabled set,
colors, Z heights) read-only from PDK truth (KLayout .lyp/.lyt +
xsection .xs via the PDK store); LAYER_PRESET{layers, renderLayers,
flip, active} mirroring KiCad's with built-ins (All/None/All-metal/
Top/Bottom) + user save/overwrite/delete and explicit apply; viewer
rows driven by the same schemas. The PDK remains truth: no user fork
of the stackup, no guessed heights (missing xsect serves explicit
z_complete=False, never invented Z).

Committed tests use tiny synthetic lyp/lyt/xs fixtures only. The
12G user tree (~/.local/share/pdk/sky130A) is parsed read-only when
present (never copied); the registered-store test skips unless a
sky130a entry already exists.
"""

import copy

import pytest

TINY_LYP = """<?xml version="1.0" encoding="utf-8"?>
<layer-properties>
 <properties>
  <frame-color>#aabbcc</frame-color>
  <fill-color>#ddeeff</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>diff.drawing - 65/20</name>
  <source>65/20@1</source>
 </properties>
 <properties>
  <frame-color>#112233</frame-color>
  <fill-color>#445566</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>poly.drawing - 66/20</name>
  <source>66/20@1</source>
 </properties>
 <properties>
  <frame-color>#223344</frame-color>
  <fill-color>#556677</fill-color>
  <valid>true</valid>
  <visible>false</visible>
  <name>li1.drawing - 67/20</name>
  <source>67/20@1</source>
 </properties>
 <properties>
  <frame-color>#334455</frame-color>
  <fill-color>#667788</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>mcon.drawing - 67/44</name>
  <source>67/44@1</source>
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
  <frame-color>#445566</frame-color>
  <fill-color>#778899</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>via.drawing - 68/44</name>
  <source>68/44@1</source>
 </properties>
 <properties>
  <frame-color>#999999</frame-color>
  <fill-color>#999999</fill-color>
  <valid>false</valid>
  <visible>false</visible>
  <name>met1.fill - 68/30</name>
  <source>68/30@1</source>
 </properties>
 <properties>
  <frame-color>#ccccd9</frame-color>
  <fill-color>#ccccd9</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>prBoundary.boundary - 235/4</name>
  <source>235/4@1</source>
 </properties>
 <properties>
  <frame-color>#123456</frame-color>
  <fill-color>#654321</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>mydev.drawing - 99/0</name>
  <source>99/0@1</source>
 </properties>
</layer-properties>
"""

TINY_LYT = """<?xml version="1.0" encoding="utf-8"?>
<technology>
 <name>sky130</name>
 <dbu>0.001</dbu>
 <layer-properties_file>sky130A.lyp</layer-properties_file>
</technology>
"""

# Subset of the sky130 xsection variables: enough for poly/li1/mcon/met1
# spans; via intentionally lacks its recipe vars (partial-Z coverage).
TINY_XS = """
diff   = layer("65/20")
poly   = layer("66/20")
li1    = layer("67/20")
mcon   = layer("67/44")
met1   = layer("68/20")
via    = layer("68/44")

gox_thickness = 0.004
poly_thickness = 0.18
bpsg_thickness = 0.94
li_thickness = 0.1
ild2_thickness = 0.43
m1_thickness = 0.36
li_bottom = bpsg_thickness
m1_bottom = li_bottom + ild2_thickness

m_poly = mask(poly).grow(poly_thickness, 0.0)
output("22/0", m_poly)
"""

# Full conductor recipe vars (values from the sky130 xsection script):
# every canonical conductor/contact resolves, so z_complete is True.
FULL_XS = TINY_XS + """
met2   = layer("69/20")
via2   = layer("69/44")
met3   = layer("70/20")
via3   = layer("70/44")
met4   = layer("71/20")
via4   = layer("71/44")
met5   = layer("72/20")
licon1 = layer("66/44")

m2_thickness = 0.36
ild3_thickness = 0.27 + m1_thickness
m3_thickness = 0.845
ild4_thickness = 0.42 + m2_thickness
m4_thickness = 0.845
ild5_thickness = 0.39 + m3_thickness
m5_thickness = 1.26
ild6_thickness = 0.505 + m4_thickness
m2_bottom = m1_bottom + ild3_thickness
m3_bottom = m2_bottom + ild4_thickness
m4_bottom = m3_bottom + ild5_thickness
m5_bottom = m4_bottom + ild6_thickness
"""

FULL_LYP_EXTRA = """
 <properties>
  <frame-color>#010101</frame-color>
  <fill-color>#010101</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>licon1.drawing - 66/44</name>
  <source>66/44@1</source>
 </properties>
 <properties>
  <frame-color>#020202</frame-color>
  <fill-color>#020202</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met2.drawing - 69/20</name>
  <source>69/20@1</source>
 </properties>
 <properties>
  <frame-color>#030303</frame-color>
  <fill-color>#030303</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>via2.drawing - 69/44</name>
  <source>69/44@1</source>
 </properties>
 <properties>
  <frame-color>#040404</frame-color>
  <fill-color>#040404</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met3.drawing - 70/20</name>
  <source>70/20@1</source>
 </properties>
 <properties>
  <frame-color>#050505</frame-color>
  <fill-color>#050505</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>via3.drawing - 70/44</name>
  <source>70/44@1</source>
 </properties>
 <properties>
  <frame-color>#060606</frame-color>
  <fill-color>#060606</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met4.drawing - 71/20</name>
  <source>71/20@1</source>
 </properties>
 <properties>
  <frame-color>#070707</frame-color>
  <fill-color>#070707</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>via4.drawing - 71/44</name>
  <source>71/44@1</source>
 </properties>
 <properties>
  <frame-color>#080808</frame-color>
  <fill-color>#080808</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met5.drawing - 72/20</name>
  <source>72/20@1</source>
 </properties>
"""

FULL_LYP = TINY_LYP.replace("</layer-properties>", FULL_LYP_EXTRA + "</layer-properties>")


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _tiny_stackup(**overrides):
    from rocket_engine.interfaces.layer_serving_stackup import build_stackup

    kwargs = {
        "pdk_id": "tiny130A",
        "revision": "v1",
        "lyp_text": TINY_LYP,
        "lyt_text": TINY_LYT,
        "xsect_text": TINY_XS,
    }
    kwargs.update(overrides)
    return build_stackup(**kwargs)


def _full_stackup():
    from rocket_engine.interfaces.layer_serving_stackup import build_stackup

    return build_stackup(
        pdk_id="tiny130A",
        revision="v1",
        lyp_text=FULL_LYP,
        lyt_text=TINY_LYT,
        xsect_text=FULL_XS,
    )


# --- .lyp parsing: order, colors, flags, purposes ---

def test_parse_lyp_orders_colors_and_flags():
    from rocket_engine.interfaces.layer_serving_stackup import parse_lyp  # RED: missing

    entries = parse_lyp(TINY_LYP)["entries"]
    assert [e["name"] for e in entries] == [
        "diff.drawing", "poly.drawing", "li1.drawing", "mcon.drawing",
        "met1.drawing", "via.drawing", "met1.fill", "prBoundary.boundary",
        "mydev.drawing",
    ]
    met1 = entries[4]
    assert met1["base"] == "met1" and met1["purpose"] == "drawing"
    assert (met1["layer"], met1["datatype"]) == (68, 20)
    assert met1["frame"] == "#0000ff" and met1["fill"] == "#0000ff"
    assert met1["valid"] is True and met1["visible"] is True
    assert entries[2]["visible"] is False  # li1 hidden in the PDK default
    assert entries[6]["valid"] is False  # met1.fill not PDK-enabled
    assert entries[8]["label"] == "mydev.drawing - 99/0"


def test_parse_lyp_rejects_malformed():
    from rocket_engine.interfaces.layer_serving_stackup import parse_lyp  # RED: missing

    with pytest.raises(Exception) as excinfo:
        parse_lyp("this is not xml <")
    assert _code(excinfo) == "invalid_stackup"
    missing_source = TINY_LYP.replace("<source>68/20@1</source>", "")
    with pytest.raises(Exception) as excinfo:
        parse_lyp(missing_source)
    assert _code(excinfo) == "invalid_stackup"
    assert "met1.drawing" in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        parse_lyp("<layer-properties></layer-properties>")
    assert _code(excinfo) == "invalid_stackup"


# --- .lyt parsing: tech + dbu ---

def test_parse_lyt_reads_tech_and_dbu():
    from rocket_engine.interfaces.layer_serving_stackup import parse_lyt  # RED: missing

    assert parse_lyt(TINY_LYT) == {
        "tech": "sky130",
        "dbu_um": pytest.approx(0.001),
        "layer_properties": "sky130A.lyp",
    }
    with pytest.raises(Exception) as excinfo:
        parse_lyt("<technology><name>x</name></technology>")
    assert _code(excinfo) == "invalid_stackup"


# --- .xs parsing: inputs, arithmetic, spans ---

def test_parse_xsect_evaluates_arithmetic():
    from rocket_engine.interfaces.layer_serving_stackup import parse_xsect  # RED: missing

    parsed = parse_xsect(TINY_XS)
    assert parsed["inputs"][(66, 20)] == "poly"
    assert parsed["inputs"][(68, 44)] == "via"
    assert parsed["values"]["m1_bottom"] == pytest.approx(0.94 + 0.43)
    assert parsed["values"]["li_bottom"] == pytest.approx(0.94)


def test_parse_xsect_ignores_process_calls_and_outputs():
    from rocket_engine.interfaces.layer_serving_stackup import parse_xsect  # RED: missing

    parsed = parse_xsect(TINY_XS)
    assert "m_poly" not in parsed["values"]  # mask()/grow() line skipped
    assert "output" not in parsed["values"]


def test_parse_xsect_unknown_variable_is_loud():
    from rocket_engine.interfaces.layer_serving_stackup import parse_xsect  # RED: missing

    with pytest.raises(Exception) as excinfo:
        parse_xsect('poly = layer("66/20")\nfoo_bottom = bar_bottom + 1.0\n')
    assert _code(excinfo) == "invalid_stackup"
    assert "bar_bottom" in str(excinfo.value)


def test_parse_xsect_spans_follow_recipe():
    from rocket_engine.interfaces.layer_serving_stackup import parse_xsect  # RED: missing

    spans = parse_xsect(FULL_XS)["spans"]
    assert spans["poly"]["z_base_um"] == pytest.approx(0.004)
    assert spans["poly"]["z_top_um"] == pytest.approx(0.184)
    assert spans["li1"]["z_base_um"] == pytest.approx(0.94)
    assert spans["mcon"]["z_base_um"] == pytest.approx(0.94)
    assert spans["mcon"]["z_top_um"] == pytest.approx(0.94 + 0.43)
    assert spans["met1"]["thickness_um"] == pytest.approx(0.36)
    assert spans["licon1"]["z_base_um"] == pytest.approx(0.0)
    assert spans["licon1"]["z_top_um"] == pytest.approx(0.94)
    # Vias span the ILD between neighboring metals, never guessed.
    assert spans["via"]["z_base_um"] == pytest.approx(spans["met1"]["z_base_um"])
    assert spans["via"]["z_top_um"] == pytest.approx(spans["met2"]["z_base_um"])
    assert spans["met5"]["z_base_um"] > spans["met4"]["z_base_um"]
    assert "xsect:" in spans["poly"]["z_source"]


# --- stackup assembly: grouping, enabled, Z order, read-only ---

def test_build_stackup_groups_and_enabled():
    stackup = _tiny_stackup()  # RED: missing surface

    assert stackup["stackup_version"] == 1
    assert stackup["pdk_id"] == "tiny130A" and stackup["revision"] == "v1"
    assert stackup["dbu_um"] == pytest.approx(0.001)
    assert stackup["groups"]["metal"] == ["li1.drawing", "met1.drawing", "met1.fill"]
    assert stackup["groups"]["via"] == ["mcon.drawing", "via.drawing"]
    assert stackup["groups"]["frontend"] == ["diff.drawing", "poly.drawing"]
    assert stackup["groups"]["tech"] == ["prBoundary.boundary"]
    assert stackup["groups"]["other"] == ["mydev.drawing"]
    assert "met1.fill" not in stackup["enabled"]  # valid=false excluded
    assert len(stackup["enabled"]) == len(stackup["layers"]) - 1
    by_name = {layer["name"]: layer for layer in stackup["layers"]}
    assert by_name["met1.drawing"]["gds"] == [68, 20]
    assert by_name["met1.drawing"]["color"] == {
        "frame": "#0000ff", "fill": "#0000ff",
    }


def test_build_stackup_z_order_and_stack_index():
    stackup = _tiny_stackup()  # RED: missing surface

    by_name = {layer["name"]: layer for layer in stackup["layers"]}
    assert by_name["poly.drawing"]["z_base_um"] == pytest.approx(0.004)
    assert by_name["poly.drawing"]["stack_index"] == 0
    assert by_name["li1.drawing"]["stack_index"] == 1
    # Tie (li1 base == mcon base) breaks by file order, never by hash.
    assert by_name["mcon.drawing"]["stack_index"] == 2
    assert by_name["met1.drawing"]["stack_index"] == 3
    assert by_name["diff.drawing"]["z_base_um"] is None  # FEOL: no span
    assert by_name["diff.drawing"]["stack_index"] is None
    assert by_name["via.drawing"]["z_base_um"] is None  # recipe vars absent
    assert stackup["z_complete"] is False  # partial recipe coverage
    assert stackup["z_reason"]


def test_full_stackup_reports_z_complete():
    stackup = _full_stackup()  # RED: missing surface

    assert stackup["z_complete"] is True
    by_name = {layer["name"]: layer for layer in stackup["layers"]}
    bases = [by_name[f"met{n}.drawing"]["z_base_um"] for n in range(1, 6)]
    assert bases == sorted(bases)
    assert by_name["met5.drawing"]["stack_index"] == max(
        layer["stack_index"] for layer in stackup["layers"]
        if layer["stack_index"] is not None
    )


def test_build_stackup_without_xsect_serves_no_heights():
    stackup = _tiny_stackup(xsect_text=None)  # RED: missing surface

    assert all(layer["z_base_um"] is None for layer in stackup["layers"])
    assert stackup["z_complete"] is False
    assert "xsect" in stackup["z_reason"]


def test_build_stackup_is_read_only():
    first = _tiny_stackup()  # RED: missing surface
    first["layers"][0]["visible"] = not first["layers"][0]["visible"]
    first["enabled"].clear()

    second = _tiny_stackup()
    assert second["layers"][0]["visible"] is True
    assert len(second["enabled"]) == len(second["layers"]) - 1
    assert second == _tiny_stackup()


def test_build_stackup_rejects_duplicate_names():
    from rocket_engine.interfaces.layer_serving_stackup import build_stackup  # RED

    doubled = TINY_LYP.replace("</layer-properties>", """
 <properties>
  <frame-color>#000000</frame-color>
  <fill-color>#000000</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>met1.drawing - 68/20</name>
  <source>68/20@1</source>
 </properties>
</layer-properties>""")
    with pytest.raises(Exception) as excinfo:
        build_stackup(pdk_id="x", revision="v1", lyp_text=doubled)
    assert _code(excinfo) == "invalid_stackup"
    assert "met1.drawing" in str(excinfo.value)


# --- PDK-tree + store serving ---

SKY130A_RELS = {
    "lyp": "libs.tech/klayout/tech/sky130A.lyp",
    "lyt": "libs.tech/klayout/tech/sky130A.lyt",
    "xsect": "libs.tech/klayout/tech/xsect/sky130.xs",
}


def _write_tree(root):
    for key, rel in SKY130A_RELS.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = {"lyp": FULL_LYP, "lyt": TINY_LYT, "xsect": FULL_XS}[key]
        target.write_text(text)
    return root


def test_stackup_from_dir_reads_pdk_tree(tmp_path):
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        get_stackup_from_dir,
    )

    stackup = get_stackup_from_dir("sky130A", "v1", _write_tree(tmp_path / "pdk"))
    assert stackup["pdk_id"] == "sky130A" and stackup["z_complete"] is True
    assert stackup["source"]["kind"] == "pdk-dir"
    with pytest.raises(Exception) as excinfo:
        get_stackup_from_dir("otherPdk", "v1", tmp_path / "pdk")
    assert _code(excinfo) == "unknown_stackup"


def test_stackup_from_dir_missing_lyp_is_loud(tmp_path):
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        get_stackup_from_dir,
    )

    root = tmp_path / "pdk"
    (root / "libs.tech").mkdir(parents=True)
    with pytest.raises(Exception) as excinfo:
        get_stackup_from_dir("sky130A", "v1", root)
    assert _code(excinfo) == "unknown_stackup"
    assert SKY130A_RELS["lyp"] in str(excinfo.value)


def test_get_stackup_prefers_newest_revision_and_echoes_it(tmp_path):
    from rocket_engine.interfaces.layer_serving_stackup import get_stackup  # RED: missing
    from rocket_engine.interfaces.pdks import register_pdk

    engine_root = tmp_path / "root"
    register_pdk(_write_tree(tmp_path / "src_v1"), "sky130A", "v1",
                 engine_root=engine_root)
    register_pdk(_write_tree(tmp_path / "src_v2"), "sky130A", "v2",
                 engine_root=engine_root)
    latest = get_stackup("sky130A", engine_root=engine_root)
    assert latest["revision"] == "v2" and latest["z_complete"] is True
    assert latest["source"]["kind"] == "pdk-store"
    assert latest["source"]["sha256"][SKY130A_RELS["lyp"]]
    pinned = get_stackup("sky130a", "v1", engine_root=engine_root)
    assert pinned["revision"] == "v1"


def test_get_stackup_unknown_pdk_raises_unknown_pdk(tmp_path):
    from rocket_engine.interfaces.layer_serving_stackup import get_stackup  # RED: missing
    from rocket_engine.interfaces.pdks import ensure_engine_root

    engine_root = ensure_engine_root(tmp_path / "root")
    with pytest.raises(Exception) as excinfo:
        get_stackup("noSuchPdk", "v1", engine_root=engine_root)
    assert _code(excinfo) == "unknown_pdk"


def test_get_stackup_unmapped_pdk_raises_unknown_stackup(tmp_path):
    from rocket_engine.interfaces.layer_serving_stackup import get_stackup  # RED: missing
    from rocket_engine.interfaces.pdks import register_pdk

    engine_root = tmp_path / "root"
    source = tmp_path / "src"
    (source / "libs.tech").mkdir(parents=True)
    (source / "libs.tech" / "note.txt").write_text("no klayout tech here\n")
    register_pdk(source, "otherPdk", "v1", engine_root=engine_root)
    with pytest.raises(Exception) as excinfo:
        get_stackup("otherPdk", "v1", engine_root=engine_root)
    assert _code(excinfo) == "unknown_stackup"


# --- built-in presets ---

def test_builtin_names_are_pinned():
    from rocket_engine.interfaces.layer_serving_stackup import BUILTIN_PRESETS  # RED

    assert tuple(BUILTIN_PRESETS) == ("All", "None", "All-metal", "Top", "Bottom")


def test_builtin_all_none_metal_round_trip():
    from rocket_engine.interfaces.layer_serving_stackup import builtin_preset  # RED

    stackup = _tiny_stackup()
    all_preset = builtin_preset(stackup, "All")
    assert all_preset["preset_version"] == 1 and all_preset["builtin"] is True
    assert all_preset["flip"] is False and all_preset["active"] is None
    assert set(all_preset["layers"]) == {layer["name"] for layer in stackup["layers"]}
    assert all_preset["layers"]["met1.drawing"] is True
    assert all_preset["layers"]["met1.fill"] is False  # not PDK-enabled
    none_preset = builtin_preset(stackup, "None")
    assert set(none_preset["layers"].values()) == {False}
    metal = builtin_preset(stackup, "All-metal")
    assert metal["layers"]["met1.drawing"] is True
    assert metal["layers"]["via.drawing"] is True
    assert metal["layers"]["poly.drawing"] is False
    assert metal["layers"]["met1.fill"] is False  # group matches, enabled wins
    assert metal["renderLayers"]["grid"] is True


def test_builtin_top_bottom_carry_flip_and_active():
    from rocket_engine.interfaces.layer_serving_stackup import builtin_preset  # RED

    stackup = _full_stackup()
    top = builtin_preset(stackup, "Top")
    assert top["flip"] is False
    assert top["active"] == "met5.drawing"
    assert top["layers"]["met5.drawing"] is True
    assert top["layers"]["prBoundary.boundary"] is True
    assert top["layers"]["met1.drawing"] is False
    bottom = builtin_preset(stackup, "Bottom")
    assert bottom["flip"] is True
    assert bottom["active"] == "poly.drawing"
    assert bottom["layers"]["poly.drawing"] is True
    assert bottom["layers"]["diff.drawing"] is True
    assert bottom["layers"]["met5.drawing"] is False


def test_builtin_without_heights_carries_no_active():
    from rocket_engine.interfaces.layer_serving_stackup import builtin_preset  # RED

    stackup = _tiny_stackup(xsect_text=None)
    assert builtin_preset(stackup, "Top")["active"] is None
    assert builtin_preset(stackup, "Bottom")["active"] is None


def test_builtin_unknown_name_lists_builtins():
    from rocket_engine.interfaces.layer_serving_stackup import builtin_preset  # RED

    with pytest.raises(Exception) as excinfo:
        builtin_preset(_tiny_stackup(), "Front")
    assert _code(excinfo) == "unknown_preset"
    assert "All" in str(excinfo.value)


# --- user presets: save/overwrite/delete + explicit apply ---

def test_preset_save_round_trip_and_overwrite():
    from rocket_engine.interfaces.layer_serving_stackup import PresetStore  # RED

    store = PresetStore()
    stackup = _tiny_stackup()
    saved = store.save(stackup, "mine", {"met1.drawing": True}, flip=True,
                       active="met1.drawing")
    assert saved["builtin"] is False
    applied = store.apply(stackup, "mine")
    assert applied["flip"] is True and applied["active"] == "met1.drawing"
    assert applied["layers"]["met1.drawing"] is True
    assert applied["layers"]["poly.drawing"] is False  # sparse saves hide rest
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "mine", {"poly.drawing": True})
    assert _code(excinfo) == "preset_conflict"
    store.save(stackup, "mine", {"poly.drawing": True}, overwrite=True)
    assert store.apply(stackup, "mine")["layers"]["poly.drawing"] is True


def test_preset_save_rejects_builtin_names():
    from rocket_engine.interfaces.layer_serving_stackup import PresetStore  # RED

    store = PresetStore()
    stackup = _tiny_stackup()
    for name in ("All", "None", "All-metal", "Top", "Bottom"):
        with pytest.raises(Exception) as excinfo:
            store.save(stackup, name, {}, overwrite=True)
        assert _code(excinfo) == "preset_conflict"


def test_preset_save_validates_names_and_shapes():
    from rocket_engine.interfaces.layer_serving_stackup import PresetStore  # RED

    store = PresetStore()
    stackup = _tiny_stackup()
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "bad", {"nope.drawing": True})
    assert _code(excinfo) == "invalid_preset"
    assert "nope.drawing" in str(excinfo.value)
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "bad", {}, render_layers={"grid": "yes"})
    assert _code(excinfo) == "invalid_preset"
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "bad", {}, flip="yes")
    assert _code(excinfo) == "invalid_preset"
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "bad", {}, active="nope.drawing")
    assert _code(excinfo) == "invalid_preset"
    with pytest.raises(Exception) as excinfo:
        store.save(stackup, "  ", {})
    assert _code(excinfo) == "invalid_preset"


def test_preset_delete_removes_only_user():
    from rocket_engine.interfaces.layer_serving_stackup import PresetStore  # RED

    store = PresetStore()
    stackup = _tiny_stackup()
    store.save(stackup, "mine", {})
    assert store.delete("mine") == {"deleted": "mine"}
    with pytest.raises(Exception) as excinfo:
        store.delete("mine")
    assert _code(excinfo) == "unknown_preset"
    with pytest.raises(Exception) as excinfo:
        store.delete("All")
    assert _code(excinfo) == "preset_conflict"


def test_preset_apply_validates_against_current_stackup():
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        PresetStore,
        build_stackup,
    )

    store = PresetStore()
    stackup = _tiny_stackup()
    store.save(stackup, "mine", {"mydev.drawing": True})
    shrunk = build_stackup(pdk_id="tiny130A", revision="v2",
                           lyp_text=TINY_LYP.replace("""
 <properties>
  <frame-color>#123456</frame-color>
  <fill-color>#654321</fill-color>
  <valid>true</valid>
  <visible>true</visible>
  <name>mydev.drawing - 99/0</name>
  <source>99/0@1</source>
 </properties>
""", ""))
    with pytest.raises(Exception) as excinfo:
        store.apply(shrunk, "mine")
    assert _code(excinfo) == "invalid_preset"
    assert "mydev.drawing" in str(excinfo.value)


def test_preset_list_orders_builtins_first():
    from rocket_engine.interfaces.layer_serving_stackup import PresetStore  # RED

    store = PresetStore()
    store.save(_tiny_stackup(), "mine", {})
    assert store.list_presets() == [
        {"name": "All", "builtin": True},
        {"name": "None", "builtin": True},
        {"name": "All-metal", "builtin": True},
        {"name": "Top", "builtin": True},
        {"name": "Bottom", "builtin": True},
        {"name": "mine", "builtin": False},
    ]


# --- viewer rows ---

def test_viewer_rows_default_to_lyp_visibility():
    from rocket_engine.interfaces.layer_serving_stackup import viewer_rows  # RED

    page = viewer_rows(_tiny_stackup())
    assert [row["name"] for row in page["rows"]] == [
        layer["name"] for layer in _tiny_stackup()["layers"]
    ]
    by_name = {row["name"]: row for row in page["rows"]}
    assert by_name["li1.drawing"]["visible"] is False  # PDK default honored
    assert by_name["met1.drawing"]["visible"] is True
    assert by_name["met1.drawing"]["active"] is False
    assert by_name["met1.drawing"]["gds"] == [68, 20]
    assert by_name["met1.drawing"]["group"] == "metal"
    assert by_name["met1.drawing"]["color"] == {
        "frame": "#0000ff", "fill": "#0000ff",
    }
    assert by_name["met1.drawing"]["stack_index"] == 3
    assert page["active"] is None and page["flip"] is False


def test_viewer_rows_overrides_and_active():
    from rocket_engine.interfaces.layer_serving_stackup import viewer_rows  # RED

    page = viewer_rows(_tiny_stackup(),
                       visibility={"li1.drawing": True}, active="li1.drawing")
    by_name = {row["name"]: row for row in page["rows"]}
    assert by_name["li1.drawing"]["visible"] is True
    assert by_name["li1.drawing"]["active"] is True
    assert sum(1 for row in page["rows"] if row["active"]) == 1
    with pytest.raises(Exception) as excinfo:
        viewer_rows(_tiny_stackup(), visibility={"nope": True})
    assert _code(excinfo) == "invalid_visibility"
    with pytest.raises(Exception) as excinfo:
        viewer_rows(_tiny_stackup(), active="nope")
    assert _code(excinfo) == "invalid_visibility"


def test_viewer_rows_for_preset_applies_explicitly():
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        PresetStore,
        viewer_rows_for_preset,
    )

    store = PresetStore()
    stackup = _full_stackup()
    page = viewer_rows_for_preset(store, stackup, "Bottom")
    assert page["flip"] is True and page["active"] == "poly.drawing"
    by_name = {row["name"]: row for row in page["rows"]}
    assert by_name["poly.drawing"]["visible"] is True
    assert by_name["met5.drawing"]["visible"] is False
    assert by_name["poly.drawing"]["active"] is True
    overridden = viewer_rows_for_preset(store, stackup, "Bottom",
                                        overrides={"met5.drawing": True},
                                        active="met5.drawing")
    assert overridden["flip"] is True  # overrides never clear the preset flip
    assert overridden["active"] == "met5.drawing"
    assert {row["name"]: row["visible"] for row in overridden["rows"]}[
        "met5.drawing"] is True


# --- sky130A completeness (live PDK truth, skipped when absent) ---

def _user_tree_files():
    from pathlib import Path

    root = Path.home() / ".local" / "share" / "pdk" / "sky130A"
    paths = {key: root / rel for key, rel in SKY130A_RELS.items()}
    if all(path.is_file() for path in paths.values()):
        return paths
    return None


def _registered_sky130a_revision():
    try:
        from rocket_engine.interfaces.pdks import list_pdks
        from rocket_engine.interfaces.paths import slugify
    except Exception:
        return None
    try:
        entries = list_pdks()
    except Exception:
        return None
    revisions = sorted(e["revision"] for e in entries
                       if slugify(e.get("id") or "") == "sky130a")
    return revisions[-1] if revisions else None


CANONICAL_DRAWING = [
    "diff.drawing", "tap.drawing", "nwell.drawing", "poly.drawing",
    "licon1.drawing", "li1.drawing", "mcon.drawing",
    "met1.drawing", "via.drawing", "met2.drawing", "via2.drawing",
    "met3.drawing", "via3.drawing", "met4.drawing", "via4.drawing",
    "met5.drawing", "pad.drawing",
]


def test_sky130a_stackup_complete_from_user_tree():
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        PresetStore,
        build_stackup,
        viewer_rows_for_preset,
    )

    paths = _user_tree_files()
    if paths is None:
        pytest.skip("sky130A user tree not present (no copy in the suite)")
    stackup = build_stackup(
        pdk_id="sky130A",
        revision="user-tree",
        lyp_text=paths["lyp"].read_text(),
        lyt_text=paths["lyt"].read_text(),
        xsect_text=paths["xsect"].read_text(),
    )
    by_name = {layer["name"]: layer for layer in stackup["layers"]}
    for name in CANONICAL_DRAWING:
        assert name in by_name, name
        assert by_name[name]["enabled"] is True, name
    assert stackup["z_complete"] is True
    metals = [by_name[f"met{n}.drawing"] for n in range(1, 6)]
    bases = [layer["z_base_um"] for layer in metals]
    assert bases == sorted(bases)
    assert by_name["poly.drawing"]["z_top_um"] < by_name["li1.drawing"]["z_base_um"]
    for color in (layer["color"] for layer in stackup["layers"]):
        assert color["frame"].startswith("#") and color["fill"].startswith("#")
    for group in ("metal", "via", "frontend", "tech"):
        assert stackup["groups"][group] != [], group
    store = PresetStore()
    page = viewer_rows_for_preset(store, stackup, "All-metal")
    visible = {row["name"] for row in page["rows"] if row["visible"]}
    assert "met3.drawing" in visible and "poly.drawing" not in visible


def test_sky130a_stackup_from_registered_store():
    from rocket_engine.interfaces.layer_serving_stackup import get_stackup  # RED

    revision = _registered_sky130a_revision()
    if revision is None:
        pytest.skip("no registered sky130a entry (ROCKETEDA_HOME)")
    stackup = get_stackup("sky130A", revision)
    assert stackup["z_complete"] is True
    assert stackup["source"]["sha256"][SKY130A_RELS["lyp"]]
    assert {layer["name"] for layer in stackup["layers"]} >= set(CANONICAL_DRAWING)


def test_layer_serving_error_carries_stable_codes():
    from rocket_engine.interfaces.layer_serving_stackup import (  # RED: missing
        LayerServingError,
    )

    assert LayerServingError("unknown_stackup", "x").code == "unknown_stackup"
