"""TIMING-STA RED — OpenStaTimingAdapter behind the ToolAdapter port (run_timing).

Valid RED = `rocket_engine.adapters.timing_sta` does not exist yet,
so every test fails on ImportError. The adapter is a standalone
top-level timing recheck: mapped netlist + timing libs + SDC (plus
an optional top-level SPEF) flow to `sta`, and the parse returns
setup/hold WNS/TNS, critical paths, slew/load violations, and the
unconstrained endpoints — listed, never silent.

Hermetic tests drive a stub `sta` (golden OpenSTA-style log) plus
script-content assertions, so they pin the invocation contract
without the binary. Live tests need the PROV-pinned `sta` and the
ambient sky130 liberty and skip loudly without them (never
fake-green); the mixed SERV top recheck additionally needs yosys
plus the vendored SERV tree. Golden log formats are best-knowledge
OpenSTA shapes — the live gate-host run settles any drift.
"""

import os
import re
import shutil
import stat
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "timing"
ROOT = Path(__file__).resolve().parent.parent.parent
SERV = ROOT / "fixtures" / "upstream" / "serv"
SERV_MANIFEST = Path(__file__).parent / "fixtures" / "hdl" / "serv_sources.txt"
PROVISIONER = ROOT / "scripts" / "provision_toolchain.sh"

_PIN_MATCH = re.search(
    r'OPENSTA_PIN="([0-9a-f]{40})"', PROVISIONER.read_text()
)
assert _PIN_MATCH, "provisioner lost its OPENSTA_PIN line"
OPENSTA_SHORT = _PIN_MATCH.group(1)[:7]

_LIBERTY_DEFAULT = (
    Path.home()
    / ".local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib"
    / "sky130_fd_sc_hd__tt_100C_1v80.lib"
)
LIBERTY = Path(os.environ.get("TIMING_STA_LIBERTY", str(_LIBERTY_DEFAULT)))


def _pinned_sta():
    prefix = os.environ.get("OPENSTA_PREFIX")
    if prefix:
        return Path(prefix) / "bin" / "sta"
    return Path.home() / "tools" / f"opensta-{OPENSTA_SHORT}" / "bin" / "sta"


sta_present = _pinned_sta().is_file() or shutil.which("sta") is not None
needs_sta = pytest.mark.skipif(not sta_present, reason="sta not provisioned")
needs_liberty = pytest.mark.skipif(
    not LIBERTY.is_file(), reason=f"sky130 liberty absent: {LIBERTY}"
)
needs_yosys = pytest.mark.skipif(
    shutil.which("yosys") is None, reason="yosys not on PATH"
)

