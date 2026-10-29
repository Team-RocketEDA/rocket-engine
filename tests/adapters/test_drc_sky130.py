"""DRC-SKY130 RED — real sky130A.lydrc through KlayoutDrcAdapter.

Valid RED = `KlayoutDrcAdapter` has no deck mode yet, so deck tests
fail (preflight demands synthetic rules, parse demands TOTAL).
Fixtures are hand-built minimal met1 cells on 68/20, verified
against real KLayout 0.28.16 + sky130A.lydrc: good->0, bad->1x m1.1.
Mined good (bandgap trivial_mos_array.gds, 4.9K) also verified clean
manually; committed cells are minimal for speed per *.gds ignore.
Tests skip (never fake-green) where klayout, fixtures, or the PDK
deck are absent; lyrdb parse units always run.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "drc_sky130"
DECK_REL = "libs.tech/klayout/drc/sky130A.lydrc"

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(not klayout_present, reason="klayout not installed")

CLEAN_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category>
   <name>m1.1</name>
   <description>m1.1 : min. m1 width : 0.14um</description>
  </category>
 </categories>
 <cells>
  <cell><name>TOP</name></cell>
 </cells>
 <items>
 </items>
</report-database>
"""

VIOL_LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
 <description>SKY130 DRC runset</description>
 <top-cell>TOP</top-cell>
 <categories>
  <category>
   <name>m1.1</name>
   <description>m1.1 : min. m1 width : 0.14um</description>
  </category>
 </categories>
 <cells>
  <cell><name>TOP</name></cell>
 </cells>
 <items>
  <item>
   <tags/>
   <category>'m1.1'</category>
   <cell>TOP</cell>
   <visited>false</visited>
   <multiplicity>1</multiplicity>
   <image/>
   <values>
    <value>edge-pair: (0,0;0,2)|(0.05,2;0.05,0)</value>
   </values>
  </item>
 </items>
</report-database>
"""


def _find_sky130_deck():
    try:
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
    except Exception:
        return None
    try:
        entries = list_pdks()
    except Exception:
        return None
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [e for e in entries if e.get("id") == "sky130a"]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        return None
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    try:
        hit = resolve_deck(entry["id"], entry["revision"], DECK_REL)
    except Exception:
        return None
    path = hit.get("path")
    return path if path and Path(path).is_file() else None


def _require_fixtures():
    for name in ("good.gds", "bad.gds"):
        if not (FIXTURES / name).is_file():
            pytest.skip(f"sky130 fixtures not generated: {name} (run make_cells.py)")


def _job(cell, tmp_path, deck_file):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds_file = workdir / f"{cell}.gds"
    shutil.copy(FIXTURES / f"{cell}.gds", gds_file)
    return {
        "operation": "run_drc",
        "tech": "sky130A",
        "cell": cell,
        "gds_file": str(gds_file),
        "workdir": str(workdir),
        "deck": {"tool": "klayout"},
        "deck_file": deck_file,
    }


@needs_klayout
def test_drc_sky130_preflight_accepts_deck_without_rules(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: no deck mode

    _require_fixtures()
    deck = _find_sky130_deck()
    if deck is None:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    checked = KlayoutDrcAdapter().preflight(_job("good", tmp_path, deck))
    assert checked.get("deck_file") == deck


@needs_klayout
def test_drc_sky130_good_cell_reports_zero(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: no deck mode

    _require_fixtures()
    deck = _find_sky130_deck()
    if deck is None:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    adapter = KlayoutDrcAdapter()
    result = adapter.parse(adapter.execute(_job("good", tmp_path, deck)))
    assert result["total"] == 0
    assert result["violations"] == []


@needs_klayout
def test_drc_sky130_bad_cell_reports_m1_1(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: no deck mode

    _require_fixtures()
    deck = _find_sky130_deck()
    if deck is None:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    adapter = KlayoutDrcAdapter()
    result = adapter.parse(adapter.execute(_job("bad", tmp_path, deck)))
    assert result["total"] >= 1
    assert any("m1.1" in v["rule"] for v in result["violations"])
    for violation in result["violations"]:
        assert len(violation["bbox_um"]) == 4


@needs_klayout
def test_drc_sky130_unknown_deck_raises_no_substitute(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: ignores deck_file

    _require_fixtures()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds_file = workdir / "good.gds"
    shutil.copy(FIXTURES / "good.gds", gds_file)
    job = {
        "operation": "run_drc",
        "gds_file": str(gds_file),
        "workdir": str(workdir),
        "deck": {"tool": "klayout"},
        "deck_file": str(tmp_path / "no-such-deck.lydrc"),
        "rules": {"layer": [1, 0], "width_um": 3.0, "space_um": 3.0},
    }
    try:
        KlayoutDrcAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing deck (no synthetic fallback)")


def test_drc_sky130_unknown_tool_raises():
    from rocket_engine.composition import Engine

    engine = Engine(project_id="sky130_demo", actor={"kind": "user"}, catalog_root=".")
    ack = engine.submit(
        {
            "project_id": "sky130_demo",
            "operation": "run_drc",
            "arguments": {
                "expected_revision": "p12",
                "target": {"scope": "project", "id": "good", "revision": "r1"},
            },
            "request_id": "sky130-unknown-tool",
        }
    )
    try:
        engine.run(
            {
                "project_id": "sky130_demo",
                "operation": "run_drc",
                "arguments": {"deck": {"tool": "no_such_tool"}},
                "snapshot_id": ack["snapshot_id"],
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for unknown deck tool")


def test_drc_sky130_parse_clean_report():
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: no lyrdb parse

    result = KlayoutDrcAdapter().parse({"report_xml": CLEAN_LYRDB})
    assert result["total"] == 0
    assert result["violations"] == []


def test_drc_sky130_parse_violation_report():
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: no lyrdb parse

    result = KlayoutDrcAdapter().parse({"report_xml": VIOL_LYRDB})
    assert result["total"] == 1
    assert len(result["violations"]) == 1
    violation = result["violations"][0]
    assert "m1.1" in violation["rule"]
    assert len(violation["bbox_um"]) == 4
    assert violation["bbox_um"][0] == 0.0
    assert violation["bbox_um"][2] == pytest.approx(0.05)


@needs_klayout
def test_drc_sky130_proves_fixture_labels_against_real_deck(tmp_path):
    # Oracle check: labels verified against klayout + real deck,
    # not against the adapter under test.
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # noqa: F401  # RED marker

    _require_fixtures()
    deck = _find_sky130_deck()
    if deck is None:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    for cell, want_items, want_rule in (
        ("good", 0, None),
        ("bad", 1, "m1.1"),
    ):
        report = tmp_path / f"oracle_{cell}.lyrdb"
        proc = subprocess.run(
            [
                "klayout",
                "-b",
                "-rd",
                f"input={FIXTURES / f'{cell}.gds'}",
                "-rd",
                f"report={report}",
                "-r",
                deck,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=tmp_path,
        )
        assert proc.returncode == 0
        assert report.is_file()
        text = report.read_text()
        assert text.count("<item>") == want_items
        if want_rule:
            assert want_rule in text
