"""PHOTONIC-WIRE RED — MeowAdapter behind run_em (deck.tool meow).

Valid RED = `src/adapters/meow/adapter.py` does not exist yet, so the
loader below fails on FileNotFoundError. Project device YAML in, EME
S-parameters plus two-resolution convergence evidence out — never the
hardcoded smoke widths (`run_eme_smoke` stays the qualification
smoke; this op generalizes it to any widths/wl/cell/modes spec).
Fixtures replay the MEOW-LIVE proof numbers (matched guide T=1.0,
0.5->1.0um step T=0.877). Live tests skip (never fake-green) where
meow is uninstalled; unit tests use canned driver envelopes and
FakeRunners.
"""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "meow"

meow_present = importlib.util.find_spec("meow") is not None
needs_meow = pytest.mark.skipif(
    not meow_present,
    reason="meow not installed (uv sync)",
)


def _load_adapter():
    # RED: src/adapters/meow/adapter.py does not exist yet.
    path = ROOT / "src" / "adapters" / "meow" / "adapter.py"
    spec = importlib.util.spec_from_file_location(
        "meow_em_adapter", path
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
    job = {"operation": "run_em", "sources": staged,
           "workdir": str(workdir)}
    job.update(over)
    return job


def _basis(transmission=1.0, reflection=0.0, modes=2, neff0=2.3108):
    return {
        "num_modes": modes,
        "neff_re": [neff0] + [1.5] * (modes - 1),
        "neff_im": [0.0] * modes,
        "transmission": transmission,
        "reflection": reflection,
        "s21_phase_rad": 0.123,
    }


def _ok_envelope(base, refined):
    return json.dumps(
        {
            "ok": True,
            "meow_version": "0.15.0-canned",
            "tidy3d_version": "2.10.0-canned",
            "result": {
                "wl_um": 1.55,
                "widths_um": [0.5],
                "cell_length_um": 10.0,
                "base": base,
                "refined": refined,
                "convergence": {
                    "dT": abs(refined["transmission"]
                              - base["transmission"]),
                    "dR": abs(refined["reflection"]
                              - base["reflection"]),
                    "dneff": abs(refined["neff_re"][0]
                                 - base["neff_re"][0]),
                },
                "ports": {"left@0": 0, "right@0": 1},
            },
        }
    )


def _matched_native(**over):
    base = _basis(transmission=1.0, reflection=0.0, modes=2)
    refined = _basis(transmission=1.0, reflection=0.0, modes=4)
    native = {
        "exit_code": 0,
        "stdout": _ok_envelope(base, refined),
        "stderr": "",
        "spec": str(FIXTURES / "matched.yml"),
        "spec_text": (FIXTURES / "matched.yml").read_text(),
        "targets": [
            {"metric": "transmission", "min": 0.99},
            {"metric": "reflection", "max": 1.0e-6},
            {"metric": "convergence_dT", "max": 0.01},
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
        return subprocess.CompletedProcess(
            command, self._exit_code, self._stdout, ""
        )


def test_meow_em_adapter_exists():
    mod = _load_adapter()  # RED: missing module
    assert mod.OPERATION == "run_em"
    assert callable(mod.MeowAdapter)


def test_meow_em_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface

    mod = _load_adapter()  # RED: missing module
    assert issubclass(mod.MeowAdapter, ToolAdapter)


def test_meow_em_capabilities_advertise_tool():
    mod = _load_adapter()  # RED: missing module
    caps = mod.MeowAdapter().capabilities({"device": "strip"})
    assert caps["operations"] == ["run_em"]
    assert caps["tool"] == "meow"


def test_meow_em_preflight_refuses_bad_operation(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path, operation="run_optical")
    try:
        mod.MeowAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_optical")


def test_meow_em_preflight_refuses_missing_sources(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path)
    job["sources"] = [str(tmp_path / "work" / "ghost.yml")]
    try:
        mod.MeowAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for missing sources")


def test_meow_em_preflight_refuses_bad_timeout(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path, timeout_s=-1)
    try:
        mod.MeowAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for timeout -1")


def test_meow_em_preflight_refuses_bad_widths(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(bad.read_text().replace("[0.5]", "[0.5, -1.0]"))
    try:
        mod.MeowAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for negative width")


def test_meow_em_preflight_refuses_unrefined_modes(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path)
    bad = Path(job["sources"][0])
    bad.write_text(bad.read_text().replace(
        "{base: 2, refined: 4}", "{base: 4, refined: 4}"))
    try:
        mod.MeowAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for refined <= base")


def test_meow_em_preflight_accepts_op_fixture(tmp_path):
    mod = _load_adapter()  # RED: missing module
    checked = mod.MeowAdapter().preflight(_job(["matched.yml"], tmp_path))
    assert checked["spec"].endswith("matched.yml")
    assert checked["doc"]["device"] == "strip-matched"
    assert checked["timeout_s"] == 120


def test_meow_em_parse_passes_matched_guide():
    mod = _load_adapter()  # RED: missing module
    got = mod.MeowAdapter().parse(_matched_native())
    assert got["total"] == 0
    assert got["violations"] == []
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["value"] == pytest.approx(1.0)
    assert by_name["transmission"]["status"] == "pass"
    assert by_name["reflection"]["value"] == pytest.approx(0.0)
    assert by_name["convergence_dT"]["value"] == pytest.approx(0.0)
    assert by_name["convergence_dT"]["status"] == "pass"
    assert got["meow_version"] == "0.15.0-canned"
    assert got["tidy3d_version"] == "2.10.0-canned"
    assert got["modes"]["base"]["num_modes"] == 2
    assert got["modes"]["refined"]["num_modes"] == 4


def test_meow_em_parse_fails_step_transmission():
    mod = _load_adapter()  # RED: missing module
    base = _basis(transmission=0.877, reflection=0.0009, modes=2)
    refined = _basis(transmission=0.879, reflection=0.0008, modes=4,
                     neff0=2.3111)
    native = _matched_native(stdout=_ok_envelope(base, refined))
    got = mod.MeowAdapter().parse(native)
    # The step scatters: transmission misses min 0.99 AND reflection
    # misses max 1e-6, while the basis itself converges cleanly.
    assert got["total"] == 2
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["status"] == "fail"
    assert by_name["transmission"]["margin"] < 0
    assert by_name["reflection"]["status"] == "fail"
    assert by_name["convergence_dT"]["status"] == "pass"
    assert {v["rule"] for v in got["violations"]} == {"s_param"}
    assert got["violations"][0]["file"] == native["spec"]


def test_meow_em_parse_fails_unconverged_basis():
    mod = _load_adapter()  # RED: missing module
    base = _basis(transmission=0.995, reflection=0.0, modes=2)
    refined = _basis(transmission=0.90, reflection=0.01, modes=4,
                     neff0=2.35)
    native = _matched_native(stdout=_ok_envelope(base, refined))
    got = mod.MeowAdapter().parse(native)
    assert got["total"] >= 1
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["convergence_dT"]["status"] == "fail"
    assert any(v["rule"] == "convergence" for v in got["violations"])


def test_meow_em_parse_invalid_device_synthesizes_violation():
    mod = _load_adapter()  # RED: missing module
    native = _matched_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "invalid_device",
                    "message": "ValueError: mesh too coarse",
                    "token": "widths_um",
                    "line": 5,
                },
            }
        )
    )
    got = mod.MeowAdapter().parse(native)
    assert got["total"] == 1
    assert got["violations"][0]["rule"] == "device"
    assert got["violations"][0]["line"] == 5
    assert got["measurements"] == []


