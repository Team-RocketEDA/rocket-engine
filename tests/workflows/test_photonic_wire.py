"""PHOTONIC-WIRE RED — photonic lane dispatch through the wiring seam.

Valid RED = `rocket_engine.workflows.photonic_wire` does not exist
yet, so every test fails on ModuleNotFoundError. The seam wires the
proven photonic solvers into an Engine: circulax as the second
run_optical deck.tool (sax stays the default) and meow behind
run_em (the only tool). FDTD/FEM stay out — unknown deck tools
raise, never dispatch.

Project specs ride inline (never the hardcoded smokes): the RC
cases generalize the CIRCULAX-LIVE proof to new R/C values with an
analytic 1-e^-t/tau oracle, and the strip cases replay the
MEOW-LIVE proof numbers (T=1.0 matched, T=0.877 step) plus a
non-proof width carrying convergence evidence. Live tests skip
(never fake-green) where the solver is uninstalled; dispatch
tests use canned driver envelopes and FakeRunners.

The `stock_engine` tests prove the integrator patch, not the seam:
they skip on an unwired tree and run once composition.py wires
the solvers by default.
"""

import importlib.util
import json
import math
import subprocess
from pathlib import Path

import pytest

circulax_present = importlib.util.find_spec("circulax") is not None
needs_circulax = pytest.mark.skipif(
    not circulax_present,
    reason="circulax not installed (uv sync --group photonic)",
)
meow_present = importlib.util.find_spec("meow") is not None
needs_meow = pytest.mark.skipif(
    not meow_present,
    reason="meow not installed (uv sync --group photonic)",
)


def _wire():
    from rocket_engine.workflows.photonic_wire import (  # RED: missing module
        wire_photonics,
    )

    return wire_photonics


def _engine(name="photonic-wire"):
    from rocket_engine.composition import Engine

    return Engine(name, actor="tester")


def _rc_spec(path, R, C, target_min=0.9):
    path.write_text(
        "circuit: rc-inline\n"
        "instances:\n"
        "  V1: {component: vsource, settings: {V: 1.0}}\n"
        f"  R1: {{component: resistor, settings: {{R: {R}}}}}\n"
        f"  C1: {{component: capacitor, settings: {{C: {C}}}}}\n"
        "  GND: {component: ground}\n"
        "connections:\n"
        "  V1,p1: R1,p1\n"
        "  V1,p2: GND,p1\n"
        "  R1,p2: C1,p1\n"
        "  C1,p2: GND,p1\n"
        'transient: {t1_s: 5.0e-6, points: 11, observe: "C1,p1"}\n'
        "targets:\n"
        f"  - {{at_s: 5.0e-6, min_V: {target_min}}}\n"
    )
    return str(path)


def _strip_spec(path, widths, targets=None):
    if targets is None:
        targets = [
            "{metric: transmission, min: 0.99}",
            "{metric: reflection, max: 1.0e-6}",
            "{metric: convergence_dT, max: 0.01}",
        ]
    path.write_text(
        "device: strip-inline\n"
        "wl_um: 1.55\n"
        "cell_length_um: 10.0\n"
        f"widths_um: {widths}\n"
        "modes: {base: 2, refined: 4}\n"
        "targets:\n" + "".join(f"  - {item}\n" for item in targets)
    )
    return str(path)


def _circ_envelope(final=0.9933, version="0.2.5-canned"):
    grid = [i * 5e-6 / 10 for i in range(11)]
    curve = [final * (1 - 0.5 ** (i + 1)) / (1 - 0.5**11) for i in range(11)]
    curve[-1] = final
    return json.dumps(
        {
            "ok": True,
            "circulax_version": version,
            "result": {
                "t_s": grid,
                "v_V": curve,
                "final_V": final,
                "observe": "C1,p1",
                "t1_s": 5e-6,
                "points": 11,
            },
        }
    )


