"""LVS-ESCAPE RED — a bulk-net rename must FAIL LVS, not escape it.

Valid RED = `NetgenLvsAdapter.parse` trusts a netgen MATCH verdict
even when the two sides name different nets, so the inventory tests
below FAIL (match True where False is required) and the live seeds
PASS (escape). GREEN = the adapter compares the flattened net-name
sets and reports name-only-on-one-side nets as `lvs_net_mismatch`
violations, so 3/3 seeds FAIL with the renamed net named.

Why netgen alone cannot see it: netgen's one-shot `lvs` with
`permute default` matches by topology, and renaming a
singly-connected net (the lvs_inv single-pfet bulk VPB, the
single-nfet bulk VNB) preserves the topology exactly — the escape
is invisible to any isomorphism-based compare. The losing side is
the adapter surface (it dropped the name evidence), not the setup
file (no global/net-merging directives: see docs/probe-*.md); the
mutate operator shape is mirrored here, not changed.

Live tests skip (never fake-green) where netgen or the PDK setup
deck is absent; parse/inventory units always run.
"""

import os
import shutil
from pathlib import Path

import pytest

from tests.adapters.test_extract_sky130 import (
    MATCH_SAMPLE_REPORT,
    MISMATCH_SAMPLE_REPORT,
)

LVS_FIXTURES = Path(__file__).parent.parent / "mutate" / "fixtures" / "lvs_inv"

LAYOUT_NETS = ["A", "VGND", "VNB", "VPB", "VPWR", "Y"]

netgen_present = shutil.which("netgen") is not None
needs_netgen = pytest.mark.skipif(not netgen_present, reason="netgen not installed")


def _native(report, layout_nets, schematic_nets):
    return {
        "report_text": report,
        "layout_nets": list(layout_nets),
        "schematic_nets": list(schematic_nets),
    }


def test_escape_match_with_renamed_bulk_fails_names_net():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    schematic = [n for n in LAYOUT_NETS if n != "VPB"] + ["VPB_BAD"]
    result = NetgenLvsAdapter().parse(_native(MATCH_SAMPLE_REPORT, LAYOUT_NETS, schematic))
    assert result["match"] is False
    assert result["total"] >= 1
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
    assert any("VPB_BAD" in v["message"] for v in result["violations"])
    assert any("VPB" in v["message"] for v in result["violations"])


def test_escape_match_with_renamed_nfet_bulk_fails():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    schematic = [n for n in LAYOUT_NETS if n != "VNB"] + ["VNB_BAD"]
    result = NetgenLvsAdapter().parse(_native(MATCH_SAMPLE_REPORT, LAYOUT_NETS, schematic))
    assert result["match"] is False
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
    assert any("VNB_BAD" in v["message"] for v in result["violations"])


def test_escape_good_pair_still_passes():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    result = NetgenLvsAdapter().parse(
        _native(MATCH_SAMPLE_REPORT, LAYOUT_NETS, LAYOUT_NETS)
    )
    assert result["match"] is True
    assert result["total"] == 0
    assert result["violations"] == []


def test_escape_legacy_native_without_inventory_unchanged():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    result = NetgenLvsAdapter().parse({"report_text": MATCH_SAMPLE_REPORT})
    assert result["match"] is True
    assert result["violations"] == []


def test_escape_mismatch_report_keeps_netgen_verdict():
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    schematic = [n for n in LAYOUT_NETS if n != "VPB"] + ["VPB_BAD"]
    result = NetgenLvsAdapter().parse(
        _native(MISMATCH_SAMPLE_REPORT, LAYOUT_NETS, schematic)
    )
    assert result["match"] is False
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
    assert any("VPB_BAD" in v["message"] for v in result["violations"])


def test_inventory_nets_reads_x_lines_only():
    from rocket_engine.adapters.lvs_netgen import inventory_nets

    text = (
        "* comment line with VPB_BAD must not leak into the inventory\n"
        ".subckt inv_min A Y VPWR VGND VPB VNB\n"
        "X0 Y A VPWR VPB_BAD sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n"
        "X1 Y A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15\n"
        ".ends\n"
    )
    assert inventory_nets(text) == {"Y", "A", "VPWR", "VPB_BAD", "VGND", "VNB"}


def _resolve_setup():
    try:
        from rocket_engine.interfaces.pdks import list_pdks, resolve_deck
        from rocket_engine.interfaces.paths import slugify
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    want_rev = os.environ.get("SKY130_PDK_REVISION")
    candidates = [
        e for e in entries if slugify(e.get("id") or "") == "sky130a"
    ]
    if want_rev:
        candidates = [e for e in candidates if e.get("revision") == want_rev]
    if not candidates:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    entry = sorted(candidates, key=lambda e: e["revision"])[0]
    try:
        hit = resolve_deck(entry["id"], entry["revision"], "libs.tech/netgen/sky130A_setup.tcl")
    except Exception:
        pytest.skip("sky130 netgen setup deck not resolved")
    path = hit.get("path")
    if not path or not Path(path).is_file():
        pytest.skip("sky130 netgen setup deck missing on disk")
    return path


@needs_netgen
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_escape_seeds_fail_live(tmp_path, seed):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter
    from rocket_engine.mutate import apply_operator

    setup = _resolve_setup()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = workdir / "layout.spice"
    layout.write_bytes((LVS_FIXTURES / "layout.spice").read_bytes())
    dest = tmp_path / "mut"
    evidence = apply_operator("netlist_lvs_mismatch", dest, seed, LVS_FIXTURES)
    mutated = dest / "schematic.spice"
    assert evidence["bad_net"] in mutated.read_text()

    adapter = NetgenLvsAdapter()
    job = {
        "operation": "run_lvs",
        "layout_spice": str(layout),
        "schematic_spice": str(mutated),
        "setup_file": setup,
        "workdir": str(workdir),
    }
    result = adapter.parse(adapter.execute(job))
    assert result["match"] is False, seed
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"]), seed
    assert any(evidence["bad_net"] in v["message"] for v in result["violations"]), seed


@needs_netgen
def test_escape_good_pair_passes_live(tmp_path):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    setup = _resolve_setup()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = workdir / "layout.spice"
    layout.write_bytes((LVS_FIXTURES / "layout.spice").read_bytes())
    schematic = workdir / "schematic.spice"
    schematic.write_bytes((LVS_FIXTURES / "schematic.spice").read_bytes())
    adapter = NetgenLvsAdapter()
    result = adapter.parse(
        adapter.execute(
            {
                "operation": "run_lvs",
                "layout_spice": str(layout),
                "schematic_spice": str(schematic),
                "setup_file": setup,
                "workdir": str(workdir),
            }
        )
    )
    assert result["match"] is True
    assert result["violations"] == []