def test_meow_em_parse_missing_dependency_raises():
    mod = _load_adapter()  # RED: missing module
    native = _matched_native(
        stdout=json.dumps(
            {
                "ok": False,
                "error": {
                    "code": "missing_dependency",
                    "message": "meow is not importable",
                    "token": None,
                    "line": None,
                },
            }
        )
    )
    try:
        mod.MeowAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency")


def test_meow_em_parse_no_envelope_raises():
    mod = _load_adapter()  # RED: missing module
    native = _matched_native(stdout="Traceback (most recent call last): boom\n")
    try:
        mod.MeowAdapter().parse(native)
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")


def test_meow_em_execute_stages_driver_and_job(tmp_path):
    mod = _load_adapter()  # RED: missing module
    base = _basis()
    refined = _basis(modes=4)
    runner = FakeRunner(_ok_envelope(base, refined))
    job = _job(["matched.yml"], tmp_path)
    native = mod.MeowAdapter(runner=runner).execute(job)
    assert native["exit_code"] == 0
    assert len(native["targets"]) == 3
    assert (Path(job["workdir"]) / "meow_driver.py").is_file()
    assert (Path(job["workdir"]) / "meow_job.json").is_file()
    assert runner.seen["command"][1:] == ["meow_driver.py", "meow_job.json"]


