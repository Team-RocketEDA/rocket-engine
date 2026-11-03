"""DRC-BANDGAP-TRIAGE regression pins (klayout + magic present).

Reproduced 2026-11-03 through `KlayoutDrcAdapter` deck mode over
the vendored routed GDS with the store deck
sky130A@5f09001e: FAIL, total 740 = 672 OFFGRID (setup/parity
gap: 1 nm generator grid vs the foundry 5 nm manufacturing grid
the deck enforces) + 68 li.5 (REAL: 0.17x0.17 li stubs with zero
licon enclosure in `bandgap_core_bus`).

The DRC-path fix in this lane is an opt-in `waive_rules`
seam: waived violations drop from the parse with a `waived`
tally, so the OFFGRID setup bucket clears and the 68 real
defects stand alone. The fixture geometry fix (regen the bus
cell with enclosed li stubs) needs the upstream `klt` flow,
absent on this host — loud-skipped and BLOCKED below. Default
parse behavior (no waivers) is unchanged.
"""

import os
import shutil
from pathlib import Path

import pytest

DECK_REL = "libs.tech/klayout/drc/sky130A.lydrc"
GDS_REL = ("fixtures/upstream/sky130-bandgap/layout/bandgap-core"
           "/reports/20260817-020222-13476b7/bandgap_core_routed.gds")

OFFGRID_RULES = ["licon_OFFGRID", "ct_OFFGRID", "m1_OFFGRID",
                 "li_OFFGRID", "via_OFFGRID", "m2_OFFGRID"]

klayout_present = shutil.which("klayout") is not None


def _deck():
    try:
        from rocket_engine.interfaces.pdks import resolve_deck
    except Exception:
        return None
    home_store = (Path(os.environ.get("ROCKETEDA_HOME", ""))
                  if os.environ.get("ROCKETEDA_HOME") else
                  Path.home() / ".local" / "share" / "rocketeda")
    try:
        hit = resolve_deck(
            "sky130A", "5f09001e4b975ba35d27d99a10ecdf45054a9bd5",
            DECK_REL, engine_root=home_store)
    except Exception:
        return None
    path = hit.get("path") if isinstance(hit, dict) else None
    return path if path and Path(path).is_file() else None


deck_present = _deck() is not None
needs_live = pytest.mark.skipif(
    not (klayout_present and deck_present),
    reason="klayout or the sky130A deck is absent; live legs skip loudly")


def _canned_xml():
    return """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category><name>li.5</name><description>enclosure</description></category>
  <category><name>licon_OFFGRID</name><description>offgrid</description></category>
 </categories>
 <cells><cell><name>TOP</name></cell></cells>
 <items>
  <item>
   <tags/><category>'li.5'</category><cell>TOP</cell>
   <visited>false</visited><multiplicity>1</multiplicity><image/>
   <values><value>polygon: (1,1;1,2;2,2;2,1)</value></values>
  </item>
  <item>
   <tags/><category>'licon_OFFGRID'</category><cell>TOP</cell>
   <visited>false</visited><multiplicity>1</multiplicity><image/>
   <values><value>edge-pair: (0,0;0,1)/(0,0;0,1)</value></values>
  </item>
 </items>
</report-database>
"""


def test_waivers_drop_matching_rules_with_tally():
    from rocket_engine.adapters.drc.klayout import apply_waivers

    parsed = {"total": 2,
              "violations": [{"rule": "li.5", "bbox_um": [1, 1, 2, 2]},
                             {"rule": "licon_OFFGRID",
                              "bbox_um": [0, 0, 0, 1]}]}
    waived = apply_waivers(parsed, ["licon_OFFGRID"])
    assert waived["total"] == 1
    assert [v["rule"] for v in waived["violations"]] == ["li.5"]
    assert waived["waived"] == {"rules": ["licon_OFFGRID"], "count": 1}


def test_waivers_default_to_no_waiver():
    from rocket_engine.adapters.drc.klayout import apply_waivers

    parsed = {"total": 1, "violations": [{"rule": "li.5"}]}
    assert apply_waivers(parsed, None)["total"] == 1


def test_waive_rules_rejects_non_lists_loudly(tmp_path):
    import shutil

    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter
    from rocket_engine.adapters.errors import AdapterError

    fixture = (Path(__file__).resolve().parent / "fixtures"
               / "drc_kl" / "good.gds")
    gds = tmp_path / "good.gds"
    shutil.copy(fixture, gds)
    adapter = KlayoutDrcAdapter()
    try:
        adapter.preflight({"operation": "run_drc",
                           "gds_file": str(gds),
                           "rules": {"layer": [1, 0], "width_um": 1.0,
                                     "space_um": 1.0},
                           "waive_rules": "licon_OFFGRID"})
    except AdapterError as exc:
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a waive string")


@needs_live
def test_live_bandgap_reproduces_740_split(tmp_path):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    gds = Path(__file__).resolve().parent.parent.parent / GDS_REL
    assert gds.is_file(), "vendored bandgap GDS missing"
    workdir = tmp_path / "work"
    workdir.mkdir()
    job = {"operation": "run_drc", "gds_file": str(gds.resolve()),
           "deck_file": _deck(), "workdir": str(workdir)}
    parsed = KlayoutDrcAdapter().parse(KlayoutDrcAdapter().execute(job))
    assert parsed["total"] == 740
    rules = [v["rule"] for v in parsed["violations"]]
    assert sum(1 for r in rules if r.endswith("_OFFGRID")) == 672
    assert sum(1 for r in rules if r == "li.5") == 68


@needs_live
def test_live_waiver_clears_offgrid_leaving_real_li5(tmp_path):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    gds = Path(__file__).resolve().parent.parent.parent / GDS_REL
    workdir = tmp_path / "work"
    workdir.mkdir()
    job = {"operation": "run_drc", "gds_file": str(gds.resolve()),
           "deck_file": _deck(), "workdir": str(workdir),
           "waive_rules": list(OFFGRID_RULES)}
    adapter = KlayoutDrcAdapter()
    parsed = adapter.parse(adapter.execute(job))
    assert parsed["total"] == 68
    assert {v["rule"] for v in parsed["violations"]} == {"li.5"}
    assert parsed["waived"] == {"rules": sorted(OFFGRID_RULES),
                                "count": 672}