GOLDEN_LOG = """OpenSTA 2.5.1 splash line (unknown lines are ignored, never fatal)
Warning: liberty voltage scaling note (generic warning, never fatal alone).
===== TIMING_STA REPORT_CHECKS =====
Startpoint: cnt_reg[0]/Q (rising edge-triggered flip-flop clocked by clk)
Endpoint: cnt_reg[1]/D (rising edge-triggered flip-flop clocked by clk)
Path Group: clk
Path Type: max

  Delay    Time Description
---------------------------------------------------------
   0.00    0.00 clock clk (rise edge)
   0.00    0.00 clock network delay (ideal)
   0.10    0.10 ^ cnt_reg[0]/CK (sky130_fd_sc_hd__dfrtp_1)
   0.25    0.35 ^ cnt_reg[0]/Q (sky130_fd_sc_hd__dfrtp_1)
   0.30    0.65 ^ u3/X (sky130_fd_sc_hd__xor2_1)
   0.05    0.70 ^ cnt_reg[1]/D (sky130_fd_sc_hd__dfrtp_1)
           0.70 data arrival time

  10.00   10.00 clock clk (rise edge)
   0.00   10.00 clock network delay (ideal)
   0.00   10.00 clock uncertainty
  -0.10    9.90 v cnt_reg[1]/CK (sky130_fd_sc_hd__dfrtp_1)
  -0.05    9.85 library setup time
           9.85 data required time
---------------------------------------------------------
           9.85 data required time
          -0.70 data arrival time
---------------------------------------------------------
           9.15 slack (MET)
Startpoint: cnt_reg[2]/Q (rising edge-triggered flip-flop clocked by clk)
Endpoint: cnt_reg[2]/D (rising edge-triggered flip-flop clocked by clk)
Path Group: clk
Path Type: min

  Delay    Time Description
---------------------------------------------------------
   0.00    0.00 clock clk (rise edge)
   0.00    0.00 clock network delay (ideal)
   0.10    0.10 ^ cnt_reg[2]/CK (sky130_fd_sc_hd__dfrtp_1)
   0.15    0.25 ^ cnt_reg[2]/Q (sky130_fd_sc_hd__dfrtp_1)
   0.05    0.30 ^ cnt_reg[2]/D (sky130_fd_sc_hd__dfrtp_1)
           0.30 data arrival time

   0.00    0.00 clock clk (rise edge)
   0.00    0.00 clock network delay (ideal)
   0.00    0.00 clock uncertainty
   0.10    0.10 ^ cnt_reg[2]/CK (sky130_fd_sc_hd__dfrtp_1)
   0.05    0.15 library hold time
           0.15 data required time
---------------------------------------------------------
           0.15 data required time
          -0.30 data arrival time
---------------------------------------------------------
          -0.15 slack (VIOLATED)
===== TIMING_STA WNS_MAX =====
wns 9.15
===== TIMING_STA TNS_MAX =====
tns 9.15
===== TIMING_STA WNS_MIN =====
wns -0.15
===== TIMING_STA TNS_MIN =====
tns -0.15
===== TIMING_STA CONSTRAINTS =====
Pin                     Limit  Actual  Slack
------------------------------------------------
cnt_reg[0]/Q             0.50    0.75  -0.25 (VIOLATED)
===== TIMING_STA CHECK_SETUP =====
Warning: endpoint rdata0_in is unconstrained.
Warning: endpoint wdata0_out is unconstrained.
"""


