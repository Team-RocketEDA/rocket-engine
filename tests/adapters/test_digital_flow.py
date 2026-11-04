"""DIGITAL-FLOW RED — LibrelaneFlowAdapter behind the ToolAdapter port.

Valid RED = `rocket_engine.adapters.digital_flow` does not exist yet,
so every test fails on ImportError. Hermetic tests drive a stub
`librelane` binary (version probe plus fake run dirs under
design/runs/<tag>/); live tests run counter/SERV through the real
pinned distribution and skip loudly (never fake-green) where the
distribution or a LibreLane PDK root is absent.

Tool placement on PATH plus the LibreLane PDK root are B10/PROV
integration scope, not test scope.
"""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "digital_flow"
ROOT = Path(__file__).resolve().parent.parent.parent
SERV = ROOT / "fixtures" / "upstream" / "serv"
SERV_MANIFEST = Path(__file__).parent / "fixtures" / "hdl" / "serv_sources.txt"

PIN = "3.0.17"
STAGE_IDS = [f"D{i:02d}" for i in range(11, 28)]
_MISSING_TOOL_REMEDY = (
    "run scripts/provision_toolchain.sh --install for the pinned AppImage "
    "per the upstream install docs"
)

STUB_TEMPLATE = r'''#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  echo "__VERSION__"
  exit 0
fi
TAG="engine"
CONFIG=""
PREV=""
for _a in "$@"; do
  if [ "$PREV" = "--tag" ] || [ "$PREV" = "--run-tag" ]; then TAG="$_a"; PREV=""; continue; fi
  case "$_a" in
    --tag|--run-tag) PREV="$_a" ;;
    *.json) CONFIG="$_a" ;;
  esac
done
DESIGN="$(dirname "$CONFIG")"
printf '%s\n' "$*" >"$DESIGN/stub_argv.txt"
BEHAVIOR="${STUB_BEHAVIOR:-ok}"
if [ "$BEHAVIOR" = "sleep" ]; then
  sleep 30
  exit 0
fi
RUNS="$DESIGN/runs/$TAG"
if [ "$BEHAVIOR" = "synthfail" ]; then
  mkdir -p "$RUNS/Yosys.Synthesis"
  printf 'ERROR: parse error on line 1 of broken.v\n' \
    >"$RUNS/Yosys.Synthesis/synth.log"
  exit 1
fi
mkdir -p "$RUNS/Yosys.Synthesis"
printf 'module counter(); endmodule\n' \
  >"$RUNS/Yosys.Synthesis/synth_netlist.v"
printf 'cells: 42\n' >"$RUNS/Yosys.Synthesis/synth_stat.txt"
printf 'Synthesis finished\n' >"$RUNS/Yosys.Synthesis/synth.log"
if [ "$BEHAVIOR" = "partial" ]; then
  exit 0
fi
mkdir -p "$RUNS/OpenROAD.CheckSDC"
printf 'SDC clean\n' >"$RUNS/OpenROAD.CheckSDC/check.rpt"
mkdir -p "$RUNS/OpenROAD.Floorplan"
: >"$RUNS/OpenROAD.Floorplan/floorplan.odb"
: >"$RUNS/OpenROAD.Floorplan/floorplan.def"
mkdir -p "$RUNS/OpenROAD.TapEndcapInsertion"
: >"$RUNS/OpenROAD.TapEndcapInsertion/pdn.def"
mkdir -p "$RUNS/OpenROAD.GlobalPlacement"
: >"$RUNS/OpenROAD.GlobalPlacement/placement.odb"
mkdir -p "$RUNS/OpenROAD.CTS"
printf 'skew 0.05\n' >"$RUNS/OpenROAD.CTS/cts.rpt"
mkdir -p "$RUNS/OpenROAD.GlobalRouting"
: >"$RUNS/OpenROAD.GlobalRouting/route.guide"
mkdir -p "$RUNS/OpenROAD.DetailedRouting"
: >"$RUNS/OpenROAD.DetailedRouting/routed.odb"
printf 'droute clean\n' >"$RUNS/OpenROAD.DetailedRouting/droute.rpt"
mkdir -p "$RUNS/OpenROAD.FillerInsertion"
: >"$RUNS/OpenROAD.FillerInsertion/fill.odb"
mkdir -p "$RUNS/OpenROAD.RCX"
printf '*SPEF 1.0\n' >"$RUNS/OpenROAD.RCX/design.spef"
mkdir -p "$RUNS/OpenROAD.STAPostPNR"
printf 'No violations\n' >"$RUNS/OpenROAD.STAPostPNR/sta.rpt"
mkdir -p "$RUNS/OpenROAD.IRDrop"
printf 'drop 12mV\n' >"$RUNS/OpenROAD.IRDrop/power.rpt"
mkdir -p "$RUNS/Odb.WriteGDS"
printf 'GDS42' >"$RUNS/Odb.WriteGDS/design.gds"
: >"$RUNS/Odb.WriteGDS/design.lef"
mkdir -p "$RUNS/KLayout.DRC"
printf 'total: 0\n' >"$RUNS/KLayout.DRC/drc.rpt"
mkdir -p "$RUNS/Netgen.LVS"
printf 'Circuits match uniquely.\n' >"$RUNS/Netgen.LVS/lvs.out"
mkdir -p "$RUNS/Yosys.EQY"
printf 'Equivalent: all 42 points proven\n' >"$RUNS/Yosys.EQY/equiv.rpt"
for _d in "$RUNS"/*/; do
  if [ ! -f "$_d/state_out.json" ]; then
    printf '{"metrics": {"step__done": 1}}\n' >"$_d/state_out.json"
    printf 'Metric,Value\nstep__done,1\n' >"$_d/metrics.csv"
  fi
done
printf '{"metrics": {"timing__setup__ws": 9.15,\n' >"$RUNS/OpenROAD.STAPostPNR/state_out.json"
printf ' "timing__hold__ws": 0.05}}\n' >>"$RUNS/OpenROAD.STAPostPNR/state_out.json"
printf 'Metric,Value\ntiming__setup__ws,9.15\n' >"$RUNS/OpenROAD.STAPostPNR/metrics.csv"
printf 'timing__hold__ws,0.05\n' >>"$RUNS/OpenROAD.STAPostPNR/metrics.csv"
printf '{"metrics": {"drc__violations": 0}}\n' >"$RUNS/KLayout.DRC/state_out.json"
printf 'Metric,Value\ndrc__violations,0\n' >"$RUNS/KLayout.DRC/metrics.csv"
printf '{"metrics": {"lvs__match": 1}}\n' >"$RUNS/Netgen.LVS/state_out.json"
printf 'Metric,Value\nlvs__match,1\n' >"$RUNS/Netgen.LVS/metrics.csv"
printf '{"metrics": {"equiv__equivalent": 1}}\n' >"$RUNS/Yosys.EQY/state_out.json"
printf 'Metric,Value\nequiv__equivalent,1\n' >"$RUNS/Yosys.EQY/metrics.csv"
exit 0
'''


