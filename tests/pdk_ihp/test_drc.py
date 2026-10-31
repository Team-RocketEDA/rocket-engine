"""PDK-IHP RED — DRC position: engine M1.a/M1.b checks + deck honesty.

Valid RED = profile/fixture missing (FileNotFoundError) or klayout
unimportable (loud skip). The PDK's own KLayout deck ships locally
but needs the `euclidean` DRC metric, which neither sandbox KLayout
(system 0.28.16 nor nix 0.30.7) provides — so the deck cannot run
here and the profile marks it needs-newer-klayout. The live proof
runs engine-side width/space checks with the deck's own values
(M1.a = 0.16 um, M1.b = 0.18 um on GDS 8/0, from rule_decks
5_16_metal1.drc + sg13g2_tech_default.json): the reference fixture
is clean, a synthesized dirty layout trips exactly one width and
one space violation at golden bboxes.
"""

import importlib.util

import pytest

from ._profile import FIXTURES, load_profile

kl_present = importlib.util.find_spec("klayout.db") is not None
needs_kl = pytest.mark.skipif(
    not kl_present, reason="engine DRC checks need the klayout python package"
)


def _m1_violations(path, width_um, space_um):
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(path))
    top = layout.top_cell()
    dbu = layout.dbu
    region = kdb.Region(top.begin_shapes_rec(layout.find_layer(8, 0)))
    width = region.width_check(int(round(width_um / dbu)))
    space = region.space_check(int(round(space_um / dbu)))

    def boxes(edges):
        return sorted(
            (
                round(e.bbox().left * dbu, 4),
                round(e.bbox().bottom * dbu, 4),
                round(e.bbox().right * dbu, 4),
                round(e.bbox().top * dbu, 4),
            )
            for e in edges.each()
        )

    return boxes(width), boxes(space)


def _engine_rules():
    profile = load_profile()  # RED: missing profile.yaml
    rules = {
        r["name"]: r
        for r in profile["variants"]["bicmos"]["drc"]["engine_rules"]
    }
    assert rules["M1.a"]["width_um"] == 0.16
    assert rules["M1.b"]["space_um"] == 0.18
    return rules


@needs_kl
def test_reference_fixture_is_m1_clean():
    _engine_rules()  # RED: missing profile.yaml
    fixture = FIXTURES / "nmos_ref.gds"
    if not fixture.is_file():
        raise FileNotFoundError(f"IHP proof fixture not found: {fixture}")
    width, space = _m1_violations(fixture, 0.16, 0.18)
    assert width == []
    assert space == []


@needs_kl
def test_dirty_layout_trips_golden_m1_violations(tmp_path):
    _engine_rules()  # RED: missing profile.yaml
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("dirty_m1")
    layer = layout.layer(8, 0)
    top.shapes(layer).insert(kdb.DBox(0, 0, 2.0, 0.10))  # M1.a: 100 nm wide
    top.shapes(layer).insert(kdb.DBox(0, 1.0, 2.0, 1.5))  # bar A
    top.shapes(layer).insert(kdb.DBox(0, 1.6, 2.0, 2.1))  # bar B: 100 nm gap
    dirty = tmp_path / "dirty_m1.gds"
    layout.write(str(dirty))
    width, space = _m1_violations(dirty, 0.16, 0.18)
    assert width == [(0.0, 0.0, 2.0, 0.1)]
    assert space == [(0.0, 1.5, 2.0, 1.6)]


@needs_kl
def test_fixture_matches_upstream_nmos_shape():
    load_profile()  # RED: missing profile.yaml
    import klayout.db as kdb

    fixture = FIXTURES / "nmos_ref.gds"
    if not fixture.is_file():
        raise FileNotFoundError(f"IHP proof fixture not found: {fixture}")
    layout = kdb.Layout()
    layout.read(str(fixture))
    top = layout.top_cell()
    assert top.name == "nmos"
    dbu = layout.dbu
    box = top.bbox()
    got = [box.left * dbu, box.bottom * dbu, box.right * dbu, box.top * dbu]
    assert got == pytest.approx([0.0, -0.105, 0.87, 0.405], abs=1e-9)
    shapes = {
        f"{layout.get_info(li).layer}/{layout.get_info(li).datatype}": sum(
            1 for _s in top.each_shape(li)
        )
        for li in layout.layer_indexes()
    }
    shapes = {k: v for k, v in shapes.items() if v}
    assert shapes == {
        "1/0": 3,
        "5/0": 1,
        "5/2": 1,
        "51/0": 2,
        "6/0": 2,
        "8/0": 2,
        "8/2": 2,
    }