def _basis(transmission=1.0, reflection=0.0, modes=2, neff0=2.3108):
    return {
        "num_modes": modes,
        "neff_re": [neff0] + [1.5] * (modes - 1),
        "neff_im": [0.0] * modes,
        "transmission": transmission,
        "reflection": reflection,
        "s21_phase_rad": 0.123,
    }


def _meow_envelope(base, refined):
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
                    "dT": abs(
                        refined["transmission"] - base["transmission"]
                    ),
                    "dR": abs(refined["reflection"] - base["reflection"]),
                    "dneff": abs(
                        refined["neff_re"][0] - base["neff_re"][0]
                    ),
                },
                "ports": {"left@0": 0, "right@0": 1},
            },
        }
    )


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


@pytest.fixture(autouse=True)
def _restore_solver_deps():
    from rocket_engine.interfaces.setup import SOLVER_DEPS

    before = dict(SOLVER_DEPS)
    yield
    SOLVER_DEPS.clear()
    SOLVER_DEPS.update(before)


def _run(engine, operation, spec, workdir, tool):
    return engine.run(
        {
            "project_id": engine.snapshot()["project_id"],
            "operation": operation,
            "arguments": {
                "sources": [spec],
                "workdir": workdir,
                "deck": {"tool": tool},
            },
        }
    )


def test_photonic_wire_helper_exists():
    wire_photonics = _wire()  # RED: missing module
    assert callable(wire_photonics)


def test_photonic_tools_map_names_both_lanes():
    from rocket_engine.workflows.photonic_wire import (  # RED: missing module
        PHOTONIC_TOOLS,
    )

    assert PHOTONIC_TOOLS == {"run_optical": "circulax", "run_em": "meow"}


def test_wire_photonics_registers_both_lanes():
    engine = _engine()
    records = _wire()(engine)  # RED: missing module
    assert records == {"run_optical": "circulax", "run_em": "meow"}
    optical = engine.solvers_for("run_optical")
    assert list(optical) == ["sax", "circulax"]
    assert type(optical["circulax"]).__name__ == "CirculaxAdapter"
    em_solvers = engine.solvers_for("run_em")
    assert list(em_solvers) == ["meow"]
    assert type(em_solvers["meow"]).__name__ == "MeowAdapter"


def test_wire_photonics_keeps_sax_default_and_job_kinds():
    engine = _engine()
    _wire()(engine)  # RED: missing module
    kinds = {
        row["operation"]: row["tools"] for row in engine.job_kinds()["job_kinds"]
    }
    assert kinds["run_optical"] == ["sax", "circulax"]
    assert kinds["run_em"] == ["meow"]


def test_wire_photonics_is_idempotent():
    engine = _engine()
    wire_photonics = _wire()  # RED: missing module
    wire_photonics(engine)
    wire_photonics(engine)
    assert list(engine.solvers_for("run_optical")) == ["sax", "circulax"]
    assert list(engine.solvers_for("run_em")) == ["meow"]


def test_wire_photonics_reports_capabilities_without_unknown_solver():
    engine = _engine()
    _wire()(engine)  # RED: missing module
    report = engine.capabilities()
    optical = report["operations"]["run_optical"]
    assert set(optical["tools"]) == {"sax", "circulax"}
    assert optical["tools"]["circulax"]["available"] is circulax_present
    em_report = report["operations"]["run_em"]
    assert set(em_report["tools"]) == {"meow"}
    assert em_report["tools"]["meow"]["available"] is meow_present
    if circulax_present or meow_present:
        assert report["operations"]["run_em"]["readiness"] in (
            "ready",
            "blocked",
        )


def test_circulax_dispatch_pass_carries_run_id(tmp_path):
    engine = _engine()
    _wire()(engine, runner=FakeRunner(_circ_envelope(0.9933)))  # RED
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "good.yml", 1000.0, 1.0e-9)
    out = _run(engine, "run_optical", spec, str(workdir), "circulax")
    assert out["operation"] == "run_optical"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert out["verdict"]["measurements"][0]["status"] == "pass"
    events = engine.events_since(0)
    assert any(
        e.get("event") == "run_completed"
        and e.get("data", {}).get("run_id") == out["run_id"]
        for e in events
    ), events