def _probe_librelane():
    """(present, reason) for the pinned librelane on PATH."""
    found = shutil.which("librelane")
    if found is None:
        return False, "librelane not on PATH"
    try:
        proc = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"librelane version probe failed: {exc}"
    banner = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode == 0 and PIN in banner:
        return True, ""
    first = banner.splitlines()[0] if banner else "empty banner"
    return False, f"librelane version mismatch: {first!r} (want {PIN})"


def _probe_pdk_root():
    """(present, path, reason) for a LibreLane PDK root."""
    override = os.environ.get("DIGITAL_FLOW_PDK_ROOT")
    if override:
        if Path(override).is_dir():
            return True, override, ""
        return False, override, f"DIGITAL_FLOW_PDK_ROOT is not a dir: {override}"
    default = Path.home() / ".ciel"
    if default.is_dir():
        return True, str(default), ""
    return False, str(default), f"PDK root absent: {default}"


_LIBRELANE_PRESENT, _LIBRELANE_REASON = _probe_librelane()
_PDK_PRESENT, _PDK_ROOT, _PDK_REASON = _probe_pdk_root()
needs_librelane = pytest.mark.skipif(
    not _LIBRELANE_PRESENT,
    reason=f"{_LIBRELANE_REASON} ({_MISSING_TOOL_REMEDY})",
)
needs_pdk_root = pytest.mark.skipif(
    not _PDK_PRESENT,
    reason=f"{_PDK_REASON} (set DIGITAL_FLOW_PDK_ROOT to the volare/ciel root)",
)


