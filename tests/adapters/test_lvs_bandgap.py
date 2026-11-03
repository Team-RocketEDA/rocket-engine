"""LVS-BANDGAP RED — engine-extraction leg: hierarchy + bulk typing.

Valid RED = `flatten_hierarchy` and `retype_by_bulk` do not exist
yet (and `inventory_nets` ignores M-lines), so the hierarchy and
retype tests below fail on ImportError/empty results while the
single-wrapper identity tests already pass.

Why: Wave-1 (docs/probe-extract-gds.md) unblocked extraction but
handed LVS two loud gaps: the engine-extracted bandgap netlist is
hierarchical (18 subckts; `flatten_spice` only strips a single
wrapper) and uniformly p-typed (68x `pfet_01v8` w=30 l=20) while
magic's own bulk grouping is exactly 52 devices on one common
bulk plus 8 pairs — mirroring the klt 52-pfet/16-nfet split.
Bulk nets adjudicate: bulk-on-VSS devices are n-type. M-line
inventory covers the klt/reference format both bandgap sides use.

Live tests skip (never fake-green) where netgen is absent; the
full bandgap match stays BLOCKED on setup mapping (see verdict).
"""

import shutil
from pathlib import Path

import pytest

# Synthetic engine-extracted shape: top instantiates two leaves; the
# leaves carry uniform-pfet X-lines whose bulk nets split into one
# common p-bulk (VDD, 4 devices) plus VSS-bulked devices that the klt
# split calls nfet. Mirrors the Wave-1 bulk-grouping evidence.
HIER_SPICE = """* engine-extracted hierarchical layout (synthetic bandgap shape)
.subckt leaf_amp IN OUT VDD VSS
X0 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
X1 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
.ends leaf_amp
.subckt leaf_bus A B VDD VSS
X0 B A VSS VSS sky130_fd_pr__pfet_01v8 w=30 l=20
X1 B A VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
.ends leaf_bus
.subckt bandgap_mini OUT VDD VSS
XAMP OUT OUT VDD VSS leaf_amp
XBUS OUT OUT VDD VSS leaf_bus
.ends bandgap_mini
"""

FLAT_SPICE = """* flat reference side
X0 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
X1 OUT IN VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
X2 B A VSS VSS sky130_fd_pr__nfet_01v8 w=30 l=20
X3 B A VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
"""

KLT_M_SPICE = """* klt/reference M-device format (bandgap pair shape)
.subckt mini_core VOUT VDD VSS
MMP1 D1 VB TAIL VDD pfet L=10U W=20U m=8
MMN1 D1 D1 VSS VSS nfet L=20U W=8U m=4
RR1 VBQ VB VSS 14026.89 res_high_po
QQ1 VSS VSS VA pnp AE=3.6992P PE=21.76U NE=8
.ends mini_core
"""

netgen_present = shutil.which("netgen") is not None
needs_netgen = pytest.mark.skipif(not netgen_present, reason="netgen not installed")


def test_flatten_hierarchy_inlines_leaf_instances():
    """Hierarchical ext2spice output flattens to top-level devices."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy

    flat = flatten_hierarchy(HIER_SPICE)
    assert ".subckt" not in flat.lower()
    assert ".ends" not in flat.lower()
    x_lines = [line for line in flat.splitlines() if line.startswith("X")]
    assert len(x_lines) == 4
    assert "leaf_amp" not in flat
    assert "leaf_bus" not in flat


def test_flatten_hierarchy_selects_uninstantiated_root():
    """The never-instantiated block is the top without a cell arg."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy

    flat = flatten_hierarchy(HIER_SPICE, top="bandgap_mini")
    assert ".subckt" not in flat.lower()
    assert len([line for line in flat.splitlines() if line.startswith("X")]) == 4
    assert "XAMP_X0" in flat
    assert "XBUS_X0" in flat


def test_flatten_hierarchy_ambiguous_roots_raise():
    """Two never-instantiated blocks without top refuse to guess."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy

    lib = HIER_SPICE + HIER_SPICE.replace("bandgap_mini", "other_top")
    try:
        flatten_hierarchy(lib)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for ambiguous roots")


def test_flatten_hierarchy_missing_top_raises():
    """An unknown top cell refuses instead of flattening wrongly."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy

    try:
        flatten_hierarchy(HIER_SPICE, top="no_such_cell")
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a missing top")