def test_circulax_dispatch_fail_carries_run_id(tmp_path):
    engine = _engine()
    _wire()(engine, runner=FakeRunner(_circ_envelope(0.0488)))  # RED
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "slow.yml", 100000.0, 1.0e-9)
    out = _run(engine, "run_optical", spec, str(workdir), "circulax")
    assert out["run_id"]
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["rule"] == "transient" for f in found)


def test_meow_dispatch_pass_carries_run_id(tmp_path):
    engine = _engine()
    envelope = _meow_envelope(_basis(), _basis(modes=4))
    _wire()(engine, runner=FakeRunner(envelope))  # RED
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _strip_spec(workdir / "matched.yml", [0.5])
    out = _run(engine, "run_em", spec, str(workdir), "meow")
    assert out["operation"] == "run_em"
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    assert len(out["verdict"]["measurements"]) == 3
    events = engine.events_since(0)
    assert any(
        e.get("event") == "run_completed"
        and e.get("data", {}).get("run_id") == out["run_id"]
        for e in events
    ), events


def test_meow_dispatch_step_fails_matched_target(tmp_path):
    engine = _engine()
    base = _basis(transmission=0.877, reflection=0.0009, modes=2)
    refined = _basis(
        transmission=0.879, reflection=0.0008, modes=4, neff0=2.3111
    )
    _wire()(engine, runner=FakeRunner(_meow_envelope(base, refined)))  # RED
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _strip_spec(workdir / "step.yml", [0.5])
    out = _run(engine, "run_em", spec, str(workdir), "meow")
    assert out["run_id"]
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["rule"] == "s_param" for f in found)


def test_unknown_deck_tool_still_raises(tmp_path):
    # FDTD/FEM stay proposed, not proven: meep/palace dispatch
    # nothing, on either photonic operation.
    from rocket_engine.project.errors import ProjectError

    engine = _engine()
    _wire()(engine, runner=FakeRunner(_circ_envelope()))  # RED
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "good.yml", 1000.0, 1.0e-9)
    with pytest.raises(ProjectError) as refused:
        _run(engine, "run_optical", spec, str(workdir), "meep")
    assert refused.value.code == "unsupported_operation"
    strip = _strip_spec(workdir / "matched.yml", [0.5])
    with pytest.raises(ProjectError) as refused_em:
        _run(engine, "run_em", strip, str(workdir), "palace")
    assert refused_em.value.code == "unsupported_operation"


def test_stock_engine_serves_circulax_after_patch(tmp_path):
    # Integrator-patch proof: a stock Engine dispatches circulax
    # with no manual wiring. Skips on an unwired tree.
    from rocket_engine.project.errors import ProjectError

    engine = _engine("photonic-wire-stock")
    if "circulax" not in engine.solvers_for("run_optical"):
        pytest.skip("unwired tree: integrator patch not applied")
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "good.yml", 1000.0, 1.0e-9)
    try:
        out = _run(engine, "run_optical", spec, str(workdir), "circulax")
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip("unwired tree: integrator patch not applied")
        raise
    assert out["run_id"]
    assert out["verdict"]["status"] in ("PASS", "FAIL", "NOT_RUN")


def test_stock_engine_serves_meow_after_patch(tmp_path):
    # Integrator-patch proof: a stock Engine dispatches meow with
    # no manual wiring. Skips on an unwired tree.
    from rocket_engine.project.errors import ProjectError

    engine = _engine("photonic-wire-stock")
    if "meow" not in engine.solvers_for("run_em"):
        pytest.skip("unwired tree: integrator patch not applied")
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _strip_spec(workdir / "matched.yml", [0.5])
    try:
        out = _run(engine, "run_em", spec, str(workdir), "meow")
    except ProjectError as exc:
        if exc.code == "unsupported_operation":
            pytest.skip("unwired tree: integrator patch not applied")
        raise
    assert out["run_id"]
    assert out["verdict"]["status"] in ("PASS", "FAIL", "NOT_RUN")