def _job(names, top, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in names:
        dest = workdir / Path(name).name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {
        "operation": "run_digital_flow",
        "sources": staged,
        "top": top,
        "clock_port": "clk",
        "clock_period": 10.0,
        "pdk": "sky130A",
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def _require_serv():
    if not (SERV / "rtl" / "serv_top.v").is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")
    if not SERV_MANIFEST.is_file():
        raise FileNotFoundError(f"SERV sources manifest missing: {SERV_MANIFEST}")


def _stage_serv_rtl(tmp_path):
    _require_serv()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for line in SERV_MANIFEST.read_text().splitlines():
        rel = line.strip()
        if not rel or rel.startswith("#") or not rel.startswith("rtl/"):
            continue
        src = SERV / rel
        if not src.is_file():
            raise FileNotFoundError(f"SERV source missing: {src}")
        dest = workdir / Path(rel).name
        shutil.copy(src, dest)
        staged.append(str(dest))
    return workdir, staged


def _stub_librelane(path, version="LibreLane 3.0.17"):
    path.write_text(STUB_TEMPLATE.replace("__VERSION__", version))
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def _write(path, text=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _fake_evidence(design, tag, variant="ok", machine=True):
    """Fake design/runs/<tag>/ evidence tree plus the flow config."""
    runs = design / "runs" / tag
    _write(design / "digital_flow_config.json", '{"DESIGN_NAME": "counter"}\n')
    if variant == "norun":
        return runs
    if variant == "synthfail":
        _write(
            runs / "Yosys.Synthesis" / "synth.log",
            "ERROR: parse error on line 1 of broken.v\n",
        )
        return runs
    synth = runs / "Yosys.Synthesis"
    _write(synth / "synth_netlist.v", "module counter(); endmodule\n")
    _write(synth / "synth_stat.txt", "cells: 42\n")
    _write(synth / "synth.log", "Synthesis finished\n")
    if variant == "partial":
        _ensure_step_states(runs)
        return runs
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
    sta_text = "Setup VIOLATED\n" if variant == "sta_fail" else "No violations\n"
    _write(runs / "OpenROAD.STAPostPNR" / "sta.rpt", sta_text)
    _write(runs / "OpenROAD.IRDrop" / "power.rpt", "drop 12mV\n")
    gds = runs / "Odb.WriteGDS" / "design.gds"
    gds.parent.mkdir(parents=True, exist_ok=True)
    gds.write_bytes(b"GDS42")
    _write(runs / "Odb.WriteGDS" / "design.lef")
    drc_text = "total: 5\n" if variant == "drc_dirty" else "total: 0\n"
    _write(runs / "KLayout.DRC" / "drc.rpt", drc_text)
    if variant == "lvs_fail":
        lvs_text = "Netlists do not match.\n*** MISMATCH ***\n"
    else:
        lvs_text = "Circuits match uniquely.\n"
    _write(runs / "Netgen.LVS" / "lvs.out", lvs_text)
    _write(runs / "Yosys.EQY" / "equiv.rpt", "Equivalent: all 42 points proven\n")
    if machine:
        _write_machine_states(runs, variant=variant)
        _ensure_step_states(runs)
    return runs


def _native(workdir, design, tag, exit_code=0, timed_out=False, forced=()):
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
        "forced": list(forced),
        "librelane_version": f"LibreLane {PIN}",
        "timeout_s": 3600,
        "flow": "Classic",
    }


def _errors(result):
    return [v for v in result["violations"] if v["severity"] == "error"]


def _stages(result):
    return {stage["id"]: stage for stage in result["measurements"]["stages"]}


def test_digital_flow_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    assert issubclass(LibrelaneFlowAdapter, ToolAdapter)


def test_digital_flow_capabilities_advertise_run_digital_flow():
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    caps = LibrelaneFlowAdapter().capabilities({"top": "counter"})
    assert caps["operations"] == ["run_digital_flow"]
    assert caps["tool"] == "librelane"
    assert caps["flow"] == "Classic"
    assert caps["stages"] == STAGE_IDS


def test_digital_flow_preflight_refuses_wrong_operation(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, operation="run_synth")
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "unsupported_operation"


def test_digital_flow_preflight_refuses_foreign_deck_tool(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, deck={"tool": "yosys"})
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "unsupported_operation"


def test_digital_flow_preflight_refuses_bad_deck_shape(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, deck="librelane")
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("top", ["", None, "not a top", "counter; rm -rf /", "a.b"])
def test_digital_flow_preflight_refuses_bad_top(tmp_path, top):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["top"] = top
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


def test_digital_flow_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.v")]
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_digital_flow_preflight_refuses_duplicate_basenames(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    first = tmp_path / "a" / "dup.v"
    second = tmp_path / "b" / "dup.v"
    _write(first, "module a(); endmodule\n")
    _write(second, "module b(); endmodule\n")
    job = _job(["counter.v"], "counter", tmp_path)
    job["sources"] = [str(first), str(second)]
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("period", [0, -1.5, "10", None, True])
def test_digital_flow_preflight_refuses_bad_clock_period(tmp_path, period):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, clock_period=period)
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("port", ["", "not a port", 42])
def test_digital_flow_preflight_refuses_bad_clock_port(tmp_path, port):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, clock_port=port)
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize(
    "key,value",
    [("tag", "bad tag!"), ("tag", ""), ("flow", "Chip"), ("pdk", ""),
     ("pdk", None), ("timeout_s", 0), ("timeout_s", "60")],
)
def test_digital_flow_preflight_refuses_bad_run_knobs(tmp_path, key, value):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, **{key: value})
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize(
    "force", [["D99"], ["run_synth"], "D12", [42], ["D11", "D99"]]
)
def test_digital_flow_preflight_refuses_bad_force(tmp_path, force):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, force=force)
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("config", [["not", "dict"], "flow", [42]])
def test_digital_flow_preflight_refuses_bad_config(tmp_path, config):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, config=config)
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