def test_meow_em_driver_consumes_project_device():
    # Generalization law: the staged driver must build its
    # cross-sections from the project spec — hardcoded widths would
    # re-qualify the smoke instead of generalizing it.
    driver = ROOT / "src" / "adapters" / "meow" / "_driver.py"
    text = driver.read_text()
    assert 'doc["widths_um"]' in text
    assert "compute_s_matrix" in text
    # Locality: the repo's own no-cloud guard must pass on the
    # driver — the FDE backend is meow's local eigensolver, never
    # the tidy3d web client.
    spec = importlib.util.spec_from_file_location(
        "check_no_cloud", ROOT / "scripts" / "check_no_cloud.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard.scan_file(driver) == []


def test_meow_em_dispatches_as_engine_run(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    base = _basis()
    refined = _basis(modes=4)
    engine = Engine("photonic-wire-meow", actor="tester")
    engine.register_solver(
        "run_em", mod.MeowAdapter(runner=FakeRunner(
            _ok_envelope(base, refined))), tool="meow")
    job = _job(["matched.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "photonic-wire-meow",
            "operation": "run_em",
            "arguments": {
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "meow"},
            },
        }
    )
    assert out["operation"] == "run_em"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert len(out["verdict"]["measurements"]) == 3
    events = engine.events_since(0)
    assert any(
        e.get("event") == "run_completed" and e.get("data", {}).get(
            "run_id") == out["run_id"] for e in events
    ), events


def test_meow_em_dispatch_fail_carries_run_id(tmp_path):
    from rocket_engine.composition import Engine

    mod = _load_adapter()  # RED: missing module
    base = _basis(transmission=0.877, reflection=0.0009, modes=2)
    refined = _basis(transmission=0.879, reflection=0.0008, modes=4)
    engine = Engine("photonic-wire-meow", actor="tester")
    engine.register_solver(
        "run_em", mod.MeowAdapter(runner=FakeRunner(
            _ok_envelope(base, refined))), tool="meow")
    job = _job(["step.yml"], tmp_path)
    out = engine.run(
        {
            "project_id": "photonic-wire-meow",
            "operation": "run_em",
            "arguments": {
                "sources": job["sources"],
                "workdir": job["workdir"],
                "deck": {"tool": "meow"},
            },
        }
    )
    assert out["run_id"]
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["rule"] == "s_param" for f in found)


@needs_meow
def test_meow_em_live_matched_guide_passes(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["matched.yml"], tmp_path)
    adapter = mod.MeowAdapter()
    got = adapter.parse(adapter.execute(job))
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert by_name["convergence_dT"]["value"] == pytest.approx(0.0, abs=0.01)
    assert got["total"] == 0


@needs_meow
def test_meow_em_live_step_misses_matched_target(tmp_path):
    mod = _load_adapter()  # RED: missing module
    job = _job(["step.yml"], tmp_path)
    adapter = mod.MeowAdapter()
    got = adapter.parse(adapter.execute(job))
    by_name = {m["name"]: m for m in got["measurements"]}
    assert by_name["transmission"]["value"] == pytest.approx(0.877, abs=0.02)
    assert by_name["transmission"]["status"] == "fail"
    assert got["total"] >= 1
