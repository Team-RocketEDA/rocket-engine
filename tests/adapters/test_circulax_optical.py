"""PHOTONIC-WIRE RED — CirculaxAdapter behind run_optical (deck.tool circulax).

Valid RED = `src/adapters/circulax/adapter.py` does not exist yet, so
the loader below fails on FileNotFoundError. Project circuit YAML in,
transient out — never the hardcoded RC smoke (`run_rc_step` stays the
qualification smoke; this op generalizes it to any R/C/V/t1/observe
spec). Fixtures replay the CIRCULAX-LIVE proof numbers (good RC
Vc(5us)=0.9933 passes 0.9 V, slow RC 0.0488 misses it). Live tests
skip (never fake-green) where circulax is uninstalled; unit tests use
canned driver envelopes and FakeRunners.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "circulax"

circulax_present = importlib.util.find_spec("circulax") is not None
needs_circulax = pytest.mark.skipif(
    not circulax_present,
    reason="circulax not installed (uv sync --group photonic)",
)


def _load_adapter():
    # RED: src/adapters/circulax/adapter.py does not exist yet.
    path = ROOT / "src" / "adapters" / "circulax" / "adapter.py"
    spec = importlib.util.spec_from_file_location(
        "circulax_optical_adapter", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _job(sources, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {"operation": "run_optical", "sources": staged,
           "workdir": str(workdir)}
    job.update(over)
    return job


def _trace(final=0.9933, points=11, t1=5e-6):
    # Monotone charge curve ending at `final`; shape is canned, the
    # parse math (nearest-sample lookup, margins) is what's pinned.
    grid = [i * t1 / (points - 1) for i in range(points)]
    curve = [final * (1 - 0.5 ** (i + 1)) / (1 - 0.5 ** points)
             for i in range(points)]
    curve[-1] = final
    return grid, curve


def _ok_envelope(t_s, v_V, observe="C1,p1"):
    return json.dumps(
        {
            "ok": True,
            "circulax_version": "0.2.5-canned",
            "result": {
                "t_s": list(t_s),
                "v_V": list(v_V),
                "final_V": v_V[-1],
                "observe": observe,
                "t1_s": t_s[-1],
                "points": len(t_s),
            },
        }
    )


def _good_native(**over):
    t_s, v_V = _trace(final=0.9933)
    native = {
        "exit_code": 0,
        "stdout": _ok_envelope(t_s, v_V),
        "stderr": "",
        "spec": str(FIXTURES / "good_rc.yml"),
        "spec_text": (FIXTURES / "good_rc.yml").read_text(),
        "targets": [{"at_s": 5e-6, "min_V": 0.9}],
        "observe": "C1,p1",
    }
    native.update(over)
    return native


class FakeRunner:
    def __init__(self, stdout, exit_code=0):
        self._stdout = stdout
        self._exit_code = exit_code
        self.seen = {}

    def preflight(self):
        return {"ready": True}

    def run(self, command, workdir, timeout_s=120, extra_binds=()):
        self.seen["command"] = command
        self.seen["workdir"] = workdir
        self.seen["timeout_s"] = timeout_s
        self.seen["extra_binds"] = extra_binds
        return subprocess.CompletedProcess(
            command, self._exit_code, self._stdout, ""
        )


def test_circulax_optical_adapter_exists():
    mod = _load_adapter()  # RED: missing module
    assert mod.OPERATION == "run_optical"
    assert callable(mod.CirculaxAdapter)


def test_circulax_optical_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface

    mod = _load_adapter()  # RED: missing module
    assert issubclass(mod.CirculaxAdapter, ToolAdapter)


def test_circulax_optical_capabilities_advertise_tool():
    mod = _load_adapter()  # RED: missing module
    caps = mod.CirculaxAdapter().capabilities({"circuit": "rc-step"})
    assert caps["operations"] == ["run_optical"]
    assert caps["tool"] == "circulax"


def test_circulax_optical_preflight_refuses_bad_operation(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path, operation="run_spice")
    try:
        mod.CirculaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_spice")


def test_circulax_optical_preflight_refuses_missing_sources(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.yml")]
    try:
        mod.CirculaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_circulax_optical_preflight_refuses_bad_timeout(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path, timeout_s=0)
    try:
        mod.CirculaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for timeout 0")


def test_circulax_optical_preflight_refuses_bad_connection(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(
        bad.read_text().replace("V1,p1: R1,p1", "V1.p1: R1.p1"))
    try:
        mod.CirculaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for dot-separated ref")


def test_circulax_optical_preflight_refuses_unknown_component(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(bad.read_text().replace("resistor", "memristor"))
    try:
        mod.CirculaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for memristor")


def test_circulax_optical_preflight_accepts_op_fixture(tmp_path):
    mod = _load_adapter()  # RED: missing module
    checked = mod.CirculaxAdapter().preflight(_job(["good_rc.yml"], tmp_path))
    assert checked["spec"].endswith("good_rc.yml")
    assert checked["doc"]["circuit"] == "rc-step-good"
    assert checked["timeout_s"] == 120


def test_circulax_optical_parse_passes_good_trace():
    mod = _load_adapter()  # RED: missing module
    got = mod.CirculaxAdapter().parse(_good_native())
    assert got["total"] == 0
    assert got["violations"] == []
    assert len(got["measurements"]) == 1
    meas = got["measurements"][0]
    assert meas["value"] == pytest.approx(0.9933, abs=1e-9)
    assert meas["unit"] == "V"
    assert meas["margin"] == pytest.approx(0.0933, abs=1e-9)
    assert meas["status"] == "pass"
    assert got["transient"]["observe"] == "C1,p1"
    assert got["circulax_version"] == "0.2.5-canned"


def test_circulax_optical_parse_fails_slow_trace():
    mod = _load_adapter()  # RED: missing module
    t_s, v_V = _trace(final=0.0488)
    native = _good_native(stdout=_ok_envelope(t_s, v_V))
    got = mod.CirculaxAdapter().parse(native)
    assert got["total"] == 1
    assert got["measurements"][0]["status"] == "fail"
    assert got["measurements"][0]["margin"] < 0
    violation = got["violations"][0]
    assert violation["rule"] == "transient"
    assert violation["severity"] == "error"
    assert violation["file"] == native["spec"]
    assert violation["sim_time"] == pytest.approx(5e-6)


def test_circulax_optical_parse_invalid_circuit_synthesizes_violation():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "invalid_circuit",
                    "message": "KeyError: 'ghost'",
                    "token": "ghost",
                    "line": 7,
                },
            }
        )
    )
    got = mod.CirculaxAdapter().parse(native)
    assert got["total"] == 1
    assert got["violations"][0]["rule"] == "circuit"
    assert got["violations"][0]["line"] == 7
    assert got["measurements"] == []


def test_circulax_optical_parse_missing_dependency_raises():
    mod = _load_adapter()  # RED: missing module
    native = _good_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "missing_dependency",
                    "message": "circulax is not importable",
                    "token": None,
                    "line": None,
                },
            }
        )
    )
    try:
        mod.CirculaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency")


def test_circulax_optical_parse_no_envelope_raises(tmp_path):
    mod = _load_adapter()  # RED: missing module
    native = _good_native(stdout="Traceback (most recent call last): boom\n")
    try:
        mod.CirculaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")


def test_circulax_optical_execute_stages_driver_and_job(tmp_path):
    mod = _load_adapter()  # RED: missing module
    t_s, v_V = _trace(final=0.9933)
    runner = FakeRunner(_ok_envelope(t_s, v_V))
    job = _job(["good_rc.yml"], tmp_path)
    native = mod.CirculaxAdapter(runner=runner).execute(job)
    assert native["exit_code"] == 0
    assert native["targets"] == [{"at_s": 5e-6, "min_V": 0.9}]
    assert native["observe"] == "C1,p1"
    assert (Path(job["workdir"]) / "circulax_driver.py").is_file()
    assert (Path(job["workdir"]) / "circulax_job.json").is_file()
    assert runner.seen["command"][1:] == [
        "circulax_driver.py", "circulax_job.json"]


def test_circulax_optical_driver_consumes_project_circuit():
    # Generalization law: the staged driver must build its netlist
    # from the project spec — a hardcoded RC would re-qualify the
    # smoke instead of generalizing it.
    text = (ROOT / "src" / "adapters" / "circulax" / "_driver.py").read_text()
    assert 'doc["instances"]' in text
    assert 'doc.get("connections")' in text
    assert 'doc["transient"]' in text
    assert "compile_circuit" in text


def test_circulax_optical_dispatches_as_engine_run(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    t_s, v_V = _trace(final=0.9933)
    engine = Engine("photonic-wire-circulax", actor="tester")
    engine.register_solver(
        "run_optical", mod.CirculaxAdapter(runner=FakeRunner(
            _ok_envelope(t_s, v_V))), tool="circulax")
    job = _job(["good_rc.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "photonic-wire-circulax",
            "operation": "run_optical",
            "arguments": {
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "circulax"},
            },
        }
    )
    assert out["operation"] == "run_optical"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert out["verdict"]["measurements"][0]["status"] == "pass"
    events = engine.events_since(0)
    assert any(
        e.get("event") == "run_completed" and e.get("data", {}).get(
            "run_id") == out["run_id"] for e in events
    ), events


def test_circulax_optical_dispatch_fail_carries_run_id(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    t_s, v_V = _trace(final=0.0488)
    engine = Engine("photonic-wire-circulax", actor="tester")
    engine.register_solver(
        "run_optical", mod.CirculaxAdapter(runner=FakeRunner(
            _ok_envelope(t_s, v_V))), tool="circulax")
    job = _job(["slow_rc.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "photonic-wire-circulax",
            "operation": "run_optical",
            "arguments": {
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "circulax"},
            },
        }
    )
    assert out["run_id"]
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["rule"] == "transient" for f in found)


@needs_circulax
def test_circulax_optical_live_good_rc_passes(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["good_rc.yml"], tmp_path)
    adapter = mod.CirculaxAdapter()
    got = adapter.parse(adapter.execute(job))
    assert got["measurements"][0]["value"] == pytest.approx(0.9933, abs=1e-3)
    assert got["total"] == 0


@needs_circulax
def test_circulax_optical_live_slow_rc_fails(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["slow_rc.yml"], tmp_path)
    adapter = mod.CirculaxAdapter()
    got = adapter.parse(adapter.execute(job))
    assert got["measurements"][0]["value"] == pytest.approx(0.0488, abs=1e-3)
    assert got["total"] == 1
    assert got["violations"][0]["rule"] == "transient"