def _job(netlists, top, tmp_path, libs=None, sdc="counter.sdc", **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged_net = []
    for name in netlists:
        dest = workdir / Path(name).name
        shutil.copy(FIXTURES / name, dest)
        staged_net.append(str(dest))
    staged_libs = []
    for name in libs if libs is not None else ["stub.lib"]:
        dest = workdir / Path(name).name
        shutil.copy(FIXTURES / name, dest)
        staged_libs.append(str(dest))
    sdc_dest = workdir / Path(sdc).name
    shutil.copy(FIXTURES / sdc, sdc_dest)
    job = {
        "operation": "run_timing",
        "netlist": staged_net,
        "libs": staged_libs,
        "sdc": str(sdc_dest),
        "top": top,
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def _write_stub(bindir, log=GOLDEN_LOG, exit_code=0,
                version="OpenSTA 2.5.1 TIMING-STA-stub"):
    bindir.mkdir(parents=True, exist_ok=True)
    sta = bindir / "sta"
    sta.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-version" ] || [ "$1" = "--version" ]; then\n'
        f'  echo "{version}"\n'
        "  exit 0\n"
        "fi\n"
        "cat <<'STA_EOF'\n"
        + log
        + ("" if log.endswith("\n") else "\n")
        + "STA_EOF\n"
        f"exit {exit_code}\n"
    )
    sta.chmod(sta.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(bindir)


def _errors(result):
    return [v for v in result["violations"] if v["severity"] == "error"]


def _measurement(result, name):
    return next(m for m in result["measurements"] if m["name"] == name)


def _require_serv():
    if not (SERV / "rtl" / "serv_top.v").is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")
    if not SERV_MANIFEST.is_file():
        raise FileNotFoundError(f"SERV sources manifest missing: {SERV_MANIFEST}")


def test_timing_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    assert issubclass(OpenStaTimingAdapter, ToolAdapter)


def test_timing_capabilities_advertise_run_timing():
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    caps = OpenStaTimingAdapter().capabilities({"top": "top_mixed"})
    assert caps["operations"] == ["run_timing"]
    assert caps["tool"] == "opensta"


def test_timing_preflight_refuses_wrong_operation(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job["operation"] = "run_synth"
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "unsupported_operation"


@pytest.mark.parametrize("top", ["", None, "not a top", "top; rm -rf /", "a.b"])
def test_timing_preflight_refuses_bad_top(tmp_path, top):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job["top"] = top
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("timeout", [0, -5, "soon", None])
def test_timing_preflight_refuses_bad_timeout(tmp_path, timeout):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path, timeout_s=timeout)
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


@pytest.mark.parametrize("key", ["netlist", "libs"])
def test_timing_preflight_refuses_missing_inputs(tmp_path, key):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job[key] = [str(tmp_path / "work" / "ghost.xyz")]
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_timing_preflight_refuses_empty_inputs(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    for key in ("netlist", "libs"):
        job = _job(["counter_mapped.v"], "counter", tmp_path)
        job[key] = []
        with pytest.raises(Exception) as caught:
            OpenStaTimingAdapter().preflight(job)
        assert getattr(caught.value, "code", None) == "invalid_reference"


def test_timing_preflight_refuses_missing_sdc(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job["sdc"] = str(tmp_path / "work" / "ghost.sdc")
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_timing_preflight_refuses_missing_spef(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job["spef"] = str(tmp_path / "work" / "ghost.spef")
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_timing_preflight_refuses_missing_tool(tmp_path, monkeypatch):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("OPENSTA_PREFIX", raising=False)
    job = _job(["counter_mapped.v"], "counter", tmp_path)
    job["tool_dir"] = str(tmp_path / "no-such-bindir")
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "missing_dependency"
    assert "provision_toolchain" in str(caught.value)


def test_timing_preflight_refuses_unassertable_version(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    tool_dir = _write_stub(tmp_path / "bin", version="definitely-not-sta 0.0")
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "missing_dependency"


def test_timing_preflight_records_sta_version(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    tool_dir = _write_stub(tmp_path / "bin")
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    checked = OpenStaTimingAdapter().preflight(job)
    assert checked["sta_version"].startswith("OpenSTA ")


def test_timing_opensta_prefix_env_resolution(tmp_path, monkeypatch):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    prefix = tmp_path / "opensta-fake"
    _write_stub(prefix / "bin")
    monkeypatch.setenv("OPENSTA_PREFIX", str(prefix))
    monkeypatch.setenv("PATH", str(tmp_path))
    job = _job(["counter_mapped.v"], "counter", tmp_path)
    checked = OpenStaTimingAdapter().preflight(job)
    assert checked["sta"] == str(prefix / "bin" / "sta")


def test_timing_script_covers_flow_commands(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    tool_dir = _write_stub(tmp_path / "bin")
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    native = OpenStaTimingAdapter().execute(job)
    assert native["exit_code"] == 0
    script = Path(job["workdir"], "timing.tcl").read_text()
    for command in (
        "read_liberty",
        "read_verilog",
        "link_design counter",
        "read_sdc",
        "report_checks -path_delay min_max",
        "report_wns",
        "report_tns",
        "report_constraint",
        "check_setup",
    ):
        assert command in script, command
    assert "read_spef" not in script
    assert script.rstrip().endswith("exit")
    assert native["log"] != ""


def test_timing_script_adds_spef_when_given(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    tool_dir = _write_stub(tmp_path / "bin")
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    spef_dest = Path(job["workdir"], "top_mixed.spef")
    shutil.copy(FIXTURES / "top_mixed.spef", spef_dest)
    job["spef"] = str(spef_dest)
    native = OpenStaTimingAdapter().execute(job)
    assert native["exit_code"] == 0
    assert "read_spef" in Path(job["workdir"], "timing.tcl").read_text()
    assert native["spef"] == str(spef_dest)


def test_timing_parse_golden_reports_margins_paths_findings(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    tool_dir = _write_stub(tmp_path / "bin")
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    result = OpenStaTimingAdapter().parse(OpenStaTimingAdapter().execute(job))
    assert _measurement(result, "wns_setup")["value"] == pytest.approx(9.15)
    assert _measurement(result, "tns_setup")["value"] == pytest.approx(9.15)
    assert _measurement(result, "wns_hold")["value"] == pytest.approx(-0.15)
    assert _measurement(result, "tns_hold")["value"] == pytest.approx(-0.15)
    assert result["wns_setup"] == pytest.approx(9.15)
    assert result["wns_hold"] == pytest.approx(-0.15)
    paths = result["critical_paths"]
    assert len(paths) == 2
    setup = next(p for p in paths if p["type"] == "max")
    assert setup["slack"] == pytest.approx(9.15)
    assert setup["violated"] is False
    assert setup["endpoint"].endswith("/D")
    hold = next(p for p in paths if p["type"] == "min")
    assert hold["violated"] is True
    rules = {v["rule"] for v in result["violations"]}
    assert "hold_violation" in rules
    assert "setup_violation" not in rules
    assert "constraint_violation" in rules
    assert "sta_warning" in rules
    assert "unconstrained_endpoint" in rules
    assert _errors(result) != []
    evidence = " ".join(result["unconstrained_endpoints"])
    assert "rdata0_in" in evidence and "wdata0_out" in evidence
    assert result["check_setup"] != ""


def test_timing_parse_violated_setup_flags_setup_violation(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    log = GOLDEN_LOG.replace("9.15 slack (MET)", "-1.25 slack (VIOLATED)")
    log = log.replace("wns 9.15", "wns -1.25").replace("tns 9.15", "tns -1.25")
    tool_dir = _write_stub(tmp_path / "bin", log=log)
    job = _job(["counter_mapped.v"], "counter", tmp_path, tool_dir=tool_dir)
    result = OpenStaTimingAdapter().parse(OpenStaTimingAdapter().execute(job))
    assert result["wns_setup"] == pytest.approx(-1.25)
    assert any(v["rule"] == "setup_violation" for v in result["violations"])
    assert _errors(result) != []


def test_timing_parse_failed_run_without_errors_synthesizes_error():
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    result = OpenStaTimingAdapter().parse({"exit_code": 1, "log": ""})
    assert result["total"] >= 1
    assert any(v["rule"] == "sta_error" for v in result["violations"])
    assert _errors(result) != []


def test_timing_parse_without_verdict_raises():
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().parse({"exit_code": 0, "log": "nothing here\n"})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_timing_parse_errors_fail_despite_exit_zero():
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    log = "Error: link_design failed: top counter not found.\n" + GOLDEN_LOG
    result = OpenStaTimingAdapter().parse({"exit_code": 0, "log": log})
    assert any(v["rule"] == "sta_error" for v in result["violations"])
    assert _errors(result) != []
    assert result["measurements"] == []


@needs_sta
@needs_liberty
def test_timing_counter_live_reports_margins(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    adapter = OpenStaTimingAdapter()
    job = _job(["counter_mapped.v"], "counter", tmp_path, libs=None)
    job["libs"] = [str(LIBERTY)]
    native = adapter.execute(job)
    assert native["exit_code"] == 0, native["log"][-2000:]
    result = adapter.parse(native)
    assert not any(v["rule"] == "sta_error" for v in result["violations"])
    assert result["critical_paths"] != []
    for name in ("wns_setup", "tns_setup", "wns_hold", "tns_hold"):
        assert isinstance(_measurement(result, name)["value"], float)
    assert native["sta_version"].startswith("OpenSTA")


@needs_sta
@needs_liberty
def test_timing_counter_live_lists_unconstrained_pin(tmp_path):
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

    adapter = OpenStaTimingAdapter()
    job = _job(["counter_mapped.v"], "counter", tmp_path, libs=None)
    job["libs"] = [str(LIBERTY)]
    result = adapter.parse(adapter.execute(job))
    evidence = " ".join(result["unconstrained_endpoints"]) + result["check_setup"]
    assert "overflow" in evidence


@needs_sta
@needs_liberty
@needs_yosys
def test_timing_mixed_serv_top_recheck(tmp_path):
    from rocket_engine.adapters.synth_yosys import YosysSynthAdapter
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

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
    synth = YosysSynthAdapter().parse(
        YosysSynthAdapter().execute(
            {
                "operation": "run_synth",
                "sources": staged,
                "top": "serv_top",
                "liberty": str(LIBERTY),
                "workdir": str(workdir),
            }
        )
    )
    assert synth["total"] == 0 or all(
        v["severity"] != "error" for v in synth["violations"]
    )
    wrapper = workdir / "top_mixed.v"
    shutil.copy(FIXTURES / "top_mixed.v", wrapper)
    sdc = workdir / "top_mixed.sdc"
    shutil.copy(FIXTURES / "top_mixed.sdc", sdc)
    job = {
        "operation": "run_timing",
        "netlist": [str(wrapper), synth["netlist"]],
        "libs": [str(LIBERTY)],
        "sdc": str(sdc),
        "top": "top_mixed",
        "workdir": str(workdir),
        "timeout_s": 600,
    }
    result = OpenStaTimingAdapter().parse(OpenStaTimingAdapter().execute(job))
    assert not any(v["rule"] == "sta_error" for v in result["violations"])
    assert len(result["critical_paths"]) >= 3
    for name in ("wns_setup", "tns_setup", "wns_hold", "tns_hold"):
        assert isinstance(_measurement(result, name)["value"], float)
    evidence = " ".join(result["unconstrained_endpoints"]) + result["check_setup"]
    assert "rdata0_in" in evidence
    assert "dac_data_out" in evidence or "adc_trig_in" in evidence


@needs_sta
@needs_liberty
@needs_yosys
def test_timing_mixed_spef_flows_through(tmp_path):
    from rocket_engine.adapters.synth_yosys import YosysSynthAdapter
    from rocket_engine.adapters.timing_sta import (  # RED: missing adapter
        OpenStaTimingAdapter,
    )

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
    synth = YosysSynthAdapter().parse(
        YosysSynthAdapter().execute(
            {
                "operation": "run_synth",
                "sources": staged,
                "top": "serv_top",
                "liberty": str(LIBERTY),
                "workdir": str(workdir),
            }
        )
    )
    wrapper = workdir / "top_mixed.v"
    shutil.copy(FIXTURES / "top_mixed.v", wrapper)
    sdc = workdir / "top_mixed.sdc"
    shutil.copy(FIXTURES / "top_mixed.sdc", sdc)
    spef = workdir / "top_mixed.spef"
    shutil.copy(FIXTURES / "top_mixed.spef", spef)
    job = {
        "operation": "run_timing",
        "netlist": [str(wrapper), synth["netlist"]],
        "libs": [str(LIBERTY)],
        "sdc": str(sdc),
        "spef": str(spef),
        "top": "top_mixed",
        "workdir": str(workdir),
        "timeout_s": 600,
    }
    native = OpenStaTimingAdapter().execute(job)
    assert native["exit_code"] == 0, native["log"][-2000:]
    result = OpenStaTimingAdapter().parse(native)
    assert result["critical_paths"] != []
    assert native["spef"] == str(spef)