def test_digital_flow_preflight_refuses_missing_pdk_root(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["pdk_root"] = str(tmp_path / "ghost-pdk")
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_digital_flow_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-digital-flow-tests"
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "missing_dependency"
    message = str(caught.value)
    assert "LibreLane" in message
    assert "provision_toolchain.sh" in message
    assert PIN in message


def test_digital_flow_version_mismatch_refuses_loudly(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_librelane(bindir / "librelane", version="LibreLane 0.0.0")
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=str(bindir))
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "missing_dependency"
    assert PIN in str(caught.value)


def test_digital_flow_preflight_records_version_with_stub(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_librelane(bindir / "librelane")
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=str(bindir))
    checked = LibrelaneFlowAdapter().preflight(job)
    assert PIN in checked["librelane_version"]
    assert checked["top"] == "counter"
    assert checked["flow"] == "Classic"


def test_digital_flow_parse_without_verdict_raises():
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_digital_flow_parse_timeout_reports_timeout(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="partial")
    native = _native(workdir, design, "engine", exit_code=None, timed_out=True)
    native["timeout_s"] = 60
    result = LibrelaneFlowAdapter().parse(native)
    assert result["total"] >= 1
    assert any(v["rule"] == "digital_flow_timeout" for v in result["violations"])
    assert _errors(result) != []
    assert result["measurements"]["timed_out"] is True


def test_digital_flow_parse_complete_run_is_clean(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="ok")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) == [], result["violations"]
    assert result["total"] == 0
    stages = _stages(result)
    assert sorted(stages) == STAGE_IDS
    assert all(s["status"] == "pass" for s in stages.values())
    measures = result["measurements"]
    assert Path(measures["gds"]).is_file()
    assert measures["drc_total"] == 0
    assert measures["lvs_match"] is True
    assert Path(measures["netlist"]).is_file()
    assert Path(measures["spef"]).is_file()
    assert PIN in measures["librelane_version"]