def test_flatten_hierarchy_single_wrapper_is_identity():
    """Already-flat netlists pass through unchanged in shape."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy

    flat = flatten_hierarchy(FLAT_SPICE)
    assert len([line for line in flat.splitlines() if line.startswith("X")]) == 4


def test_retype_by_bulk_fixes_uniform_pfet():
    """Bulk-on-VSS devices re-type to nfet; p-bulk devices keep pfet."""
    from rocket_engine.adapters.lvs_netgen import retype_by_bulk

    text, count = retype_by_bulk(
        FLAT_SPICE.replace(
            "X2 B A VSS VSS sky130_fd_pr__nfet_01v8", "X2 B A VSS VSS sky130_fd_pr__pfet_01v8"
        ),
        n_bulk_nets={"VSS", "VNB"},
        p_bulk_nets={"VDD", "VPB", "VPWR"},
    )
    assert count == 1
    lines = [line for line in text.splitlines() if line.startswith("X2")]
    assert len(lines) == 1
    assert "nfet" in lines[0]
    assert "pfet" not in lines[0]


def test_retype_by_bulk_preserves_flavor_suffix():
    """Retype keeps the variant suffix (hvt stays hvt)."""
    from rocket_engine.adapters.lvs_netgen import retype_by_bulk

    text, count = retype_by_bulk(
        "X0 Y A VSS VSS sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n",
        n_bulk_nets={"VSS"},
        p_bulk_nets={"VDD"},
    )
    assert count == 1
    assert "sky130_fd_pr__nfet_01v8_hvt" in text


def test_retype_by_bulk_leaves_unknown_bulks_untouched():
    """Bulk nets outside both families never re-type (conservative)."""
    from rocket_engine.adapters.lvs_netgen import retype_by_bulk

    line = "X0 Y A MID MIDBULK sky130_fd_pr__pfet_01v8 w=1 l=0.15\n"
    text, count = retype_by_bulk(
        line, n_bulk_nets={"VSS"}, p_bulk_nets={"VDD"}
    )
    assert count == 0
    assert text == line


def test_retype_by_bulk_correct_typing_is_identity():
    """The inv_2 good path (correct bulks) survives retype unchanged."""
    from rocket_engine.adapters.lvs_netgen import retype_by_bulk

    text = (
        "X0 Y A VPWR VPB sky130_fd_pr__pfet_01v8_hvt w=1 l=0.15\n"
        "X1 Y A VGND VNB sky130_fd_pr__nfet_01v8 w=0.65 l=0.15\n"
    )
    out, count = retype_by_bulk(
        text, n_bulk_nets={"VGND", "VNB", "VSS"}, p_bulk_nets={"VPWR", "VPB", "VDD"}
    )
    assert count == 0
    assert out == text


def test_inventory_nets_counts_m_device_lines():
    """The klt/reference M format contributes nets like X lines do."""
    from rocket_engine.adapters.lvs_netgen import inventory_nets

    # R/Q cards (RR1, QQ1) carry VBQ/VA but stay outside the X/M
    # inventory by design: name evidence comes from device lines.
    assert inventory_nets(KLT_M_SPICE) == {
        "D1", "VB", "TAIL", "VDD", "VSS",
    }


def test_inventory_nets_still_ignores_comments_and_dot_lines():
    """M-line support does not leak comments or dot cards into nets."""
    from rocket_engine.adapters.lvs_netgen import inventory_nets

    text = "* comment VGHOST\n.subckt x A\nM0 A B C D nfet w=1\n.ends\n"
    assert inventory_nets(text) == {"A", "B", "C", "D"}


# The execute leg maps HIER_SPICE to exactly this flat text: leaf
# instances inline with qualified names, the VSS-bulked device
# re-typed to nfet, p-bulked devices kept.
EXPECTED_FLAT = """XAMP_X0 OUT OUT VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
XAMP_X1 OUT OUT VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
XBUS_X0 OUT OUT VSS VSS sky130_fd_pr__nfet_01v8 w=30 l=20
XBUS_X1 OUT OUT VDD VDD sky130_fd_pr__pfet_01v8 w=30 l=20
"""


def test_flatten_then_retype_matches_expected():
    """The full engine leg maps the synthetic shape exactly, no netgen."""
    from rocket_engine.adapters.lvs_netgen import flatten_hierarchy, retype_by_bulk

    flat = flatten_hierarchy(HIER_SPICE)
    text, count = retype_by_bulk(
        flat, {"VSS", "VNB"}, {"VDD", "VPB", "VPWR"}
    )
    assert text == EXPECTED_FLAT
    assert count == 1


@needs_netgen
def test_bandgap_engine_leg_matches_live(tmp_path):
    """Hierarchical uniform-pfet layout vs flat reference: MATCH live.

    The execute leg hierarchy-flattens and bulk-retypes before the
    one-shot LVS, so the engine-extracted shape compares clean.
    """
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = workdir / "layout.spice"
    layout.write_text(HIER_SPICE)
    schematic = workdir / "schematic.spice"
    schematic.write_text(
        ".subckt bandgap_mini OUT VDD VSS\n" + EXPECTED_FLAT + ".ends\n"
    )
    setup = workdir / "mini.tcl"
    setup.write_text("permute default\n")
    job = {
        "operation": "run_lvs",
        "layout_spice": str(layout),
        "schematic_spice": str(schematic),
        "setup_file": str(setup),
        "workdir": str(workdir),
        "cell": "bandgap_mini",
        "bulk_nets": {"n": ["VSS", "VNB"], "p": ["VDD", "VPB", "VPWR"]},
    }
    result = NetgenLvsAdapter().parse(NetgenLvsAdapter().execute(job))
    assert result["match"] is True
    assert result["violations"] == []


@needs_netgen
def test_bandgap_klt_pair_still_mismatches_without_setup_mapping(tmp_path):
    """klt M-device pair vs reference FAILS: setup-mapping gap, pinned.

    Both bandgap sides are flat M-format; netgen with a bare setup
    cannot combine/map them (229 vs ~28 devices upstream). This pins
    the BLOCKED leg: the adapter reports faithfully, the fix belongs
    to the setup/deck surface, not the adapter.
    """
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    fixture = (
        Path(__file__).parent.parent.parent
        / "fixtures"
        / "upstream"
        / "sky130-bandgap"
        / "layout"
        / "bandgap-core"
        / "reports"
        / "20260817-020222-13476b7"
    )
    if not (fixture / "reference.spice").is_file():
        pytest.skip("bandgap fixture not fetched")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    setup = workdir / "mini.tcl"
    setup.write_text("permute default\n")
    job = {
        "operation": "run_lvs",
        "layout_spice": str(fixture / "bandgap_core_routed.extract.spice"),
        "schematic_spice": str(fixture / "reference.spice"),
        "setup_file": str(setup),
        "workdir": str(workdir),
    }
    result = NetgenLvsAdapter().parse(NetgenLvsAdapter().execute(job))
    assert result["match"] is False
    assert result["total"] >= 1
    assert any(v["rule"] == "lvs_net_mismatch" for v in result["violations"])