def test_stock_engine_capabilities_cover_photonic_tools():
    # Integrator-patch proof: the static SOLVER_DEPS rows exist,
    # so capabilities never raise unknown_solver post-patch.
    from rocket_engine.interfaces.setup import SOLVER_DEPS

    if ("run_optical", "circulax") not in SOLVER_DEPS or (
        "run_em",
        "meow",
    ) not in SOLVER_DEPS:
        pytest.skip("unwired tree: integrator patch not applied")
    report = _engine().capabilities()
    assert set(report["operations"]["run_optical"]["tools"]) >= {
        "sax",
        "circulax",
    }
    assert set(report["operations"]["run_em"]["tools"]) == {"meow"}


@needs_circulax
def test_live_circulax_generalizes_beyond_proof_values(tmp_path):
    # Generalization law: a project RC the proof never ran (2k/1nF,
    # tau=2us) must hit the analytic 1-e^-t/tau value — the op
    # consumes the spec, not the smoke constants.
    engine = _engine()
    _wire()(engine)  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "project.yml", 2000.0, 1.0e-9)
    out = _run(engine, "run_optical", spec, str(workdir), "circulax")
    expected = 1.0 - math.exp(-5e-6 / (2000.0 * 1.0e-9))
    assert out["verdict"]["status"] == "PASS"
    value = out["verdict"]["measurements"][0]["value"]
    assert value == pytest.approx(expected, abs=1e-3)
    assert expected == pytest.approx(0.9179, abs=1e-3)


@needs_circulax
def test_live_circulax_slow_project_rc_fails(tmp_path):
    engine = _engine()
    _wire()(engine)  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _rc_spec(workdir / "slow.yml", 47000.0, 1.0e-9)
    out = _run(engine, "run_optical", spec, str(workdir), "circulax")
    expected = 1.0 - math.exp(-5e-6 / (47000.0 * 1.0e-9))
    assert out["verdict"]["status"] == "FAIL"
    value = out["verdict"]["measurements"][0]["value"]
    assert value == pytest.approx(expected, abs=1e-3)
    assert expected < 0.9


@needs_meow
def test_live_meow_proof_replay_passes_with_run_id(tmp_path):
    # The MEOW-LIVE proof as an op run: matched 500nm strip,
    # T=1.0 plus convergence evidence, all under one run_id.
    engine = _engine()
    _wire()(engine)  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _strip_spec(workdir / "matched.yml", [0.5])
    out = _run(engine, "run_em", spec, str(workdir), "meow")
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    by_name = {m["name"]: m for m in out["verdict"]["measurements"]}
    assert by_name["transmission"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert by_name["convergence_dT"]["value"] == pytest.approx(0.0, abs=0.01)
    assert by_name["convergence_dT"]["status"] == "pass"


@needs_meow
def test_live_meow_project_width_carries_convergence(tmp_path):
    # Generalization law: a non-proof width (600nm) still ships
    # two-resolution convergence evidence with the verdict.
    engine = _engine()
    _wire()(engine)  # RED: missing module
    workdir = tmp_path / "work"
    workdir.mkdir()
    spec = _strip_spec(
        workdir / "project.yml",
        [0.6],
        targets=[
            "{metric: transmission, min: 0.99}",
            "{metric: convergence_dT, max: 0.05}",
            "{metric: convergence_dneff, max: 0.05}",
        ],
    )
    out = _run(engine, "run_em", spec, str(workdir), "meow")
    assert out["run_id"]
    assert out["verdict"]["status"] == "PASS"
    by_name = {m["name"]: m for m in out["verdict"]["measurements"]}
    assert by_name["convergence_dT"]["status"] == "pass"
    assert by_name["convergence_dneff"]["status"] == "pass"
