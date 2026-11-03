"""MIXED-TOP RED — deck-mode cell honor + m4.5ab/xschem triage pins.

Valid RED = `KlayoutDrcAdapter.preflight` drops `cell` in deck
mode today, so the honor/refusal tests below fail (no `cell` in
the checked mapping, no multi-top refusal). The m4.5ab and
xschem legs pin triage evidence: a recorded-rule parse unit plus
live probes that skip loudly (never fake-green) where the
foundry deck or xschem is absent.

Triage verdicts live in docs/tickets/MIXED-TOP-TRIAGE.md; method
notes in docs/probe-mixed-top.md.
"""

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "drc_kl"

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(not klayout_present, reason="klayout not installed")

M45AB_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
<categories>
<category><name>m4.5ab</name><description>min. 3um m4 spacing m4 : 0.4um</description></category>
</categories>
<items>
<item><category>m4.5ab</category><multiplicity>1</multiplicity>
<values><value>shape 188.6,197.205;190.0,197.205</value></values></item>
</items>
</report-database>
"""


def _deck_job(tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds = workdir / "single.gds"
    shutil.copy(FIXTURES / "good.gds", gds)
    deck = workdir / "fake.lydrc"
    deck.write_text("pass\n")
    job = {
        "operation": "run_drc",
        "gds_file": str(gds),
        "deck_file": str(deck),
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def test_deck_mode_honors_cell_matching_single_top(tmp_path):
    """Deck + cell naming the single top cell proceeds with cell kept."""
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    checked = KlayoutDrcAdapter().preflight(_deck_job(tmp_path, cell="TOP"))
    assert checked["deck_file"].endswith("fake.lydrc")
    assert checked.get("cell") == "TOP"


def test_deck_mode_refuses_unknown_cell(tmp_path):
    """Deck + cell absent from the GDS refuses loudly, never mistargets."""
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    try:
        KlayoutDrcAdapter().preflight(_deck_job(tmp_path, cell="GHOST"))
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
        assert "GHOST" in str(exc)
    else:
        raise AssertionError("expected invalid_reference for a missing cell")


def test_deck_mode_refuses_multi_top_without_cell(tmp_path):
    """Multi-top GDS with no cell refuses instead of checking top_cell."""
    pytest.importorskip("pya")
    import pya

    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = pya.Layout()
    layout.dbu = 0.001
    for name in ("TOP_A", "TOP_B"):
        cell = layout.create_cell(name)
        cell.shapes(layout.layer(1, 0)).insert(pya.Box(0, 0, 3000, 3000))
    gds = workdir / "multi.gds"
    layout.write(str(gds))
    deck = workdir / "fake.lydrc"
    deck.write_text("pass\n")
    job = {
        "operation": "run_drc",
        "gds_file": str(gds),
        "deck_file": str(deck),
        "workdir": str(workdir),
    }
    try:
        KlayoutDrcAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
        assert "TOP_A" in str(exc) or "multi" in str(exc).lower()
    else:
        raise AssertionError("expected invalid_command for multi-top without cell")


def test_m45ab_recorded_rule_parses_with_bbox():
    """The mixed-lane m4.5ab signature parses to a ruled bbox violation."""
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    result = KlayoutDrcAdapter().parse({"report_xml": M45AB_LYRDB})
    assert result["total"] == 1
    (violation,) = result["violations"]
    assert violation["rule"] == "m4.5ab"
    assert "0.4um" in violation["message"]
    assert len(violation["bbox_um"]) == 4


def test_mixed_top_drc_needs_foundry_deck_or_skips(tmp_path):
    """m4.5ab leg: foundry deck absent here → loud skip, never fake-green."""
    from rocket_engine.adapters import drc as _  # noqa: F401  (package seam)
    from rocket_engine.interfaces.pdks import resolve_deck

    try:
        hit = resolve_deck("sky130a", "5f09001e", "libs.tech/klayout/drc/sky130A.lydrc")
    except Exception:
        pytest.skip("foundry deck not resolved on this host (BLOCKED-needs-host)")
    assert Path(hit.get("path", "")).is_file()


def test_xschem_hierarchical_netlists_with_wrapper_rcfile(tmp_path):
    """sd_top-shaped hierarchy netlists once SHAREDIR is pinned (live)."""
    from rocket_engine.adapters.xschem import XschemAdapter

    if shutil.which("xschem") is None:
        pytest.skip("xschem not installed")
    leaf_sym = (
        "v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {type=subcircuit\n"
        "format=\"@name @pinlist @symname\"\ntemplate=\"name=X\"}\n"
        "V {}\nS {}\nE {}\n"
        "B 5 -60 -130 130 40 {name=dummy}\n"
    )
    adapter = XschemAdapter()
    workdir = tmp_path / "work"
    (workdir / "cells").mkdir(parents=True)
    (workdir / "cells" / "leaf.sym").write_text(
        leaf_sym + "T {@symname} 0 -100 0 0 0.3 0.3 {}\n"
        "T {@name} 0 100 0 0 0.3 0.3 {}\n"
        "T {@pinlist} 0 130 0 0 0.2 0.2 {}\n"
    )
    (workdir / "cells" / "top.sch").write_text(
        "v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\n"
        "C {cells/leaf.sym} 0 0 0 0 {name=X0}\n"
    )
    project_rc = workdir / "xschemrc"
    project_rc.write_text("set XSCHEM_SHAREDIR /nonexistent/xschem\n")
    native = adapter.execute(
        {
            "operation": "run_xschem",
            "sch_file": str(workdir / "cells" / "top.sch"),
            "rcfile": str(project_rc),
            "workdir": str(workdir),
        }
    )
    assert Path(native["netlist_file"]).is_file()
    assert "leaf" in Path(native["netlist_file"]).read_text().lower()
