"""SYNTH-YOSYS RED — YosysSynthAdapter behind the ToolAdapter port (run_synth).

Valid RED = `rocket_engine.adapters.synth_yosys` does not exist yet,
so every test fails on ImportError. Fixtures are verified against
real Yosys 0.70 (oss-cad-suite): counter synthesizes clean to
generic cells, sky130_fd_sc_hd liberty mapping yields sky130 cells
plus a chip area, latch/undriven RTL exits 0 with warnings as
findings, and broken RTL exits nonzero with ERROR lines.

Tests skip (never fake-green) where yosys is unpathed, the ambient
sky130 liberty is absent (mapped tests only), or the vendored
SERV/picorv32 trees are unfetched. Tool placement on PATH is B10
integration scope, not test scope.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "synth"
ROOT = Path(__file__).resolve().parent.parent.parent
SERV = ROOT / "fixtures" / "upstream" / "serv"
PICORV32 = ROOT / "fixtures" / "upstream" / "picorv32"
SERV_MANIFEST = Path(__file__).parent / "fixtures" / "hdl" / "serv_sources.txt"

_LIBERTY_DEFAULT = (
    Path.home()
    / ".local/share/pdk/sky130A/libs.ref/sky130_fd_sc_hd/lib"
    / "sky130_fd_sc_hd__tt_100C_1v80.lib"
)
LIBERTY = Path(os.environ.get("SYNTH_YOSYS_LIBERTY", str(_LIBERTY_DEFAULT)))

yosys_present = shutil.which("yosys") is not None
needs_yosys = pytest.mark.skipif(not yosys_present, reason="yosys not on PATH")
needs_liberty = pytest.mark.skipif(
    not LIBERTY.is_file(), reason=f"sky130 liberty absent: {LIBERTY}"
)


def _job(sources, top, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / Path(name).name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": top,
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def _require_serv():
    if not (SERV / "rtl" / "serv_top.v").is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")
    if not SERV_MANIFEST.is_file():
        raise FileNotFoundError(f"SERV sources manifest missing: {SERV_MANIFEST}")


def _stage_serv_rtl(tmp_path, corrupt=None):
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
        text = src.read_text()
        if corrupt and Path(rel).name == corrupt:
            text += "\nthis is not verilog ;;;\n"
        dest = workdir / Path(rel).name
        dest.write_text(text)
        staged.append(str(dest))
    return workdir, staged


def _stage_picorv32(tmp_path):
    if not (PICORV32 / "picorv32.v").is_file():
        pytest.skip("picorv32 fixture not fetched (fixtures/upstream/picorv32)")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    dest = workdir / "picorv32.v"
    shutil.copy(PICORV32 / "picorv32.v", dest)
    return workdir, [str(dest)]


def _errors(result):
    return [v for v in result["violations"] if v["severity"] == "error"]


def test_synth_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    assert issubclass(YosysSynthAdapter, ToolAdapter)


def test_synth_capabilities_advertise_run_synth():
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    caps = YosysSynthAdapter().capabilities({"top": "counter"})
    assert "run_synth" in caps["operations"]
    assert caps["tool"] == "yosys"


def test_synth_preflight_refuses_wrong_operation(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, operation="run_hdl_test")
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "unsupported_operation"


@pytest.mark.parametrize("top", ["", None, "not a top", "counter; rm -rf /", "a.b"])
def test_synth_preflight_refuses_bad_top(tmp_path, top):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["top"] = top
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


def test_synth_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.v")]
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_synth_preflight_refuses_bad_defines(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path, defines=["NOPE; rm -rf /"])
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_command"


def test_synth_preflight_refuses_missing_liberty(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["liberty"] = str(tmp_path / "ghost.lib")
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "invalid_reference"


def test_synth_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-synth-tests"
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().preflight(job)
    assert getattr(caught.value, "code", None) == "missing_dependency"
    assert "oss-cad-suite" in str(caught.value)


@needs_yosys
def test_synth_preflight_records_yosys_version(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    checked = YosysSynthAdapter().preflight(_job(["counter.v"], "counter", tmp_path))
    assert re.match(r"Yosys \d+\.\d+", checked["yosys_version"]), checked


def test_synth_parse_without_verdict_raises():
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_synth_parse_failed_run_without_errors_synthesizes_error():
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    result = YosysSynthAdapter().parse({"exit_code": 1, "log": "", "stat": ""})
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in _errors(result))
    assert any(v["rule"] == "synth_error" for v in result["violations"])


def test_synth_parse_classifies_latch_and_undriven_rules(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    netlist = tmp_path / "net.v"
    netlist.write_text("module top(); endmodule\n")

    log = (
        "Warning: Latch inferred for signal `\\top.\\q' from process `x'.\n"
        "Warning: Wire top.\\w is used but has no driver.\n"
        "ABC: Warning: The network is combinational (noise, not a finding).\n"
        "Warnings: 2 unique messages, 2 total\n"
    )
    stat = "\n=== top ===\n\n  2 wires\n  3 cells\n  2   $_DLATCH_P_\n  1   $_NOT_\n"
    result = YosysSynthAdapter().parse(
        {"exit_code": 0, "log": log, "stat": stat, "netlist": str(netlist)}
    )
    rules = {v["rule"] for v in result["violations"]}
    assert rules == {"latch", "undriven"}
    assert result["total"] == 2
    assert _errors(result) == []
    assert result["cell_count"] == 3
    assert result["cells"] == {"$_DLATCH_P_": 2, "$_NOT_": 1}


@needs_yosys
def test_synth_counter_generic_reports_cells_and_netlist(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    adapter = YosysSynthAdapter()
    native = adapter.execute(_job(["counter.v"], "counter", tmp_path))
    assert native["exit_code"] == 0
    assert native["mapped"] is False
    result = adapter.parse(native)
    assert _errors(result) == [], result["violations"]
    assert result["cell_count"] > 0
    assert any(name.startswith("$_DFF") for name in result["cells"])
    assert any(name.startswith("$_") for name in result["cells"])
    netlist = Path(result["netlist"])
    assert netlist.is_file()
    assert "module counter" in netlist.read_text()
    assert result["area"] is None
    assert native["yosys_version"].startswith("Yosys ")
    names = {m["name"] for m in result["measurements"]}
    assert {"cell_count", "wire_count"} <= names


@needs_yosys
@needs_liberty
def test_synth_counter_mapped_reports_sky130_cells_and_area(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    adapter = YosysSynthAdapter()
    job = _job(["counter.v"], "counter", tmp_path, liberty=str(LIBERTY))
    native = adapter.execute(job)
    assert native["exit_code"] == 0
    assert native["mapped"] is True
    result = adapter.parse(native)
    assert _errors(result) == [], result["violations"]
    assert any(name.startswith("sky130_fd_sc_hd__") for name in result["cells"])
    assert result["area"] is not None and result["area"] > 0
    netlist = Path(result["netlist"])
    assert "sky130_fd_sc_hd" in netlist.read_text()
    assert any(m["name"] == "area" for m in result["measurements"])


@needs_yosys
def test_synth_oracle_matches_direct_yosys_stat(tmp_path):
    # Oracle check: cell counts verified against yosys directly,
    # not against the adapter under test.
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    job = _job(["counter.v"], "counter", tmp_path)
    result = YosysSynthAdapter().parse(YosysSynthAdapter().execute(job))
    workdir = Path(job["workdir"])
    script = workdir / "oracle.ys"
    script.write_text(
        "read_verilog counter.v\nhierarchy -check -top counter\n"
        "synth -top counter\ntee -o oracle_stat.txt stat\n"
    )
    proc = subprocess.run(
        ["yosys", "-q", "-s", str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=workdir,
    )
    assert proc.returncode == 0, proc.stderr
    oracle_cells = {}
    for line in (workdir / "oracle_stat.txt").read_text().splitlines():
        match = re.match(r"^\s*(\d+)\s+(\$_\S+)\s*$", line)
        if match:
            oracle_cells[match.group(2)] = int(match.group(1))
    assert oracle_cells != {}
    assert result["cells"] == oracle_cells


@needs_yosys
def test_synth_latch_undriven_surface_as_findings(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    adapter = YosysSynthAdapter()
    native = adapter.execute(_job(["latch_undriven.v"], "latch_undriven", tmp_path))
    assert native["exit_code"] == 0
    result = adapter.parse(native)
    rules = {v["rule"] for v in result["violations"]}
    assert "latch" in rules, result["violations"]
    assert "undriven" in rules, result["violations"]
    assert _errors(result) == []
    assert any("DLATCH" in name for name in result["cells"])


@needs_yosys
def test_synth_broken_rtl_fails_loudly(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    adapter = YosysSynthAdapter()
    native = adapter.execute(_job(["broken.v"], "broken", tmp_path))
    assert native["exit_code"] != 0
    result = adapter.parse(native)
    assert result["total"] >= 1
    assert any(v["rule"] == "synth_error" for v in result["violations"])
    assert _errors(result) != []


@needs_yosys
def test_synth_missing_top_fails_loudly(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    adapter = YosysSynthAdapter()
    native = adapter.execute(_job(["counter.v"], "nosuchtop", tmp_path))
    assert native["exit_code"] != 0
    result = adapter.parse(native)
    assert any(v["rule"] == "synth_error" for v in result["violations"])
    assert any("nosuchtop" in v["message"] for v in result["violations"])


@needs_yosys
def test_synth_serv_generic_proves_cell_families(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    workdir, staged = _stage_serv_rtl(tmp_path)
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": "serv_top",
        "workdir": str(workdir),
    }
    adapter = YosysSynthAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    assert result["cell_count"] > 100
    assert any("DFF" in name or "SDFF" in name for name in result["cells"])
    assert any(
        name in result["cells"]
        for name in ("$_NAND_", "$_NOR_", "$_AND_", "$_OR_", "$_MUX_", "$_XOR_")
    )


@needs_yosys
@needs_liberty
def test_synth_serv_mapped_reports_sky130_area(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    workdir, staged = _stage_serv_rtl(tmp_path)
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": "serv_top",
        "workdir": str(workdir),
        "liberty": str(LIBERTY),
    }
    adapter = YosysSynthAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    assert any(name.startswith("sky130_fd_sc_hd__") for name in result["cells"])
    assert result["area"] is not None and result["area"] > 0
    assert "sky130_fd_sc_hd" in Path(result["netlist"]).read_text()


@needs_yosys
def test_synth_serv_mutated_rtl_fails_loudly(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    workdir, staged = _stage_serv_rtl(tmp_path, corrupt="serv_alu.v")
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": "serv_top",
        "workdir": str(workdir),
    }
    adapter = YosysSynthAdapter()
    native = adapter.execute(job)
    assert native["exit_code"] != 0
    result = adapter.parse(native)
    assert any(v["rule"] == "synth_error" for v in result["violations"])


@needs_yosys
def test_synth_picorv32_generic_proves_cell_families(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    workdir, staged = _stage_picorv32(tmp_path)
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": "picorv32",
        "workdir": str(workdir),
        "defines": ["COMPRESSED_ISA"],
    }
    adapter = YosysSynthAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    assert result["cell_count"] > 1000
    assert any("DFF" in name or "SDFF" in name for name in result["cells"])


@needs_yosys
@needs_liberty
def test_synth_picorv32_mapped_reports_sky130_area(tmp_path):
    from rocket_engine.adapters.synth_yosys import (  # RED: missing adapter
        YosysSynthAdapter,
    )

    workdir, staged = _stage_picorv32(tmp_path)
    job = {
        "operation": "run_synth",
        "sources": staged,
        "top": "picorv32",
        "workdir": str(workdir),
        "defines": ["COMPRESSED_ISA"],
        "liberty": str(LIBERTY),
    }
    adapter = YosysSynthAdapter()
    result = adapter.parse(adapter.execute(job))
    assert _errors(result) == [], result["violations"]
    assert any(name.startswith("sky130_fd_sc_hd__") for name in result["cells"])
    assert result["area"] is not None and result["area"] > 0
    assert "sky130_fd_sc_hd" in Path(result["netlist"]).read_text()
