"""FORMAL-SBY RED — FormalSbyAdapter behind the ToolAdapter port (run_formal).

Valid RED = `rocket_engine.adapters.formal_sby` does not exist yet,
so every test fails on ImportError. Fixtures are verified against
real sby v0.70 (pinned oss-cad-suite): prove-pass→rc 0 proven,
bmc-pass→rc 0 bounded, bad-property→rc 2 FAIL + VCD trace,
induction-gap→rc 4 UNKNOWN, broken-source→rc 16 ERROR, cover→rc 0
+ reachability witness. Verdicts always carry scope
(proven/bounded/unknown/timeout) plus assumptions and
counterexamples — never a bare PASS. Timeout tests drive a fake
sby (deterministic, no live tools); live tests skip (never
fake-green) where sby is unpathed — tool placement on PATH is
B10 integration scope, not test scope.
"""

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "formal"
ROOT = Path(__file__).resolve().parent.parent.parent
SERV_ALU = ROOT / "fixtures" / "upstream" / "serv" / "rtl" / "serv_alu.v"

tools_present = shutil.which("sby") is not None
needs_sby = pytest.mark.skipif(not tools_present, reason="sby not on PATH")


def _job(sources, top, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {
        "operation": "run_formal",
        "sources": staged,
        "top": top,
        "mode": "bmc",
        "depth": 10,
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def _require_upstream_serv():
    if not SERV_ALU.is_file():
        pytest.skip("serv fixture not fetched (fixtures/upstream/serv)")


def _write_fake_sby(bindir, body):
    script = bindir / "sby"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
    return str(bindir)


def test_formal_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    assert issubclass(FormalSbyAdapter, ToolAdapter)


def test_formal_capabilities_advertise_run_formal():
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    caps = FormalSbyAdapter().capabilities({"top": "counter"})
    assert "run_formal" in caps["operations"]
    assert caps["tool"] == "sby"
    assert {"bmc", "prove", "cover"} <= set(caps["modes"])


def test_formal_preflight_refuses_wrong_operation(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    job = _job(["counter.v"], "counter", tmp_path, operation="run_syntax")
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_syntax")


def test_formal_preflight_refuses_foreign_deck_tool(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    job = _job(["counter.v"], "counter", tmp_path, deck={"tool": "magic"})
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for deck.tool magic")


def test_formal_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    job = _job(["counter.v"], "counter", tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.v")]
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_formal_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    job = _job(["counter.v"], "counter", tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-formal-tests"
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "PROV" in str(exc)
    else:
        raise AssertionError("expected missing_dependency for bad tool_dir")


def test_formal_missing_sby_names_prov_bundle(tmp_path, monkeypatch):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    monkeypatch.setenv("PATH", str(tmp_path))
    job = _job(["counter.v"], "counter", tmp_path)
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "PROV" in str(exc)
        assert "oss-cad-suite" in str(exc)
    else:
        raise AssertionError("expected missing_dependency without sby on PATH")


def test_formal_preflight_refuses_bad_inputs(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    cases = [
        {"timeout_s": -5},
        {"timeout_s": 0},
        {"timeout_s": "30"},
        {"mode": "abc"},
        {"mode": ""},
        {"depth": 0},
        {"depth": -2},
        {"depth": "20"},
        {"depth": True},
        {"top": ""},
        {"top": "has space"},
        {"top": "semi;colon"},
        {"top": 123},
        {"engines": []},
        {"engines": [""]},
        {"engines": "smtbmc"},
        {"engines": ["smtbmc\nboolector"]},
        {"deck": "sby"},
    ]
    for over in cases:
        over = dict(over)
        top = over.pop("top", "counter")
        job = _job(["counter.v"], top, tmp_path, **over)
        try:
            FormalSbyAdapter().preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "invalid_command", over
        else:
            raise AssertionError(f"expected invalid_command for {over!r}")


def test_formal_preflight_refuses_duplicate_basenames(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(FIXTURES / "counter.v", other / "counter.v")
    job = _job(["counter.v"], "counter", tmp_path)
    job["sources"].append(str(other / "counter.v"))
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for duplicate basenames")


def test_formal_version_probe_rejects_impostor(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    tool_dir = _write_fake_sby(
        bindir, '#!/bin/sh\necho "definitely not sby"\n'
    )
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=tool_dir)
    try:
        FormalSbyAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "PROV" in str(exc)
    else:
        raise AssertionError("expected missing_dependency for an impostor sby")


@needs_sby
def test_formal_version_asserts_pinned_sby(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    checked = FormalSbyAdapter().preflight(_job(["counter.v"], "counter", tmp_path))
    assert checked["sby_version"].startswith("SBY v0.70"), checked["sby_version"]


@needs_sby
def test_formal_prove_returns_proven_scope(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(["counter.v"], "counter", tmp_path, mode="prove", depth=10)
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    assert result["violations"] == []
    measures = result["measurements"]
    assert measures["scope"] == "proven"
    assert measures["sby_status"] == "PASS"
    assert measures["mode"] == "prove"
    assert measures["depth"] == 10
    assert measures["sby_version"].startswith("SBY ")
    assert len(measures["assumptions"]) == 1
    assert measures["assumptions"][0]["file"].endswith("counter.v")
    assert isinstance(measures["assumptions"][0]["line"], int)
    assert any(p["kind"] == "assert" for p in measures["properties"])
    assert measures["counterexamples"] == []


@needs_sby
def test_formal_bmc_pass_returns_bounded_scope(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(["counter.v"], "counter", tmp_path, mode="bmc", depth=10)
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    assert result["measurements"]["scope"] == "bounded"
    assert result["measurements"]["sby_status"] == "PASS"
    assert result["measurements"]["depth"] == 10


@needs_sby
def test_formal_bad_property_fails_with_counterexample(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(["counter_bad.v"], "counter_bad", tmp_path, mode="bmc", depth=20)
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    first = result["violations"][0]
    assert first["rule"] == "assert_fail"
    assert first["file"].endswith("counter_bad.v")
    assert isinstance(first["line"], int)
    measures = result["measurements"]
    assert measures["scope"] == "bounded"
    assert measures["sby_status"] == "FAIL"
    assert len(measures["counterexamples"]) >= 1
    trace = measures["counterexamples"][0]
    assert trace["property"] is not None
    assert isinstance(trace["step"], int)
    assert trace["present"] is True
    assert Path(trace["path"]).is_file()
    assert trace["path"].endswith(".vcd")


@needs_sby
def test_formal_induction_gap_reports_unknown(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(
        ["counter_induct.v"], "counter_induct", tmp_path, mode="prove", depth=10
    )
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    assert result["violations"][0]["rule"] == "formal_unknown"
    measures = result["measurements"]
    assert measures["scope"] == "unknown"
    assert measures["sby_status"] == "UNKNOWN"
    assert any("induction" in str(e) for e in measures["engine_status"])


@needs_sby
def test_formal_broken_source_reports_unknown_not_clean(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(["counter_broken.v"], "counter_broken", tmp_path)
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    assert result["violations"][0]["rule"] == "formal_error"
    assert "syntax error" in result["violations"][0]["message"]
    assert result["measurements"]["scope"] == "unknown"
    assert result["measurements"]["sby_status"] == "ERROR"


@needs_sby
def test_formal_cover_miss_fails_with_cover_missed(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(
        ["counter_cover_miss.v"], "counter_cover_miss", tmp_path,
        mode="cover", depth=20,
    )
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    first = result["violations"][0]
    assert first["rule"] == "cover_missed"
    assert first["file"].endswith("counter_cover_miss.v")
    assert isinstance(first["line"], int)
    assert result["measurements"]["scope"] == "bounded"
    assert result["measurements"]["sby_status"] == "FAIL"


@needs_sby
def test_formal_cover_pass_returns_bounded_with_witness(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    adapter = FormalSbyAdapter()
    job = _job(
        ["counter_cover.v"], "counter_cover", tmp_path, mode="cover", depth=20
    )
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    measures = result["measurements"]
    assert measures["scope"] == "bounded"
    assert measures["sby_status"] == "PASS"
    assert len(measures["cover_witnesses"]) >= 1
    witness = measures["cover_witnesses"][0]
    assert witness["property"] is not None
    assert witness["file"].endswith("counter_cover.v")
    assert isinstance(witness["step"], int)
    assert witness["present"] is True
    assert Path(witness["path"]).is_file()


def test_formal_timeout_reports_timeout_scope(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    pid_file = tmp_path / "pids.txt"
    tool_dir = _write_fake_sby(
        bindir,
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "SBY v0.70-fake"; exit 0; fi\n'
        f"echo $$ > {pid_file}\n"
        "sleep 60 & echo $! >> " + str(pid_file) + "\n"
        "sleep 60\n",
    )
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=tool_dir, timeout_s=3)
    started = time.monotonic()
    native = FormalSbyAdapter().execute(job)
    elapsed = time.monotonic() - started
    assert native["timed_out"] is True
    assert elapsed < 30, f"engine hung {elapsed:.1f}s on a hung sby"
    pids = [int(line) for line in pid_file.read_text().split()]
    assert len(pids) == 2
    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"sby tree survivor still alive: {pid}")
    result = FormalSbyAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "formal_timeout"
    assert result["violations"][0]["severity"] == "error"
    assert result["measurements"]["scope"] == "timeout"


def test_formal_execute_refuses_missing_workdir(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    tool_dir = _write_fake_sby(
        bindir, '#!/bin/sh\necho "SBY v0.70-fake"\n'
    )
    job = _job(["counter.v"], "counter", tmp_path, tool_dir=tool_dir)
    job["workdir"] = str(tmp_path / "ghost-dir")
    try:
        FormalSbyAdapter().execute(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a missing workdir")


def test_formal_parse_rejects_native_without_status(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    workdir = tmp_path / "work"
    workdir.mkdir()
    native = {
        "exit_code": 0,
        "stdout": "sby said nothing useful\n",
        "stderr": "",
        "timed_out": False,
        "workdir": str(workdir),
        "sby_file": str(workdir / "formal.sby"),
        "sources": [],
        "mode": "bmc",
        "depth": 10,
        "top": "counter",
        "sby_version": "SBY v0.70-fake",
        "timeout_s": 300,
    }
    try:
        FormalSbyAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for statusless output")


def test_formal_parse_reports_bare_error_without_span(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    workdir = tmp_path / "work"
    workdir.mkdir()
    native = {
        "exit_code": 16,
        "stdout": (
            "SBY 19:18:14 [cover_miss] base: ERROR: Module `ghost' not found!\n"
            "SBY 19:18:14 [cover_miss] DONE (ERROR, rc=16)\n"
        ),
        "stderr": "",
        "timed_out": False,
        "workdir": str(workdir),
        "sby_file": str(workdir / "formal.sby"),
        "sources": [],
        "mode": "bmc",
        "depth": 10,
        "top": "ghost",
        "sby_version": "SBY v0.70-fake",
        "timeout_s": 300,
    }
    result = FormalSbyAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "formal_error"
    assert result["violations"][0]["severity"] == "error"
    assert "ghost" in result["violations"][0]["message"]
    assert "file" not in result["violations"][0]
    assert result["measurements"]["scope"] == "unknown"
    assert result["measurements"]["sby_status"] == "ERROR"


def test_formal_parse_synthesizes_violation_on_bare_fail(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    workdir = tmp_path / "work"
    jobdir = workdir / "formal"
    jobdir.mkdir(parents=True)
    (jobdir / "status").write_text("FAIL 2 0\n")
    native = {
        "exit_code": 2,
        "stdout": "no summary lines at all\n",
        "stderr": "",
        "timed_out": False,
        "workdir": str(workdir),
        "sby_file": str(workdir / "formal.sby"),
        "sources": [],
        "mode": "bmc",
        "depth": 10,
        "top": "counter",
        "sby_version": "SBY v0.70-fake",
        "timeout_s": 300,
    }
    result = FormalSbyAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "assert_fail"
    assert result["violations"][0]["severity"] == "error"
    assert result["measurements"]["scope"] == "bounded"


def test_formal_runner_errors_convert_to_adapter_errors(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing
    from rocket_engine.execution.errors import ExecutionError

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    tool_dir = _write_fake_sby(
        bindir, '#!/bin/sh\necho "SBY v0.70-fake"\n'
    )

    class PreflightBoom:
        def preflight(self):
            raise ExecutionError("runner_unavailable", "boom")

    class RunBoom:
        def preflight(self):
            return {"ready": True}

        def run(self, command, workdir, timeout_s=120, extra_binds=()):
            raise ExecutionError("runner_unavailable", "boom")

    job = _job(["counter.v"], "counter", tmp_path, tool_dir=tool_dir)
    cases = [
        (FormalSbyAdapter(runner=PreflightBoom()), "preflight"),
        (FormalSbyAdapter(runner=RunBoom()), "execute"),
    ]
    for adapter, method in cases:
        try:
            getattr(adapter, method)(job)
        except Exception as exc:
            assert type(exc).__name__ == "AdapterError", type(exc).__name__
            assert exc.code == "runner_unavailable"
        else:
            raise AssertionError(f"expected converted AdapterError from {method}")


def test_formal_runner_timeout_reports_timeout_scope(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing
    from rocket_engine.execution.errors import ExecutionError

    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    tool_dir = _write_fake_sby(
        bindir, '#!/bin/sh\necho "SBY v0.70-fake"\n'
    )

    class TimeoutRunner:
        def preflight(self):
            return {"ready": True}

        def run(self, command, workdir, timeout_s=120, extra_binds=()):
            raise ExecutionError(
                "runner_unavailable",
                f"Sandboxed run timed out after {timeout_s}s.",
            )

    job = _job(["counter.v"], "counter", tmp_path, tool_dir=tool_dir, timeout_s=7)
    native = FormalSbyAdapter(runner=TimeoutRunner()).execute(job)
    assert native["timed_out"] is True
    result = FormalSbyAdapter().parse(native)
    assert result["measurements"]["scope"] == "timeout"
    assert result["violations"][0]["rule"] == "formal_timeout"


@needs_sby
def test_formal_proves_labels_against_real_sby(tmp_path):
    # Oracle check: fixture labels verified against sby directly,
    # not against the adapter under test.
    from rocket_engine.adapters.formal_sby import (  # RED: missing  # noqa: F401
        FormalSbyAdapter,
    )

    cases = [
        ("counter.v", "counter", "prove", 10, 0, "DONE (PASS, rc=0)"),
        ("counter_bad.v", "counter_bad", "bmc", 20, 2, "DONE (FAIL, rc=2)"),
        ("counter_induct.v", "counter_induct", "prove", 10, 4, "DONE (UNKNOWN, rc=4)"),
        ("counter_broken.v", "counter_broken", "bmc", 10, 16, "DONE (ERROR, rc=16)"),
        ("counter_cover.v", "counter_cover", "cover", 20, 0, "DONE (PASS, rc=0)"),
        (
            "counter_cover_miss.v", "counter_cover_miss", "cover", 20, 2,
            "DONE (FAIL, rc=2)",
        ),
    ]
    for name, top, mode, depth, want_rc, want_done in cases:
        workdir = tmp_path / f"oracle-{top}"
        workdir.mkdir()
        shutil.copy(FIXTURES / name, workdir / name)
        (workdir / "oracle.sby").write_text(
            f"[options]\nmode {mode}\ndepth {depth}\n\n"
            "[engines]\nsmtbmc boolector\n\n"
            f"[script]\nread -formal {name}\nprep -top {top}\n\n"
            f"[files]\n{name}\n"
        )
        proc = subprocess.run(
            ["sby", "-f", "oracle.sby"],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=workdir,
        )
        assert proc.returncode == want_rc, (name, proc.stdout[-2000:])
        assert want_done in proc.stdout, (name, proc.stdout[-2000:])
    bad_traces = list((tmp_path / "oracle-counter_bad").glob("oracle/engine_0/*.vcd"))
    assert len(bad_traces) >= 1


@needs_sby
def test_formal_serv_property_returns_scoped_verdict(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    _require_upstream_serv()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for src in (SERV_ALU, FIXTURES / "serv_alu_prop.v"):
        dest = workdir / src.name
        shutil.copy(src, dest)
        staged.append(str(dest))
    job = {
        "operation": "run_formal",
        "sources": staged,
        "top": "serv_alu_prop",
        "mode": "bmc",
        "depth": 5,
        "workdir": str(workdir),
    }
    adapter = FormalSbyAdapter()
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0, result["violations"]
    measures = result["measurements"]
    assert measures["scope"] == "bounded"
    assert measures["sby_status"] == "PASS"
    assert measures["top"] == "serv_alu_prop"
    assert any(p["kind"] == "assert" for p in measures["properties"])
    assert measures["sby_version"].startswith("SBY ")


@needs_sby
def test_formal_serv_bad_property_fails_with_trace(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing

    _require_upstream_serv()
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for src in (SERV_ALU, FIXTURES / "serv_alu_bad.v"):
        dest = workdir / src.name
        shutil.copy(src, dest)
        staged.append(str(dest))
    job = {
        "operation": "run_formal",
        "sources": staged,
        "top": "serv_alu_bad",
        "mode": "bmc",
        "depth": 5,
        "workdir": str(workdir),
    }
    adapter = FormalSbyAdapter()
    result = adapter.parse(adapter.execute(job))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    assert result["measurements"]["scope"] == "bounded"
    assert len(result["measurements"]["counterexamples"]) >= 1
    trace = result["measurements"]["counterexamples"][0]
    assert trace["present"] is True
    assert Path(trace["path"]).is_file()


@needs_sby
def test_formal_engine_wiring_routes_run_formal(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # RED: missing
    from rocket_engine.composition import Engine

    engine = Engine("probe", actor="probe")
    if not engine.solvers_for("run_formal"):
        pytest.skip("wiring patch not applied: run_formal unregistered")
    assert isinstance(
        engine.solvers_for("run_formal").get("sby"), FormalSbyAdapter
    )
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = workdir / "counter.v"
    shutil.copy(FIXTURES / "counter.v", staged)
    completion = engine.run(
        {
            "project_id": "probe",
            "operation": "run_formal",
            "arguments": {
                "sources": [str(staged)],
                "top": "counter",
                "mode": "prove",
                "depth": 10,
                "workdir": str(workdir),
            },
        }
    )
    assert completion["verdict"]["status"] == "PASS"
    assert completion["verdict"]["measurements"]["scope"] == "proven"


@needs_sby
def test_formal_capabilities_report_covers_sby(tmp_path):
    from rocket_engine.composition import Engine  # noqa: F401  # RED: missing adapter

    from rocket_engine.adapters.formal_sby import FormalSbyAdapter  # noqa: F401

    engine = Engine("probe", actor="probe")
    if not engine.solvers_for("run_formal"):
        pytest.skip("wiring patch not applied: run_formal unregistered")
    report = engine.capabilities(engine_root=str(tmp_path / "nostore"))
    detail = report["operations"]["run_formal"]
    assert detail["readiness"] != "unsupported"
    assert "sby" in detail["tools"]
