"""PDK-CSPDK lane proof: KLayout DRC run with golden expectations (RED-first).

si340 ships tech.lyt + layers.lyp but no runnable local deck (upstream
DRC runs through the gdsfactoryplus cloud workflow, which the engine
must never touch), so the lane runs the engine KLayout batch check
(KlayoutDrcAdapter, run_drc) with the profile's engine rules — GDS 3/0,
350 nm feature / 200 nm gap from the 49th-call guidelines Table 4.

RED = the lane profile/fixture are missing, so the run fails before
KLayout starts. GREEN = the reference MZI is clean (0 violations) and
a synthesized bad layout trips exactly one width + one space violation
at the golden bboxes. Skips LOUDLY where klayout is unavailable.
"""

import shutil

import pytest

from ._profile import FIXTURES, load_profile

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(
    not klayout_present, reason="klayout binary not found"
)

REF_TOTAL = 0
BAD_TOTAL = 2
BAD_WIDTH_BBOX = [0.0, 0.0, 10.0, 0.1]
BAD_SPACE_BBOX = [25.0, 0.0, 25.1, 5.0]


def _rules():
    profile = load_profile()  # RED gate: rules come from the profile.
    rule = profile["variants"]["si340"]["drc"]["engine_rules"][0]
    return {
        "layer": list(rule["layer"]),
        "width_um": float(rule["width_um"]),
        "space_um": float(rule["space_um"]),
        "name": rule["name"],
    }


def _run_drc(gds_file, rules, workdir):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    adapter = KlayoutDrcAdapter()
    native = adapter.execute(
        {
            "operation": "run_drc",
            "gds_file": str(gds_file),
            "rules": rules,
            "workdir": str(workdir),
        }
    )
    return adapter.parse(native)


@needs_klayout
def test_si340_reference_mzi_is_drc_clean(tmp_path):
    rules = _rules()
    ref = FIXTURES / "mzi_ref.gds"
    assert ref.is_file(), f"lane fixture missing: {ref}"
    parsed = _run_drc(ref, rules, tmp_path)
    assert parsed["total"] == REF_TOTAL
    assert parsed["violations"] == []


@needs_klayout
def test_si340_bad_layout_trips_width_and_space(tmp_path):
    kdb = pytest.importorskip("klayout.db")
    rules = _rules()
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("bad")
    layer = layout.layer(3, 0)
    top.shapes(layer).insert(kdb.Box(0, 0, 10000, 100))
    top.shapes(layer).insert(kdb.Box(20000, 0, 25000, 5000))
    top.shapes(layer).insert(kdb.Box(25100, 0, 30100, 5000))
    bad = tmp_path / "bad.gds"
    layout.write(str(bad))

    parsed = _run_drc(bad, rules, tmp_path)
    assert parsed["total"] == BAD_TOTAL
    by_rule = {v["rule"]: v["bbox_um"] for v in parsed["violations"]}
    assert by_rule[f"{rules['name']}_width"] == pytest.approx(BAD_WIDTH_BBOX)
    assert by_rule[f"{rules['name']}_space"] == pytest.approx(BAD_SPACE_BBOX)
