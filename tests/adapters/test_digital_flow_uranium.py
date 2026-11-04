"""DIGITAL-FLOW-URANIUM readout tests — verdicts from machine files only.

Every gate verdict must derive from run-dir machine files
(state_out.json, metrics.csv, state views, signoff JSON reports);
report text is evidence, never the verdict. Hermetic trees here are
self-built (no imports from sibling test modules); the golden tree
mirrors a real LibreLane run layout with per-step machine files.
"""

import json
from pathlib import Path

STAGE_IDS = [f"D{i:02d}" for i in range(11, 28)]

GOLDEN_STEPS = (
    "Yosys.Synthesis",
    "OpenROAD.CheckSDC",
    "OpenROAD.Floorplan",
    "OpenROAD.TapEndcapInsertion",
    "OpenROAD.GlobalPlacement",
    "OpenROAD.CTS",
    "OpenROAD.GlobalRouting",
    "OpenROAD.DetailedRouting",
    "OpenROAD.FillerInsertion",
    "OpenROAD.RCX",
    "OpenROAD.STAPostPNR",
    "OpenROAD.IRDrop",
    "Odb.WriteGDS",
    "KLayout.DRC",
    "Netgen.LVS",
    "Yosys.EQY",
)


def _write(path, text=""):
    """Write one fixture file, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _write_state(step_dir, metrics=None, views=None):
    """Write state_out.json (+ metrics.csv) machine files for one step."""
    payload = {"metrics": dict(metrics or {})}
    payload.update(views or {})
    _write(step_dir / "state_out.json", json.dumps(payload) + "\n")
    rows = ["Metric,Value"]
    rows += [f"{key},{value}" for key, value in (metrics or {}).items()]
    _write(step_dir / "metrics.csv", "\n".join(rows) + "\n")
    return step_dir


def _golden_tree(design, tag):
    """Full ok run tree: artifacts plus per-step machine files + views."""
    runs = design / "runs" / tag
    _write(design / "digital_flow_config.json", '{"DESIGN_NAME": "counter"}\n')
    for name in GOLDEN_STEPS:
        (runs / name).mkdir(parents=True, exist_ok=True)
    synth = runs / "Yosys.Synthesis"
    _write(synth / "synth_netlist.v", "module counter(); endmodule\n")
    _write(synth / "synth_stat.txt", "cells: 42\n")
    _write(synth / "synth.log", "Synthesis finished\n")
    _write_state(synth, {"synth__cells": 42}, {"NETLIST": "synth_netlist.v"})
    _write(runs / "OpenROAD.CheckSDC" / "check.rpt", "SDC clean\n")
    _write(runs / "OpenROAD.Floorplan" / "floorplan.odb")
    _write(runs / "OpenROAD.Floorplan" / "floorplan.def")
    _write(runs / "OpenROAD.TapEndcapInsertion" / "pdn.def")
    _write(runs / "OpenROAD.GlobalPlacement" / "placement.odb")
    _write(runs / "OpenROAD.CTS" / "cts.rpt", "skew 0.05\n")
    _write(runs / "OpenROAD.GlobalRouting" / "route.guide")
    _write(runs / "OpenROAD.DetailedRouting" / "routed.odb")
    _write(runs / "OpenROAD.DetailedRouting" / "droute.rpt", "droute clean\n")
    _write(runs / "OpenROAD.FillerInsertion" / "fill.odb")
    _write(runs / "OpenROAD.RCX" / "design.spef", "*SPEF 1.0\n")
    for name in GOLDEN_STEPS:
        step = runs / name
        if not (step / "state_out.json").is_file():
            _write_state(step, {"step__done": 1})
    sta = runs / "OpenROAD.STAPostPNR"
    _write(sta / "sta.rpt", "No violations\n")
    _write_state(
        sta,
        {"timing__setup__ws": 9.15, "timing__hold__ws": 0.05},
    )
    _write(runs / "OpenROAD.IRDrop" / "power.rpt", "drop 12mV\n")
    gds = runs / "Odb.WriteGDS"
    (gds / "design.gds").write_bytes(b"GDS42")
    _write(gds / "design.lef")
    _write_state(gds, {"step__done": 1}, {"GDS": "design.gds"})
    _write(runs / "KLayout.DRC" / "drc.rpt", "total: 0\n")
    _write_state(runs / "KLayout.DRC", {"klayout__drc_error__count": 0})
    _write(runs / "Netgen.LVS" / "lvs.out", "Circuits match uniquely.\n")
    _write_state(runs / "Netgen.LVS", {"design__lvs_unmatched_net__count": 0})
    _write(runs / "Yosys.EQY" / "equiv.rpt", "Equivalent: all 42 points proven\n")
    _write_state(runs / "Yosys.EQY", {"equiv__equivalent": 1})
    return runs


def _native(workdir, design, tag, exit_code=0, timed_out=False):
    """Native block for a staged run tree."""
    run_dir = design / "runs" / tag
    return {
        "exit_code": exit_code,
        "stdout": "",
        "stderr": "",
        "log": "",
        "timed_out": timed_out,
        "workdir": str(workdir),
        "design_dir": str(design),
        "run_dir": str(run_dir) if run_dir.is_dir() else None,
        "config": str(design / "digital_flow_config.json"),
        "top": "counter",
        "tag": tag,
        "pdk": "sky130A",
        "flow": "Classic",
        "forced": [],
        "librelane_version": "LibreLane 3.0.17",
        "timeout_s": 3600,
    }


def _stages(result):
    """Stage table keyed by gate id."""
    return {stage["id"]: stage for stage in result["measurements"]["stages"]}


def _errors(result):
    """Error-severity violations only."""
    return [v for v in result["violations"] if v["severity"] == "error"]


def test_uranium_read_views_extracts_state_paths(tmp_path):
    """URANIUM RED: state_out.json view entries resolve to real files.

    Args:
        tmp_path: Pytest scratch dir for the fake step dir.
    """
    from rocket_engine.adapters.digital_flow.state import read_views

    step = tmp_path / "Odb.WriteGDS"
    step.mkdir()
    (step / "design.gds").write_bytes(b"GDS42")
    (step / "design.lef").write_text("LEF\n")
    (step / "state_out.json").write_text(
        json.dumps(
            {
                "metrics": {"step__done": 1},
                "GDS": "design.gds",
                "LEF": ["design.lef", "ghost.lef"],
            }
        )
        + "\n"
    )
    assert read_views(step) == [str(step / "design.gds"), str(step / "design.lef")]


def test_uranium_views_name_gds_deliverable(tmp_path):
    """URANIUM RED: the GDS deliverable follows the state view path.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    gds = design / "runs" / "engine" / "Odb.WriteGDS"
    (gds / "aaa.gds").write_bytes(b"AAA")
    (gds / "zzz.gds").write_bytes(b"ZZZ")
    (gds / "state_out.json").write_text(
        json.dumps({"metrics": {"step__done": 1}, "GDS": "zzz.gds"}) + "\n"
    )
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) == [], result["violations"]
    assert result["measurements"]["gds"] == str(gds / "zzz.gds")


