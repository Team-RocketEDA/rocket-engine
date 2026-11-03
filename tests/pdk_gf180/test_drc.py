"""PDK-GF180 RED — lane proof: available-deck DRC run with goldens.

Valid RED = the lane profile does not exist yet, so the proof
fails on FileNotFoundError before touching KLayout. GREEN runs
the profile's engine stand-in rules (metal1 min-width/min-space,
read from profile data — no rule literals here) in KLayout batch
against three cells: the proof inverter (width 0, space total
pinned at the 16 PDK-interior corner hits, lane routing 0/0, with
the golden shape/net counts), a width dirty (a 0.10 um sliver must
trip min-width), and a space dirty (a 0.10 um gap must trip
min-space). Skips LOUDLY (never fake-green) where klayout or the
PDK is absent. This is NOT foundry signoff: no PDK deck ships
(see profile drc.deck_reason).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from ._profile import load_profile, require_pdk

RESULT_RE = re.compile(
    r"RESULT raw=(\d+) merged=(\d+) width=(\d+) space=(\d+) "
    r"lanewidth=(\d+) lanespace=(\d+)"
)


def _klayout_check(gds_path, rules, workdir):
    """Run profile engine rules on a GDS via KLayout batch; parse counts."""
    checks = "\n".join(
        f'results.append(run_rule({tuple(rule["layer"])}, '
        f'{rule["width_um"]}, {rule["space_um"]}))'
        for rule in rules
    )
    script = workdir / "engine_drc.py"
    script.write_text(
        "import pya\n"
        "ly = pya.Layout()\n"
        f"ly.read({str(gds_path)!r})\n"
        "top = ly.top_cell()\n"
        "def touches_lane(edge, lane):\n"
        "    box = edge.bbox()\n"
        "    box.enlarge(2, 2)\n"
        "    return not lane.interacting(pya.Region(box)).is_empty()\n"
        "def run_rule(layer, wmin_um, smin_um):\n"
        "    li = ly.layer(*layer)\n"
        "    reg = pya.Region(pya.RecursiveShapeIterator(ly, top, li))\n"
        "    merged = reg.merged()\n"
        "    lane = pya.Region(top.shapes(li))\n"
        "    wmin = int(wmin_um / ly.dbu + 0.5)\n"
        "    smin = int(smin_um / ly.dbu + 0.5)\n"
        "    w = merged.width_check(wmin)\n"
        "    s = merged.space_check(smin)\n"
        "    lw = sum(1 for ep in w.each()\n"
        "             if touches_lane(ep.first, lane)\n"
        "             or touches_lane(ep.second, lane))\n"
        "    ls = sum(1 for ep in s.each()\n"
        "             if touches_lane(ep.first, lane)\n"
        "             or touches_lane(ep.second, lane))\n"
        "    return (reg.count(), merged.count(),\n"
        "            w.count(), s.count(), lw, ls)\n"
        "results = []\n"
        f"{checks}\n"
        "raw = sum(r[0] for r in results)\n"
        "nets = sum(r[1] for r in results)\n"
        "w = sum(r[2] for r in results)\n"
        "s = sum(r[3] for r in results)\n"
        "lw = sum(r[4] for r in results)\n"
        "ls = sum(r[5] for r in results)\n"
        "print(f'RESULT raw={raw} merged={nets} width={w} space={s} '\n"
        "      f'lanewidth={lw} lanespace={ls}')\n"
    )
    proc = subprocess.run(
        ["klayout", "-b", "-r", str(script)],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    match = RESULT_RE.search(proc.stdout)
    assert match, proc.stdout[-2000:]
    return tuple(int(group) for group in match.groups())


@pytest.fixture()
def engine_rules():
    profile = load_profile()  # RED: missing profile.yaml
    return profile["variants"]["mcu"]["drc"]["engine_rules"]


@pytest.fixture()
def proof_gds(tmp_path):
    load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    if shutil.which("klayout") is None:
        pytest.skip("gf180 lane live: klayout batch not installed")
    from .fixtures.inv_pair import build_cell

    gds = tmp_path / "lane_inv_clean.gds"
    build_cell().write_gds(str(gds))
    return gds


def test_lane_drc_clean_matches_goldens(proof_gds, engine_rules, tmp_path):
    profile = load_profile()  # RED: missing profile.yaml
    goldens = profile["proofs"]["drc"]
    got = _klayout_check(proof_gds, engine_rules, tmp_path)
    raw, nets, width, space, lane_width, lane_space = got
    assert raw == goldens["metal1_raw_shapes"]
    assert nets == goldens["metal1_merged_nets"]
    assert width == goldens["width_violations"]
    # The stand-in 0.23 space rule exceeds what the PDK's own FET
    # corners satisfy (0.209 diagonal at gate contacts): the total is
    # pinned as observed PDK-interior behavior, while lane-drawn
    # routing must be violation-free.
    assert space == goldens["space_violations_total"]
    assert lane_width == goldens["width_violations_lane_routing"]
    assert lane_space == goldens["space_violations_lane_routing"]


def test_lane_drc_trips_min_width(engine_rules, tmp_path):
    load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    if shutil.which("klayout") is None:
        pytest.skip("gf180 lane live: klayout batch not installed")
    import gdsfactory as gf

    from gf180mcu.layers import LAYER

    dirty = gf.Component()
    dirty.add_polygon([(0, 0), (1.0, 0), (1.0, 0.10), (0, 0.10)],
                      layer=LAYER.metal1)
    gds = tmp_path / "lane_dirty_width.gds"
    dirty.write_gds(str(gds))
    _, _, width, _, lane_width, _ = _klayout_check(gds, engine_rules, tmp_path)
    assert width >= 1
    assert lane_width >= 1


def test_lane_drc_trips_min_space(engine_rules, tmp_path):
    load_profile()  # RED: missing profile.yaml
    require_pdk()  # skip LOUDLY when gf180mcu is truly absent
    if shutil.which("klayout") is None:
        pytest.skip("gf180 lane live: klayout batch not installed")
    import gdsfactory as gf

    from gf180mcu.layers import LAYER

    dirty = gf.Component()
    dirty.add_polygon([(0, 0), (1.0, 0), (1.0, 0.5), (0, 0.5)],
                      layer=LAYER.metal1)
    dirty.add_polygon([(0, 0.60), (1.0, 0.60), (1.0, 1.10), (0, 1.10)],
                      layer=LAYER.metal1)
    gds = tmp_path / "lane_dirty_space.gds"
    dirty.write_gds(str(gds))
    _, _, _, space, _, lane_space = _klayout_check(gds, engine_rules, tmp_path)
    assert space >= 1
    assert lane_space >= 1