def test_digital_flow_parse_partial_run_fails_named_gates(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="partial")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) != []
    stages = _stages(result)
    assert stages["D11"]["status"] == "pass"
    assert stages["D12"]["status"] == "pass"
    assert stages["D13"]["status"] == "fail"
    assert stages["D24"]["status"] == "fail"
    for violation in _errors(result):
        assert violation["rule"] == "digital_flow_gate"
        assert violation["message"].startswith("D")


def test_digital_flow_parse_force_bypass_warns_not_fails(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="partial")
    forced = [f"D{i:02d}" for i in range(13, 28)]
    native = _native(workdir, design, "engine", forced=forced)
    result = LibrelaneFlowAdapter().parse(native)
    assert _errors(result) == [], result["violations"]
    stages = _stages(result)
    assert stages["D13"]["status"] == "forced"
    assert stages["D27"]["status"] == "forced"
    assert result["measurements"]["forced"] == forced
    assert all(v["severity"] == "warning" for v in result["violations"])


def test_digital_flow_parse_broken_rtl_dies_at_synth(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="synthfail")
    native = _native(workdir, design, "engine", exit_code=1)
    result = LibrelaneFlowAdapter().parse(native)
    assert _errors(result) != []
    stages = _stages(result)
    assert stages["D12"]["status"] == "fail"
    assert stages["D13"]["status"] == "not_run"
    assert stages["D27"]["status"] == "not_run"
    synth_errors = [v for v in _errors(result) if "D12" in v["message"]]
    assert synth_errors != []
    assert any("state_out.json" in v["message"] for v in synth_errors)


def test_digital_flow_parse_failed_run_without_cause_synthesizes_error(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="norun")
    native = _native(workdir, design, "engine", exit_code=1)
    result = LibrelaneFlowAdapter().parse(native)
    assert result["total"] >= 1
    assert _errors(result) != []


def test_digital_flow_parse_drc_dirty_fails_gate(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="drc_dirty")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) != []
    assert _stages(result)["D25"]["status"] == "fail"
    assert result["measurements"]["drc_total"] == 5
    assert any("D25" in v["message"] for v in _errors(result))


def test_digital_flow_parse_lvs_mismatch_fails_gate(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="lvs_fail")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) != []
    assert _stages(result)["D26"]["status"] == "fail"
    assert result["measurements"]["lvs_match"] is False


def test_digital_flow_parse_sta_violated_fails_gate(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="sta_fail")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _errors(result) != []
    assert _stages(result)["D22"]["status"] == "fail"


def test_digital_flow_execute_stub_ok_collects_evidence(tmp_path, monkeypatch):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    monkeypatch.setenv("STUB_BEHAVIOR", "ok")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_librelane(bindir / "librelane")
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=str(bindir))
    adapter = LibrelaneFlowAdapter()
    native = adapter.execute(job)
    assert native["exit_code"] == 0
    assert native["timed_out"] is False
    design = Path(job["workdir"]) / "design"
    assert (design / "digital_flow_config.json").is_file()
    assert (design / "src" / "counter.v").is_file()
    argv = (design / "stub_argv.txt").read_text()
    assert "digital_flow_config.json" in argv
    assert "--run-tag" in argv
    assert "--pdk" in argv
    result = adapter.parse(native)
    assert _errors(result) == [], result["violations"]
    assert result["measurements"]["drc_total"] == 0
    assert result["measurements"]["lvs_match"] is True


def test_digital_flow_execute_stub_synthfail_dies_at_synth(tmp_path, monkeypatch):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    monkeypatch.setenv("STUB_BEHAVIOR", "synthfail")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_librelane(bindir / "librelane")
    job = _job(["broken.v"], "broken", tmp_path, tool_dir=str(bindir))
    adapter = LibrelaneFlowAdapter()
    native = adapter.execute(job)
    assert native["exit_code"] != 0
    result = adapter.parse(native)
    assert any("D12" in v["message"] for v in _errors(result))


