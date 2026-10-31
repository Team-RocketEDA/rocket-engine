"""PDK-LXT live proofs: cell build + SAX model goldens + geometry sanity.

Provision-gated (VALIDATE-P precedent): without the PDK importable
these tests skip LOUDLY with the recipe pointer; with LXT_LIVE=1 a
missing provision fails instead of skipping. The repo env never
carries the PDK itself.

Proven (goldens measured from the pinned upstream, see report.md):
- layout: ltoi300 straight_rwg900_cband(L10) ports/bbox/layers;
- sim: matching SAX model at wl=1.55 with golden S-params;
- drc-shape: the built GDS passes a klayout-batch width/space
  SANITY check on the ridge layer (100 nm smoke threshold, not a
  design rule — the .lydrc deck itself stays gated, GUI run recipe
  documented in recipe.md, never faked);
- lnoi400: variant import, registry counts, straight build + model.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LIVE = os.environ.get("LXT_LIVE") == "1"
RECIPE_HINT = "provision per docs/pdk/lxt/recipe.md, then re-run with LXT_LIVE=1"

# Goldens measured 2026-10-31 from upstream d16db6a (gf 9.51.0,
# sax 0.18.2, gplugins 1.4.2 source, klayout 0.28.16); see report.md.
GOLDEN_PORTS = ("o1", "o2")
GOLDEN_PORT_WIDTH = 0.9
GOLDEN_O1_CENTER = (0.0, 0.0)
GOLDEN_O2_CENTER = (10.0, 0.0)
GOLDEN_RIDGE_LAYER = (2, 10)
GOLDEN_SLAB_LAYER = (3, 10)
GOLDEN_FULL_BBOX_UM = (10.0, 12.9)  # ridge 0.9 + slab offset 6.0/side
GOLDEN_RIDGE_BBOX_UM = [0.0, -0.45, 10.0, 0.45]
GOLDEN_CELLS = 26
GOLDEN_MODELS = 13
GOLDEN_S21_ABS = 0.9999424370  # 0.5 dB/cm over 10 um
GOLDEN_S21 = complex(0.9794735565993687, -0.20128693274788553)
GOLDEN_TOP_PREFIX = "straight_rwg900_cband"
GOLDEN_GDS_LAYERS = {"2/10": 1, "3/10": 1}

LNOI_CELLS = 23
LNOI_MODELS = 9
LNOI_BBOX_UM = (10.0, 10.0)
LNOI_LAYERS = {(2, 0), (3, 0)}
LNOI_S_ABS = 0.9999769744  # 0.2 dB/cm over 10 um


def _require_lxt():
    try:
        import ltoi300  # noqa: F401
    except ImportError as exc:
        if LIVE:
            pytest.fail(f"LXT_LIVE=1 but provision missing ({exc}): {RECIPE_HINT}")
        pytest.skip(f"lxt provision absent: {RECIPE_HINT}")
    import ltoi300

    return ltoi300


def _require_klayout():
    if shutil.which("klayout") is None:
        if LIVE:
            pytest.fail(f"LXT_LIVE=1 but klayout missing: {RECIPE_HINT}")
        pytest.skip("klayout not on PATH")


def _layers_of(comp):
    return {tuple(layer) for layer in comp.layers}


def test_cell_build_ports_bbox_layers():
    ltoi300 = _require_lxt()
    ltoi300.PDK.activate()
    assert len(ltoi300.PDK.cells) == GOLDEN_CELLS
    assert len(ltoi300.PDK.models) == GOLDEN_MODELS
    comp = ltoi300.cells.straight_rwg900_cband(length=10.0)
    assert tuple(sorted(p.name for p in comp.ports)) == GOLDEN_PORTS
    by_name = {p.name: p for p in comp.ports}
    assert by_name["o1"].width == pytest.approx(GOLDEN_PORT_WIDTH)
    assert tuple(by_name["o1"].center) == pytest.approx(GOLDEN_O1_CENTER)
    assert tuple(by_name["o2"].center) == pytest.approx(GOLDEN_O2_CENTER)
    assert tuple(by_name["o1"].layer) == GOLDEN_RIDGE_LAYER
    bbox = comp.bbox()
    assert (bbox.width(), bbox.height()) == pytest.approx(
        GOLDEN_FULL_BBOX_UM, abs=1e-6
    )
    assert _layers_of(comp) == {GOLDEN_RIDGE_LAYER, GOLDEN_SLAB_LAYER}


def test_model_is_sax_compatible_with_golden_sparams():
    ltoi300 = _require_lxt()
    import numpy as np

    model = ltoi300.PDK.models["straight_rwg900_cband"]
    sdict = model(wl=1.55)
    assert isinstance(sdict, dict)
    assert ("o2", "o1") in sdict  # forward transmission present
    s21 = complex(np.asarray(sdict[("o2", "o1")]).reshape(-1)[0])
    assert abs(s21) == pytest.approx(GOLDEN_S21_ABS, abs=1e-6)
    assert s21 == pytest.approx(GOLDEN_S21, abs=1e-6)
    # Reciprocal, no reflection: sax versions disagree on whether
    # self-pairs are present, so accept absent-or-zero either way.
    for pair in (("o1", "o1"), ("o2", "o2")):
        if pair in sdict:
            assert abs(complex(np.asarray(sdict[pair]).reshape(-1)[0])) == 0.0


def test_built_gds_passes_klayout_geometry_sanity(tmp_path):
    # Shape proof only: GDS readability, golden structure, and a
    # 100 nm width/space smoke check. NOT the gated DRC deck.
    ltoi300 = _require_lxt()
    _require_klayout()
    ltoi300.PDK.activate()
    comp = ltoi300.cells.straight_rwg900_cband(length=10.0)
    gds_path = tmp_path / "straight.gds"
    comp.write_gds(str(gds_path))
    script = tmp_path / "sanity.py"
    script.write_text(
        "import json, pya\n"
        "ly = pya.Layout()\n"
        f"ly.read({str(gds_path)!r})\n"
        "top = ly.top_cell()\n"
        "layers = {}\n"
        "for li in ly.layer_indexes():\n"
        "    info = ly.get_info(li)\n"
        "    n = pya.Region(top.begin_shapes_rec(li)).count()\n"
        "    if n:\n"
        "        layers['%d/%d' % (info.layer, info.datatype)] = n\n"
        "dbu = ly.dbu\n"
        "bb = top.bbox(ly.layer" + str(GOLDEN_RIDGE_LAYER) + ")\n"
        "print(json.dumps({'top': top.name, 'layers': layers,\n"
        "    'ridge_bbox_um': [bb.left * dbu, bb.bottom * dbu,\n"
        "                      bb.right * dbu, bb.top * dbu]}))\n"
        "reg = pya.Region(top.begin_shapes_rec(ly.layer"
        + str(GOLDEN_RIDGE_LAYER)
        + "))\n"
        "print('width_violations=%d' % reg.width_check(100).size())\n"
        "print('space_violations=%d' % reg.space_check(100).size())\n"
    )
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    struct = None
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            import json

            struct = json.loads(line)
    assert struct is not None, proc.stdout
    assert struct["top"].startswith(GOLDEN_TOP_PREFIX), struct["top"]
    assert struct["layers"] == GOLDEN_GDS_LAYERS, struct["layers"]
    assert struct["ridge_bbox_um"] == pytest.approx(GOLDEN_RIDGE_BBOX_UM)
    assert "width_violations=0" in proc.stdout
    assert "space_violations=0" in proc.stdout


def test_lnoi400_variant_build_and_model():
    _require_lxt()
    try:
        import lnoi400
    except ImportError as exc:
        if LIVE:
            pytest.fail(f"LXT_LIVE=1 but lnoi400 missing ({exc}): {RECIPE_HINT}")
        pytest.skip(f"lnoi400 absent: {RECIPE_HINT}")
    assert len(lnoi400.PDK.cells) == LNOI_CELLS
    assert len(lnoi400.PDK.models) == LNOI_MODELS
    assert "straight_rwg1000" in set(lnoi400.PDK.cells)
    assert "straight_rwg1000" in set(lnoi400.PDK.models)
    lnoi400.PDK.activate()
    comp = lnoi400.cells.straight_rwg1000(length=10.0)
    assert tuple(sorted(p.name for p in comp.ports)) == GOLDEN_PORTS
    bbox = comp.bbox()
    assert (bbox.width(), bbox.height()) == pytest.approx(LNOI_BBOX_UM, abs=1e-6)
    assert _layers_of(comp) == LNOI_LAYERS
    import numpy as np

    sdict = lnoi400.PDK.models["straight_rwg1000"](wl=1.55)
    assert ("o2", "o1") in sdict
    s_param = complex(np.asarray(sdict[("o2", "o1")]).reshape(-1)[0])
    assert abs(s_param) == pytest.approx(LNOI_S_ABS, abs=1e-6)


def test_proof_fixture_gds_matches_golden_structure(tmp_path):
    # The vendored proof fixture is the same cell, frozen: identical
    # golden structure must read back through klayout batch.
    _require_klayout()
    fixture = Path(__file__).resolve().parent / "fixtures" / "straight_L10.gds"
    assert fixture.is_file(), f"missing proof fixture: {fixture}"
    script = tmp_path / "struct_probe.py"
    script.write_text(
        "import json, pya\n"
        "ly = pya.Layout()\n"
        f"ly.read({str(fixture)!r})\n"
        "top = ly.top_cell()\n"
        "layers = {}\n"
        "for li in ly.layer_indexes():\n"
        "    info = ly.get_info(li)\n"
        "    n = pya.Region(top.begin_shapes_rec(li)).count()\n"
        "    if n:\n"
        "        layers['%d/%d' % (info.layer, info.datatype)] = n\n"
        "dbu = ly.dbu\n"
        "bb = top.bbox(ly.layer" + str(GOLDEN_RIDGE_LAYER) + ")\n"
        "print(json.dumps({'top': top.name, 'layers': layers,\n"
        "    'ridge_bbox_um': [bb.left * dbu, bb.bottom * dbu,\n"
        "                      bb.right * dbu, bb.top * dbu]}))\n"
    )
    try:
        proc = subprocess.run(
            ["klayout", "-b", "-r", str(script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr
    import json

    struct = json.loads(
        [line for line in proc.stdout.splitlines() if line.startswith("{")][-1]
    )
    assert struct["top"].startswith(GOLDEN_TOP_PREFIX), struct["top"]
    assert struct["layers"] == GOLDEN_GDS_LAYERS, struct["layers"]
    assert struct["ridge_bbox_um"] == pytest.approx(GOLDEN_RIDGE_BBOX_UM)