def test_uranium_synth_error_text_never_decides(tmp_path):
    """URANIUM RED: ERROR lines pass over when synth machine files exist.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    synth = design / "runs" / "engine" / "Yosys.Synthesis"
    (synth / "synth.log").write_text("ERROR: some scary but stale line\n")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _stages(result)["D12"]["status"] == "pass"


def test_uranium_missing_synth_state_fails_machine_loud(tmp_path):
    """URANIUM RED: synth without machine files fails naming them.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    synth = design / "runs" / "engine" / "Yosys.Synthesis"
    (synth / "state_out.json").unlink()
    (synth / "metrics.csv").unlink()
    (synth / "synth.log").write_text("ERROR: parse error on line 1\n")
    result = LibrelaneFlowAdapter().parse(
        _native(workdir, design, "engine", exit_code=1)
    )
    assert _stages(result)["D12"]["status"] == "fail"
    assert "state_out.json" in _stages(result)["D12"]["reason"]


def test_uranium_middle_gate_needs_machine_files(tmp_path):
    """URANIUM RED: artifacts alone never pass a middle gate.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    sdc = design / "runs" / "engine" / "OpenROAD.CheckSDC"
    (sdc / "state_out.json").unlink()
    (sdc / "metrics.csv").unlink()
    assert (sdc / "check.rpt").is_file()
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _stages(result)["D13"]["status"] == "fail"
    assert "state_out.json" in _stages(result)["D13"]["reason"]


def test_uranium_signoff_drc_total_backs_verdict(tmp_path):
    """URANIUM RED: drc.klayout.json total judges DRC without metric keys.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    drc = design / "runs" / "engine" / "KLayout.DRC"
    _write_state(drc, {"unrelated__key": 1})
    reports = drc / "reports"
    _write(
        reports / "drc.klayout.json",
        json.dumps({"metal1": 3, "total": 3}) + "\n",
    )
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _stages(result)["D25"]["status"] == "fail"
    assert result["measurements"]["drc_total"] == 3


def test_uranium_signoff_lvs_report_rides_evidence(tmp_path):
    """URANIUM RED: lvs.netgen.json is linked as LVS evidence.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    lvs = design / "runs" / "engine" / "Netgen.LVS"
    report = _write(
        lvs / "reports" / "lvs.netgen.json",
        json.dumps([{"cell": "counter", "pins": "match"}]) + "\n",
    )
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) == [], result["violations"]
    assert str(report) in _stages(result)["D26"]["reports"]


def test_uranium_golden_tree_verdicts_stable(tmp_path):
    """URANIUM anchor: the full machine-file tree stays all-pass.

    Args:
        tmp_path: Pytest scratch dir for the fake run tree.
    """
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _golden_tree(design, "engine")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) == [], result["violations"]
    assert result["total"] == 0
    stages = _stages(result)
    assert sorted(stages) == STAGE_IDS
    assert all(s["status"] == "pass" for s in stages.values())
    measures = result["measurements"]
    assert Path(measures["gds"]).is_file()
    assert Path(measures["netlist"]).is_file()
    assert Path(measures["spef"]).is_file()
    assert measures["drc_total"] == 0
    assert measures["lvs_match"] is True