def test_digital_flow_execute_timeout_kills_tree(tmp_path, monkeypatch):
    import time

    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    monkeypatch.setenv("STUB_BEHAVIOR", "sleep")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _stub_librelane(bindir / "librelane")
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=str(bindir))
    job["timeout_s"] = 2
    started = time.monotonic()
    native = LibrelaneFlowAdapter().execute(job)
    elapsed = time.monotonic() - started
    assert native["timed_out"] is True
    assert elapsed < 25
    result = LibrelaneFlowAdapter().parse(native)
    assert any(v["rule"] == "digital_flow_timeout" for v in result["violations"])


@needs_librelane
@needs_pdk_root
def test_digital_flow_counter_live_proves_gds(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, pdk_root=_PDK_ROOT)
    job["timeout_s"] = 1800
    # Small-design recipe (upstream spm example): explicit PDN grid
    # fits the tiny die; FP_CORE_UTIL 30 rooms the straps.
    job["config"] = {
        "PDN_VOFFSET": 5, "PDN_HOFFSET": 5,
        "PDN_VWIDTH": 2, "PDN_HWIDTH": 2,
        "PDN_VPITCH": 30, "PDN_HPITCH": 30,
        "PDN_SKIPTRIM": True, "FP_CORE_UTIL": 30,
    }
    # The classic flow proves no formal equivalence (FORMAL-SBY
    # lane owns that); force-bypass D27 loudly, never silently.
    job["force"] = ["D27"]
    adapter = LibrelaneFlowAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    assert Path(result["measurements"]["gds"]).is_file()
    assert result["measurements"]["lvs_match"] is True
    forced = [s for s in result["stages"] if s["status"] == "forced"]
    assert [s["id"] for s in forced] == ["D27"]


