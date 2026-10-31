"""SERV RED — SERV hello regression through HdlSimAdapter end-to-end.

Valid RED = `tests/adapters/fixtures/hdl/serv_harness.v` does not
exist yet, so every live test fails staging the harness (hard
failure, never a skip). The vendored SERV tree
(fixtures/upstream/serv, git-ignored) ships rtl + servile +
servant + bench; the committed harness replaces servant_tb.v
(which needs the unfetchable vlog_tb_utils) with a stub, a
watchdog, and the hello_uart firmware. Correct = hello prints
"Hi, I'm Servant!" and HALTs ($finish) with zero FATAL/ERROR
lines. Tests skip (never fake-green) where iverilog/vvp or the
upstream tree are absent; the harness itself is required.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "hdl"
ROOT = Path(__file__).resolve().parent.parent.parent
SERV = ROOT / "fixtures" / "upstream" / "serv"
HARNESS = FIXTURES / "serv_harness.v"
SOURCES_MANIFEST = FIXTURES / "serv_sources.txt"
FIRMWARE = "hello_uart.hex"

tools_present = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
needs_icarus = pytest.mark.skipif(not tools_present, reason="iverilog/vvp not on PATH")


def _require_upstream():
    if not (SERV / "rtl" / "serv_top.v").is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")
    if not SOURCES_MANIFEST.is_file():
        raise FileNotFoundError(f"SERV sources manifest missing: {SOURCES_MANIFEST}")


def _serv_sources():
    return [
        line.strip()
        for line in SOURCES_MANIFEST.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _stage(tmp_path, watchdog_units=None, corrupt=None):
    if not HARNESS.is_file():
        raise FileNotFoundError(f"SERV harness missing: {HARNESS}")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for rel in _serv_sources():
        src = SERV / rel
        if not src.is_file():
            raise FileNotFoundError(f"SERV source missing: {src}")
        dest = workdir / Path(rel).name
        text = src.read_text()
        if corrupt and Path(rel).name == corrupt:
            text += "\nthis is not verilog ;;;\n"
        dest.write_text(text)
        staged.append(str(dest))
    harness_text = HARNESS.read_text()
    if watchdog_units is not None:
        harness_text = harness_text.replace(
            "parameter watchdog_units = 200000000",
            f"parameter watchdog_units = {watchdog_units}",
        )
    harness_dest = workdir / HARNESS.name
    harness_dest.write_text(harness_text)
    staged.append(str(harness_dest))
    return workdir, staged


def _stage_firmware(workdir):
    hex_src = SERV / "sw" / FIRMWARE
    if not hex_src.is_file():
        raise FileNotFoundError(f"SERV firmware missing: {hex_src}")
    shutil.copy(hex_src, workdir / FIRMWARE)


@needs_icarus
def test_serv_hello_runs_clean_end_to_end(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_upstream()
    workdir, staged = _stage(tmp_path)
    _stage_firmware(workdir)
    job = {
        "operation": "run_hdl_test",
        "sources": staged,
        "workdir": str(workdir),
        "timeout_s": 300,
    }
    adapter = HdlSimAdapter()
    native = adapter.execute(job)
    assert native["run"]["exit_code"] == 0
    result = adapter.parse(native)
    assert result["total"] == 0, result["violations"]
    assert result["violations"] == []
    stdout = native["run"]["stdout"] + native["run"]["stderr"]
    assert "Hi, I'm Servant!" in stdout
    assert "Test complete" in stdout


@needs_icarus
def test_serv_proves_labels_against_real_icarus(tmp_path):
    # Oracle check: hello labels verified against iverilog/vvp
    # directly, not against the adapter under test.
    _require_upstream()
    workdir, staged = _stage(tmp_path)
    _stage_firmware(workdir)
    build = subprocess.run(
        ["iverilog", "-o", "sim.vvp", *staged],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=workdir,
    )
    assert build.returncode == 0, build.stderr
    run = subprocess.run(
        ["vvp", "sim.vvp"],
        capture_output=True,
        text=True,
        timeout=280,
        cwd=workdir,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "Hi, I'm Servant!" in run.stdout + run.stderr
    assert "Test complete" in run.stdout + run.stderr


@needs_icarus
def test_serv_missing_firmware_fails_loudly(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_upstream()
    workdir, staged = _stage(tmp_path, watchdog_units=5000000)
    adapter = HdlSimAdapter()
    job = {
        "operation": "run_hdl_test",
        "sources": staged,
        "workdir": str(workdir),
        "timeout_s": 280,
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert any(v["rule"] == "assert_fatal" for v in result["violations"])
    assert all(v["severity"] == "error" for v in result["violations"])


@needs_icarus
def test_serv_broken_rtl_reports_compile_error(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    _require_upstream()
    workdir, staged = _stage(tmp_path, corrupt="serv_alu.v")
    _stage_firmware(workdir)
    job = {
        "operation": "run_hdl_test",
        "sources": staged,
        "workdir": str(workdir),
        "timeout_s": 280,
    }
    adapter = HdlSimAdapter()
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert any(v["rule"] == "compile" for v in result["violations"])
