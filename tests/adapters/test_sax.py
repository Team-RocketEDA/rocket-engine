"""SAX RED — SaxAdapter behind the ToolAdapter port (run_optical).

Valid RED = `rocket_engine.adapters.sax` does not exist yet, so
every non-live test fails on ImportError. Fixtures are verified
against real sax 0.18.2: balanced MZI cross 1.0 / bar 0.0, all-pass
ring through 1.0, mistuned MZI cross ~0.3397 (-4.689 dB), broken
link raises KeyError('ghost'). Live tests skip (never fake-green)
where sax is uninstalled; unit tests use canned driver envelopes
and FakeRunners. sax resolves in the engine interpreter (pip
`photonic` group); an explicit job `tool_dir` may point at a
directory containing an alternate python.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "sax"

sax_present = importlib.util.find_spec("sax") is not None
needs_sax = pytest.mark.skipif(not sax_present, reason="sax not installed (uv sync --group photonic)")


def _job(sources, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = []
    for name in sources:
        dest = workdir / name
        shutil.copy(FIXTURES / name, dest)
        staged.append(str(dest))
    job = {"operation": "run_optical", "sources": staged, "workdir": str(workdir)}
    job.update(over)
    return job


def _ok_envelope(pairs, wavelength_nm=(1540.0, 1550.0, 1560.0)):
    return json.dumps(
        {
            "ok": True,
            "sax_version": "0.18.2-canned",
            "result": {
                "wavelength_nm": list(wavelength_nm),
                "transmission": {key: list(values) for key, values in pairs.items()},
                "ports": sorted({p for key in pairs for p in key.split(">")}),
            },
        }
    )


def _mzi_native(**over):
    native = {
        "exit_code": 0,
        "stdout": _ok_envelope(
            {"in0>out1": [1.0, 1.0, 1.0], "in0>out0": [0.0, 0.0, 0.0]}
        ),
        "stderr": "",
        "spec": str(FIXTURES / "mzi.yml"),
        "targets": [
            {"from": "in0", "to": "out1", "at_nm": 1550.0, "min_db": -0.5},
            {"from": "in0", "to": "out0", "at_nm": 1550.0, "max_db": -40.0},
        ],
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
        return subprocess.CompletedProcess(command, self._exit_code, self._stdout, "")


def test_sax_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    assert issubclass(SaxAdapter, ToolAdapter)


def test_sax_capabilities_advertise_run_optical():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    caps = SaxAdapter().capabilities({"circuit": "mzi"})
    assert "run_optical" in caps["operations"]
    assert caps["tool"] == "sax"


def test_sax_preflight_refuses_bad_operation(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path, operation="run_spice")
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_spice")


def test_sax_preflight_refuses_missing_sources(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.yml")]
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_sax_preflight_refuses_missing_tools(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path)
    job["tool_dir"] = "/nonexistent-dir-for-sax-tests"
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for bad tool_dir")


def test_sax_preflight_refuses_bad_timeout(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path, timeout_s=0)
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for zero timeout")


def test_sax_preflight_refuses_malformed_yaml(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["not_yaml.yml"], tmp_path)
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for unparseable spec")


def test_sax_preflight_refuses_bad_sweep(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path)
    spec = Path(job["sources"][0])
    spec.write_text(
        spec.read_text().replace(
            "sweep: {start_nm: 1540.0, stop_nm: 1560.0, points: 3}",
            "sweep: {start_nm: 1560.0, stop_nm: 1540.0, points: 3}",
        )
    )
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for an inverted sweep")


def test_sax_preflight_refuses_target_without_bounds(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    job = _job(["mzi.yml"], tmp_path)
    spec = Path(job["sources"][0])
    spec.write_text(
        spec.read_text().replace("min_db: -0.5", "note: bounds dropped")
    )
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a boundless target")


def test_sax_preflight_refuses_dot_separated_port_refs(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter

    job = _job(["mzi.yml"], tmp_path)
    spec = Path(job["sources"][0])
    spec.write_text(spec.read_text().replace("c1,in0", "c1" + "." + "in0"))
    try:
        SaxAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a dotted port ref")


@needs_sax
def test_sax_mzi_reproduces_documented_transmission(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    adapter = SaxAdapter()
    result = adapter.parse(adapter.execute(_job(["mzi.yml"], tmp_path)))
    assert result["total"] == 0
    assert result["violations"] == []
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["T(in0->out1)@1550.0nm"]["value"] == pytest.approx(0.0, abs=1e-9)
    assert by_name["T(in0->out1)@1550.0nm"]["unit"] == "dB"
    assert by_name["T(in0->out1)@1550.0nm"]["status"] == "pass"
    assert by_name["T(in0->out0)@1550.0nm"]["status"] == "pass"


@needs_sax
def test_sax_ring_reproduces_documented_transmission(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    adapter = SaxAdapter()
    result = adapter.parse(adapter.execute(_job(["ring.yml"], tmp_path)))
    assert result["total"] == 0
    by_name = {m["name"]: m for m in result["measurements"]}
    assert by_name["T(in0->through)@1550.0nm"]["value"] == pytest.approx(0.0, abs=1e-9)


@needs_sax
def test_sax_broken_circuit_errors_with_location(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    adapter = SaxAdapter()
    result = adapter.parse(adapter.execute(_job(["broken.yml"], tmp_path)))
    assert result["total"] >= 1
    assert all(v["severity"] == "error" for v in result["violations"])
    first = result["violations"][0]
    assert first["file"].endswith("broken.yml")
    assert isinstance(first["line"], int)
    assert "ghost" in first["message"]


@needs_sax
def test_sax_mistuned_misses_target_with_margin(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    adapter = SaxAdapter()
    result = adapter.parse(adapter.execute(_job(["mistuned.yml"], tmp_path)))
    assert result["total"] == 1
    violation = result["violations"][0]
    assert violation["rule"] == "transmission"
    assert violation["severity"] == "error"
    assert violation["file"].endswith("mistuned.yml")
    assert result["measurements"][0]["margin"] == pytest.approx(-3.689, abs=0.1)


@needs_sax
def test_sax_proves_labels_against_real_sax():
    # Oracle check: fixture labels verified against sax directly,
    # not against the adapter under test.
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter  # noqa: F401

    import numpy as np
    import sax
    from ruamel.yaml import YAML

    def _simulate(name):
        doc = YAML(typ="safe").load((FIXTURES / name).read_text())
        netlist = {
            "instances": doc["instances"],
            "connections": doc.get("connections") or {},
            "ports": doc["ports"],
        }
        bound = {}
        for inst in doc["instances"].values():
            bound.setdefault(inst["component"], getattr(sax.models, inst["component"]))
        circuit, _ = sax.circuit(netlist, models=bound)
        out = circuit(wl=np.array([1.55]))
        return {
            pair: float(np.abs(np.asarray(values).ravel()[0]) ** 2)
            for pair, values in out.items()
        }

    mzi = _simulate("mzi.yml")
    assert mzi[("in0", "out1")] == pytest.approx(1.0, abs=1e-9)
    assert mzi[("in0", "out0")] == pytest.approx(0.0, abs=1e-12)
    ring = _simulate("ring.yml")
    assert ring[("in0", "through")] == pytest.approx(1.0, abs=1e-9)
    mistuned = _simulate("mistuned.yml")
    assert mistuned[("in0", "out1")] == pytest.approx(0.33972, abs=0.002)


@needs_sax
def test_sax_live_reports_proven_solver_version(tmp_path):
    # SAX-LIVE: the proven solver version is observable per run,
    # not prose — the live envelope must name sax 0.18.2 (uv.lock).
    import sax

    from rocket_engine.adapters.sax import SaxAdapter

    assert sax.__version__ == "0.18.2"
    adapter = SaxAdapter()
    result = adapter.parse(adapter.execute(_job(["mzi.yml"], tmp_path)))
    assert result["sax_version"] == "0.18.2"


def test_sax_parse_threads_solver_version_from_envelope():
    # SAX-LIVE: parse carries the driver's sax_version into the
    # result shape (canned envelope, no binary needed).
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    result = SaxAdapter().parse(_mzi_native())
    assert result["sax_version"] == "0.18.2-canned"


def test_sax_parse_evaluates_targets_from_canned_envelope():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    result = SaxAdapter().parse(_mzi_native())
    assert result["total"] == 0
    assert result["violations"] == []
    assert [m["status"] for m in result["measurements"]] == ["pass", "pass"]
    assert result["measurements"][0]["unit"] == "dB"
    assert result["measurements"][0]["margin"] == pytest.approx(0.5, abs=1e-9)


def test_sax_parse_flags_target_miss_with_margin():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    native = _mzi_native(
        stdout=_ok_envelope({"in0>out1": [0.5, 0.5, 0.5]}),
        targets=[{"from": "in0", "to": "out1", "at_nm": 1550.0, "min_db": -1.0}],
    )
    result = SaxAdapter().parse(native)
    assert result["total"] == 1
    violation = result["violations"][0]
    assert violation["rule"] == "transmission"
    assert violation["severity"] == "error"
    assert violation["file"].endswith("mzi.yml")
    assert result["measurements"][0]["status"] == "fail"
    assert result["measurements"][0]["margin"] == pytest.approx(-2.0103, abs=1e-3)


def test_sax_parse_synthesizes_violation_on_invalid_circuit():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    native = _mzi_native(
        exit_code=2,
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "invalid_circuit",
                    "message": "KeyError: 'ghost'",
                    "token": "ghost",
                    "line": 9,
                },
            }
        ),
        targets=[],
    )
    result = SaxAdapter().parse(native)
    assert result["total"] == 1
    violation = result["violations"][0]
    assert violation["severity"] == "error"
    assert violation["file"].endswith("mzi.yml")
    assert violation["line"] == 9
    assert "ghost" in violation["message"]


def test_sax_parse_raises_missing_dependency():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    native = _mzi_native(
        exit_code=3,
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "missing_dependency",
                    "message": "No module named 'sax'",
                    "token": None,
                    "line": None,
                },
            }
        ),
    )
    try:
        SaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for a sax-less env")


def test_sax_parse_rejects_garbage_stdout():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    native = _mzi_native(stdout="definitely not a driver envelope\n")
    try:
        SaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for garbage stdout")


def test_sax_parse_rejects_envelope_without_result():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    native = _mzi_native(stdout=json.dumps({"ok": True}))
    try:
        SaxAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for a resultless envelope")


def test_sax_uses_injected_runner(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    runner = FakeRunner(_ok_envelope({"in0>through": [1.0, 1.0, 1.0]}))
    adapter = SaxAdapter(runner=runner)
    job = _job(["ring.yml"], tmp_path)
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    assert runner.seen["command"][1:] == ["sax_driver.py", "sax_job.json"]
    assert runner.seen["workdir"] == job["workdir"]
    assert runner.seen["timeout_s"] == 120


def test_sax_execute_stages_driver_and_job(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter

    runner = FakeRunner(_ok_envelope({"in0>through": [1.0, 1.0, 1.0]}))
    job = _job(["ring.yml"], tmp_path)
    native = SaxAdapter(runner=runner).execute(job)
    workdir = Path(job["workdir"])
    assert (workdir / "sax_driver.py").is_file()
    staged = json.loads((workdir / "sax_job.json").read_text())
    assert set(staged["doc"]["instances"]) == {"c", "loop"}
    assert native["spec"].endswith("ring.yml")
    assert native["targets"][0]["to"] == "through"


def test_sax_converts_runner_errors(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter
    from rocket_engine.execution.errors import ExecutionError

    class PreflightBoom:
        def preflight(self):
            raise ExecutionError("runner_unavailable", "boom")

    class RunBoom:
        def preflight(self):
            return {"ready": True}

        def run(self, *args, **kwargs):
            raise ExecutionError("runner_unavailable", "boom")

    job = _job(["ring.yml"], tmp_path)
    cases = [
        (SaxAdapter(runner=PreflightBoom()), "preflight"),
        (SaxAdapter(runner=RunBoom()), "execute"),
    ]
    for adapter, method in cases:
        try:
            getattr(adapter, method)(job)
        except Exception as exc:
            assert type(exc).__name__ == "AdapterError", type(exc).__name__
            assert exc.code == "runner_unavailable"
        else:
            raise AssertionError(f"expected converted AdapterError from {method}")


def test_run_optical_registers_sax_by_default():
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter
    from rocket_engine.composition import Engine

    engine = Engine("photonic_demo", actor="tester")
    assert type(engine._solvers["run_optical"]["sax"]).__name__ == type(
        SaxAdapter()
    ).__name__


def test_run_optical_selects_solver_from_deck_tool(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter
    from rocket_engine.composition import Engine

    engine = Engine("photonic_demo", actor="tester")
    runner = FakeRunner(_ok_envelope({"in0>through": [1.0, 1.0, 1.0]}))
    engine.register_solver("run_optical", SaxAdapter(runner=runner), tool="sax")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    spec = workdir / "ring.yml"
    shutil.copy(FIXTURES / "ring.yml", spec)
    out = engine.run(
        {
            "project_id": "photonic_demo",
            "operation": "run_optical",
            "arguments": {
                "sources": [str(spec)],
                "workdir": str(workdir),
                "deck": {"tool": "sax"},
            },
        }
    )
    assert out["verdict"]["status"] == "PASS"
    assert engine.findings(out["run_id"])["findings"] == []


def test_run_optical_unknown_deck_tool_raises(tmp_path):
    from rocket_engine.adapters.sax import SaxAdapter  # RED: missing adapter  # noqa: F401
    from rocket_engine.composition import Engine

    engine = Engine("photonic_demo", actor="tester")
    command = {
        "project_id": "photonic_demo",
        "operation": "run_optical",
        "arguments": {"deck": {"tool": "no_such_tool"}},
    }
    try:
        engine.run(command)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for unknown deck tool")