@needs_librelane
@needs_pdk_root
def test_digital_flow_broken_rtl_live_dies_at_synth(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    job = _job(["broken.v"], "broken", tmp_path, pdk_root=_PDK_ROOT)
    job["timeout_s"] = 1800
    adapter = LibrelaneFlowAdapter()
    native = adapter.execute(job)
    assert native["exit_code"] != 0
    result = adapter.parse(native)
    assert any("D12" in v["message"] for v in _errors(result))


def _write_step_state(step_dir, metrics):
    """Write state_out.json + metrics.csv machine files for one step."""
    step_dir.mkdir(parents=True, exist_ok=True)
    (step_dir / "state_out.json").write_text(
        json.dumps({"metrics": dict(metrics)}) + "\n"
    )
    rows = ["Metric,Value"]
    rows += [f"{key},{value}" for key, value in metrics.items()]
    (step_dir / "metrics.csv").write_text("\n".join(rows) + "\n")
    return step_dir


def _ensure_step_states(runs):
    """Minimal state_out.json for every step dir missing one.

    Real LibreLane steps always finish by writing state_out.json
    (docs/tools/librelane.md section 1, R2); the hermetic trees mirror
    that so middle gates judge machine files. Deliverable views ride
    on the synth/RCX/WriteGDS states.

    Args:
        runs: runs/<tag>/ dir path holding the fake step dirs.

    Returns:
        The runs dir path, unchanged.
    """
    views = {
        "Yosys.Synthesis": {"NETLIST": "synth_netlist.v"},
        "OpenROAD.RCX": {"SPEF": "design.spef"},
        "Odb.WriteGDS": {"GDS": "design.gds"},
    }
    if not runs.is_dir():
        return runs
    for step in sorted(runs.iterdir()):
        if not step.is_dir() or (step / "state_out.json").is_file():
            continue
        payload = {"metrics": {"step__done": 1}}
        payload.update(views.get(step.name, {}))
        (step / "state_out.json").write_text(json.dumps(payload) + "\n")
        (step / "metrics.csv").write_text("Metric,Value\nstep__done,1\n")
    return runs


def _write_machine_states(runs, variant="ok"):
    """Machine-file states for the STA/DRC/LVS/EQY steps in a run tree."""
    sta = {"timing__setup__ws": 9.15, "timing__setup__tns": 0.0,
           "timing__hold__ws": 0.05, "timing__hold__tns": 0.0}
    drc = {"drc__violations": 0}
    lvs = {"lvs__match": 1}
    eqy = {"equiv__equivalent": 1}
    if variant == "sta_fail":
        sta = {"timing__setup__ws": -1.25, "timing__setup__tns": -2.5,
               "timing__hold__ws": 0.05, "timing__hold__tns": 0.0}
    if variant == "drc_dirty":
        drc = {"drc__violations": 5}
    if variant == "lvs_fail":
        lvs = {"lvs__match": 0}
    _write_step_state(runs / "OpenROAD.STAPostPNR", sta)
    _write_step_state(runs / "KLayout.DRC", drc)
    _write_step_state(runs / "Netgen.LVS", lvs)
    _write_step_state(runs / "Yosys.EQY", eqy)
    return runs


def test_digital_flow_uranium_text_without_machine_files_fails_loud(tmp_path):
    """URANIUM: report text alone never passes a machine-gated stage."""
    from rocket_engine.adapters.digital_flow import (
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="ok", machine=False)
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    stages = _stages(result)
    for gate in ("D22", "D25", "D26"):
        assert stages[gate]["status"] == "fail"
        assert "state_out.json" in stages[gate]["reason"]
    assert stages["D27"]["status"] == "fail"
    assert "blocked by D12" in stages["D27"]["reason"]
    assert any(
        "machine" in v["message"] for v in _errors(result)
    )


def test_digital_flow_uranium_metric_violation_beats_clean_text(tmp_path):
    """URANIUM: dirty machine metrics fail the gate on clean text."""
    from rocket_engine.adapters.digital_flow import (
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="ok")
    _write_machine_states(design / "runs" / "engine", variant="drc_dirty")
    # Control: the report text still claims total 0; metrics must win.
    assert "total: 0" in (
        design / "runs" / "engine" / "KLayout.DRC" / "drc.rpt"
    ).read_text()
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _stages(result)["D25"]["status"] == "fail"
    assert result["measurements"]["drc_total"] == 5


def test_digital_flow_uranium_clean_metrics_beat_dirty_text(tmp_path):
    """URANIUM: clean machine metrics pass the gate on dirty text."""
    from rocket_engine.adapters.digital_flow import (
        LibrelaneFlowAdapter,
    )

    workdir = tmp_path / "work"
    workdir.mkdir()
    design = workdir / "design"
    _fake_evidence(design, "engine", variant="drc_dirty")
    _write_machine_states(design / "runs" / "engine", variant="ok")
    result = LibrelaneFlowAdapter().parse(_native(workdir, design, "engine"))
    assert _stages(result)["D25"]["status"] == "pass"
    assert result["measurements"]["drc_total"] == 0


@needs_librelane
@needs_pdk_root
def test_digital_flow_serv_live_proves_gds(tmp_path):
    from rocket_engine.adapters.digital_flow import (  # RED: missing adapter
        LibrelaneFlowAdapter,
    )

    workdir, staged = _stage_serv_rtl(tmp_path)
    job = {
        "operation": "run_digital_flow",
        "sources": staged,
        "top": "serv_top",
        "clock_port": "clk",
        # 10 ns leaves ss-corner setup open with default flow
        # effort (measured WNS -2.49 ns); 20 ns is the honest
        # smoke target — the STA gate still judges, never waived.
        "clock_period": 20.0,
        "pdk": "sky130A",
        "pdk_root": _PDK_ROOT,
        "workdir": str(workdir),
        "timeout_s": 3600,
        # Classic flow proves no formal equivalence (FORMAL-SBY
        # lane owns that); force-bypass D27 loudly, never silently.
        "force": ["D27"],
    }
    adapter = LibrelaneFlowAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    stages = _stages(result)
    assert all(
        s["status"] == "pass" for i, s in stages.items() if i != "D27"
    )
    assert stages["D27"]["status"] == "forced"
    assert Path(result["measurements"]["gds"]).is_file()
    assert result["measurements"]["drc_total"] == 0
    assert result["measurements"]["lvs_match"] is True
