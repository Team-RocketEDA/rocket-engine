"""HDL-SIM RED — HdlSimAdapter behind the ToolAdapter port (run_hdl_test).

Valid RED = `rocket_engine.adapters.hdl_sim` does not exist yet, so
every test fails on ImportError. Fixtures are verified against real
Icarus (iverilog 14.0 + vvp): pass→clean, broken→compile errors,
fatal→rc 1 + FATAL, error→rc 0 + ERROR, exit1→rc 0, hang→killed.
Tests skip (never fake-green) where iverilog/vvp are unpathed; tool
placement on PATH is B10 integration scope, not test scope.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "hdl"

tools_present = shutil.which("iverilog") is not None and shutil.which("vvp") is not None
needs_icarus = pytest.mark.skipif(not tools_present, reason="iverilog/vvp not on PATH")


def _job(sources, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {"operation": "run_hdl_test", "sources": staged, "workdir": str(workdir)}
    job.update(over)
    return job


def test_hdl_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    assert issubclass(HdlSimAdapter, ToolAdapter)


def test_hdl_capabilities_advertise_run_hdl_test():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    caps = HdlSimAdapter().capabilities({"top": "tb_pass"})
    assert "run_hdl_test" in caps["operations"]
    assert caps["tool"] == "icarus"


@needs_icarus
def test_hdl_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    job = _job(["counter.v", "tb_pass.v"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.v")]
    try:
        HdlSimAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_hdl_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    job = _job(["counter.v", "tb_pass.v"], tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-hdl-tests"
    try:
        HdlSimAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for bad tool_dir")


@needs_icarus
def test_hdl_clean_tb_reports_zero(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    adapter = HdlSimAdapter()
    native = adapter.execute(_job(["counter.v", "tb_pass.v"], tmp_path))
    result = adapter.parse(native)
    assert result["total"] == 0
    assert result["violations"] == []


@needs_icarus
def test_hdl_broken_compile_reports_diagnostics(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    adapter = HdlSimAdapter()
    result = adapter.parse(adapter.execute(_job(["counter_broken.v", "tb_pass.v"], tmp_path)))
    assert result["total"] >= 1
    assert all(v["rule"] == "compile" for v in result["violations"])
    assert all(v["file"].endswith(".v") for v in result["violations"])
    assert all(isinstance(v["line"], int) for v in result["violations"])


@needs_icarus
def test_hdl_fatal_reports_assert_fatal(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    adapter = HdlSimAdapter()
    result = adapter.parse(adapter.execute(_job(["counter.v", "tb_fatal.v"], tmp_path)))
    assert result["total"] >= 1
    assert any(v["rule"] == "assert_fatal" for v in result["violations"])
    assert all(v["severity"] == "error" for v in result["violations"])


@needs_icarus
def test_hdl_error_reports_despite_exit_zero(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    adapter = HdlSimAdapter()
    native = adapter.execute(_job(["counter.v", "tb_error.v"], tmp_path))
    assert native["run"]["exit_code"] == 0
    result = adapter.parse(native)
    assert result["total"] >= 1
    assert any(v["rule"] == "assert_error" for v in result["violations"])


@needs_icarus
def test_hdl_finish_status_is_not_a_failure(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    adapter = HdlSimAdapter()
    result = adapter.parse(adapter.execute(_job(["counter.v", "tb_exit1.v"], tmp_path)))
    assert result["total"] == 0


@needs_icarus
def test_hdl_hang_raises_runner_unavailable(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    job = _job(["tb_hang.v"], tmp_path, timeout_s=3)
    try:
        HdlSimAdapter().execute(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for a hung sim")


@needs_icarus
def test_hdl_proves_labels_against_real_icarus(tmp_path):
    # Oracle check: fixture labels verified against iverilog/vvp
    # directly, not against the adapter under test.
    from rocket_engine.adapters.hdl_sim import (  # RED: missing adapter  # noqa: F401
        HdlSimAdapter,
    )

    cases = [
        (["counter.v", "tb_pass.v"], 0, 0, []),
        (["counter_broken.v", "tb_pass.v"], 2, None, ["syntax error"]),
        (["counter.v", "tb_fatal.v"], 0, 1, ["FATAL:"]),
        (["counter.v", "tb_error.v"], 0, 0, ["ERROR:"]),
        (["counter.v", "tb_exit1.v"], 0, 0, ["$finish(1)"]),
    ]
    for sources, want_compile_rc, want_run_rc, want_text in cases:
        build = subprocess.run(
            ["iverilog", "-o", "sim.vvp", *[str(FIXTURES / s) for s in sources]],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmp_path,
        )
        assert build.returncode == want_compile_rc, (sources, build.stderr)
        if want_run_rc is None:
            continue
        run = subprocess.run(
            ["vvp", "sim.vvp"], capture_output=True, text=True, timeout=60, cwd=tmp_path
        )
        assert run.returncode == want_run_rc, (sources, run.returncode)
        for text in want_text:
            assert text in run.stdout + run.stderr + build.stdout + build.stderr


def test_hdl_preflight_refuses_bad_timeout(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    job = _job(["counter.v", "tb_pass.v"], tmp_path, timeout_s=-5)
    try:
        HdlSimAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for negative timeout")


def test_hdl_parse_synthesizes_violation_on_bare_compile_failure():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    native = {
        "exit_code": 2,
        "compile": {"exit_code": 2, "stdout": "", "stderr": ""},
        "run": None,
    }
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "compile"


def test_hdl_parse_rejects_native_without_run_block():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    native = {
        "exit_code": 0,
        "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
        "run": None,
    }
    try:
        HdlSimAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for a missing run block")


def test_hdl_parse_synthesizes_violation_on_bare_sim_crash():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    native = {
        "exit_code": 139,
        "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
        "run": {"exit_code": 139, "stdout": "", "stderr": ""},
    }
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "sim_fail"


def test_hdl_parse_marks_warnings_not_errors():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter  # RED: missing adapter

    native = {
        "exit_code": 0,
        "compile": {"exit_code": 0, "stdout": "x.v:3: warning: implicit net\n", "stderr": ""},
        "run": {"exit_code": 0, "stdout": "", "stderr": ""},
    }
    result = HdlSimAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "compile"
    assert result["violations"][0]["severity"] == "warning"


needs_sandbox = pytest.mark.skipif(
    not tools_present or shutil.which("bwrap") is None,
    reason="needs iverilog/vvp and bwrap",
)


def _which_all(binary):
    found = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        cand = Path(directory) / binary
        if cand.is_file() and str(cand) not in found:
            found.append(str(cand))
    return found


def _sandboxed_adapter():
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter
    from rocket_engine.execution.runner import BwrapRunner, default_profile

    tools = [shutil.which("iverilog"), shutil.which("vvp")]
    for candidate in _which_all("bwrap"):
        runner = BwrapRunner(default_profile(tools), binary=candidate)
        try:
            runner.preflight()
        except Exception:
            continue
        return HdlSimAdapter(runner=runner)
    pytest.skip("no provable bwrap on PATH")


@needs_sandbox
def test_hdl_sandboxed_run_passes(tmp_path):
    adapter = _sandboxed_adapter()
    result = adapter.parse(adapter.execute(_job(["counter.v", "tb_pass.v"], tmp_path)))
    assert result["total"] == 0


@needs_sandbox
def test_hdl_sandbox_confines_writes(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    probe = Path("/tmp/rocketeda_escape_probe")
    probe.unlink(missing_ok=True)
    try:
        # Control: unconfined run writes through to the host.
        control = HdlSimAdapter()
        plain = control.parse(control.execute(_job(["tb_escape.v"], tmp_path)))
        assert plain["total"] == 0
        assert probe.exists()
        probe.unlink()

        # Sandboxed run: sim passes, host file never appears.
        boxed_adapter = _sandboxed_adapter()
        boxed = boxed_adapter.parse(
            boxed_adapter.execute(_job(["tb_escape.v"], tmp_path))
        )
        assert boxed["total"] == 0
        assert not probe.exists()
    finally:
        probe.unlink(missing_ok=True)


def test_hdl_runner_errors_convert_to_adapter_errors(tmp_path):
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter
    from rocket_engine.execution.errors import ExecutionError

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "iverilog").write_text("")
    (bindir / "vvp").write_text("")

    class PreflightBoom:
        def preflight(self):
            raise ExecutionError("runner_unavailable", "boom")

    class RunBoom:
        def preflight(self):
            return {"ready": True}

        def run(self, command, workdir, timeout_s=120, extra_binds=()):
            raise ExecutionError("runner_unavailable", "boom")

    job = _job(["counter.v", "tb_pass.v"], tmp_path, tool_dir=str(bindir))
    cases = [
        (HdlSimAdapter(runner=PreflightBoom()), "preflight"),
        (HdlSimAdapter(runner=RunBoom()), "execute"),
    ]
    for adapter, method in cases:
        try:
            getattr(adapter, method)(job)
        except Exception as exc:
            assert type(exc).__name__ == "AdapterError", type(exc).__name__
            assert exc.code == "runner_unavailable"
        else:
            raise AssertionError(f"expected converted AdapterError from {method}")
