"""SOLVER-TIMEOUT RED — engine-owned run budget, end to end.

The solver lane has no budget of its own: adapters that honor
`timeout_s` only see it when the caller smuggles it at the job
root (unfrozen, unrecorded), `run.request` has no timeout knob,
and drc/extract/lvs adapters ignore the job timeout entirely.

Valid RED = `validate_run_request` rejects timeout_s as unknown,
`_run_operation` never stamps it, and the four constant-timeout
adapters take no budget argument.
"""
import pytest

PROJECT = "timeout_demo"


class FakeSolver:
    """Hermetic solver: records the job, verdict on demand."""

    def __init__(self, violations=()):
        self.violations = list(violations)
        self.calls = []

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "fake"}

    def preflight(self, job):
        return dict(job, tool="fake")

    def execute(self, job):
        self.calls.append(dict(job))
        return {
            "exit_code": 0, "stdout": "", "stderr": "", "log": "fake",
        }

    def parse(self, native):
        return {"violations": list(self.violations)}


def _engine(solver, project=PROJECT):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="tester")
    engine.register_solver("run_syntax", solver, tool="fake")
    return engine


def _direct(tag, solver, request=None, root_timeout=None):
    arguments = {
        "cell": tag, "deck": {"tool": "fake"},
    }
    if request is not None:
        arguments["request"] = request
    if root_timeout is not None:
        arguments["timeout_s"] = root_timeout
    return solver, {
        "project_id": PROJECT,
        "operation": "run_syntax",
        "arguments": arguments,
        "request_id": f"req-{tag}",
    }


# knob validation -------------------------------------------------------


def test_timeout_knob_defaults_to_adapter_default():
    from rocket_engine.interfaces.runparams import validate_run_request

    assert validate_run_request({})["timeout_s"] is None
    assert validate_run_request(None)["timeout_s"] is None


def test_timeout_knob_explicit_value_kept():
    from rocket_engine.interfaces.runparams import validate_run_request

    out = validate_run_request({"timeout_s": 30})
    assert out["timeout_s"] == 30
    assert validate_run_request({"timeout_s": None})["timeout_s"] is None


@pytest.mark.parametrize("bad", [0, -1, True, False, "60", 1801, [30]])
def test_timeout_knob_refuses_bad_values(bad):
    from rocket_engine.interfaces.runparams import RunParamsError
    from rocket_engine.interfaces.runparams import validate_run_request

    with pytest.raises(RunParamsError) as exc:
        validate_run_request({"timeout_s": bad})
    assert exc.value.code == "invalid_run_param"


def test_timeout_knob_freeze_round_trip():
    from rocket_engine.interfaces.runparams import (
        freeze_run_request,
        parse_run_request,
        validate_run_request,
    )

    text = freeze_run_request(validate_run_request({"timeout_s": 30}))
    assert "timeout_s: 30" in text
    assert parse_run_request(text)["timeout_s"] == 30


# engine stamping -------------------------------------------------------


def test_frozen_budget_reaches_solver_job():
    solver = FakeSolver()
    engine = _engine(solver)
    _, command = _direct("stamped", solver, request={"timeout_s": 7})
    out = engine.run(command)
    assert out["state"] == "completed"
    assert solver.calls[0]["timeout_s"] == 7


def test_no_budget_stamped_when_request_omitted():
    solver = FakeSolver()
    engine = _engine(solver)
    _, command = _direct("defaulted", solver)
    out = engine.run(command)
    assert out["state"] == "completed"
    # None means "adapter default": the engine stamps nothing, so a
    # LibreLane flow keeps its hour while a spice sim keeps 120.
    assert "timeout_s" not in solver.calls[0]


def test_root_timeout_smuggled_is_refused():
    from rocket_engine.project.errors import ProjectError

    solver = FakeSolver()
    engine = _engine(solver)
    _, command = _direct("smuggled", solver, root_timeout=5)
    with pytest.raises(ProjectError) as exc:
        engine.run(command)
    assert exc.value.code == "invalid_command"


# adapter honor ----------------------------------------------------------
#
# Four solver adapters still run on a module-constant budget and
# ignore the job timeout: drc.magic, drc.klayout, extract_magic,
# lvs_netgen. Each case pins one seam: preflight validates the
# job timeout into the checked mapping, _run honors its budget
# argument on both the runner and the direct-subprocess paths,
# and execute threads the checked budget into every _run call.


def _preflight_rejects_bad_timeout(adapter, job):
    from rocket_engine.adapters.errors import AdapterError

    bad = dict(job, timeout_s=0)
    with pytest.raises(AdapterError) as exc:
        adapter.preflight(bad)
    assert exc.value.code == "invalid_command"
    assert "timeout_s" in str(exc.value)


def test_magic_drc_preflight_validates_job_timeout(tmp_path):
    from rocket_engine.adapters.drc.magic import OPERATION, MagicDrcAdapter

    cell = tmp_path / "cell.mag"
    cell.write_text("rect 0 0 4 4\n")
    adapter = MagicDrcAdapter(runner=None)
    _preflight_rejects_bad_timeout(
        adapter,
        {
            "operation": OPERATION,
            "tech": "scmos",
            "cell": "cell",
            "cell_file": str(cell),
            "workdir": str(tmp_path),
        },
    )


def test_klayout_drc_preflight_validates_job_timeout(tmp_path):
    from rocket_engine.adapters.drc.klayout import OPERATION, KlayoutDrcAdapter

    gds = tmp_path / "a.gds"
    gds.write_bytes(b"GDS")
    adapter = KlayoutDrcAdapter(runner=None)
    _preflight_rejects_bad_timeout(
        adapter,
        {
            "operation": OPERATION,
            "gds_file": str(gds),
            "rules": {"layer": [1, 0], "width_um": 0.15},
            "workdir": str(tmp_path),
        },
    )


def test_magic_extract_preflight_validates_job_timeout(tmp_path):
    from rocket_engine.adapters.extract_magic import (
        OPERATION,
        MagicExtractAdapter,
    )

    cell = tmp_path / "cell.mag"
    cell.write_text("rect 0 0 4 4\n")
    adapter = MagicExtractAdapter(runner=None)
    _preflight_rejects_bad_timeout(
        adapter,
        {
            "operation": OPERATION,
            "tech": "scmos",
            "cell": "cell",
            "cell_file": str(cell),
            "workdir": str(tmp_path),
        },
    )


def test_netgen_lvs_preflight_validates_job_timeout(tmp_path):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter, OPERATION

    layout = tmp_path / "layout.spice"
    schematic = tmp_path / "schematic.spice"
    layout.write_text("R1 a b 1k\n")
    schematic.write_text("R1 a b 1k\n")
    setup = tmp_path / "setup.tcl"
    setup.write_text("# setup\n")
    adapter = NetgenLvsAdapter(runner=None)
    _preflight_rejects_bad_timeout(
        adapter,
        {
            "operation": OPERATION,
            "layout_spice": str(layout),
            "schematic_spice": str(schematic),
            "setup_file": str(setup),
            "workdir": str(tmp_path),
        },
    )


class _Recorder:
    """Fake isolated runner: records the budget it is given."""

    def __init__(self):
        self.seen = {}

    def run(self, *args, **kwargs):
        import subprocess

        self.seen["args"] = args
        self.seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args[0], 0, "out", "")


def _run_honors_budget(adapter, run_args, timeout=9):
    recorder = _Recorder()
    adapter._runner = recorder
    adapter._run(*run_args, timeout=timeout)
    sent = recorder.seen["kwargs"].get("timeout_s")
    if sent is None:
        sent = recorder.seen["args"][2]
    assert sent == timeout


def _run_direct_names_budget(adapter, run_args, monkeypatch, timeout=9):
    import subprocess

    captured = {}

    def boom(*args, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(args[0], timeout)

    import importlib

    mod = importlib.import_module(adapter.__module__)
    monkeypatch.setattr(mod.subprocess, "run", boom)
    adapter._runner = None
    with pytest.raises(Exception) as exc:
        adapter._run(*run_args, timeout=timeout)
    assert getattr(exc.value, "code", "") == "runner_unavailable"
    assert captured.get("timeout") == timeout
    assert str(timeout) in str(exc.value)


def test_magic_drc_run_honors_budget(tmp_path, monkeypatch):
    from rocket_engine.adapters.drc.magic import MagicDrcAdapter

    _run_honors_budget(
        MagicDrcAdapter(runner=_Recorder()),
        ("scmos", "quit\n", str(tmp_path)),
    )
    _run_direct_names_budget(
        MagicDrcAdapter(runner=None),
        ("scmos", "quit\n", str(tmp_path)),
        monkeypatch,
    )


def test_klayout_drc_run_honors_budget(tmp_path, monkeypatch):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    _run_honors_budget(
        KlayoutDrcAdapter(runner=_Recorder()),
        (["klayout", "-b"], str(tmp_path)),
    )
    _run_direct_names_budget(
        KlayoutDrcAdapter(runner=None),
        (["klayout", "-b"], str(tmp_path)),
        monkeypatch,
    )


def test_magic_extract_run_honors_budget(tmp_path, monkeypatch):
    from rocket_engine.adapters.extract_magic import MagicExtractAdapter

    _run_honors_budget(
        MagicExtractAdapter(runner=_Recorder()),
        ("scmos", "quit\n", str(tmp_path)),
    )
    _run_direct_names_budget(
        MagicExtractAdapter(runner=None),
        ("scmos", "quit\n", str(tmp_path)),
        monkeypatch,
    )


def test_netgen_lvs_run_honors_budget(tmp_path, monkeypatch):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    _run_honors_budget(
        NetgenLvsAdapter(runner=_Recorder()),
        (["netgen"], str(tmp_path)),
    )
    _run_direct_names_budget(
        NetgenLvsAdapter(runner=None),
        (["netgen"], str(tmp_path)),
        monkeypatch,
    )


def _execute_threads_checked_timeout(adapter, job, checked, timeout=9):
    from rocket_engine.adapters.errors import AdapterError

    adapter.preflight = lambda _job: checked
    seen = {}

    def stop(*args, **kwargs):
        seen["kwargs"] = kwargs
        raise AdapterError("stop", "stop here")

    adapter._run = stop
    with pytest.raises(AdapterError, match="stop here"):
        adapter.execute(job)
    assert seen["kwargs"].get("timeout") == timeout


def test_magic_drc_execute_threads_checked_timeout(tmp_path):
    from rocket_engine.adapters.drc.magic import OPERATION, MagicDrcAdapter

    cell = tmp_path / "cell.mag"
    cell.write_text("rect 0 0 4 4\n")
    _execute_threads_checked_timeout(
        MagicDrcAdapter(runner=None),
        {
            "operation": OPERATION,
            "workdir": str(tmp_path),
            "timeout_s": 9,
        },
        {
            "tech": "scmos",
            "cell": "cell",
            "cell_file": str(cell),
            "timeout_s": 9,
        },
    )


def test_klayout_drc_execute_threads_checked_timeout(tmp_path):
    from rocket_engine.adapters.drc.klayout import OPERATION, KlayoutDrcAdapter

    _execute_threads_checked_timeout(
        KlayoutDrcAdapter(runner=None),
        {
            "operation": OPERATION,
            "workdir": str(tmp_path),
            "timeout_s": 9,
        },
        {"gds_file": "a.gds", "deck_file": "d.lydrc", "timeout_s": 9},
    )


def test_magic_extract_execute_threads_checked_timeout(tmp_path):
    from rocket_engine.adapters.extract_magic import (
        OPERATION,
        MagicExtractAdapter,
    )

    cell = tmp_path / "cell.mag"
    cell.write_text("rect 0 0 4 4\n")
    _execute_threads_checked_timeout(
        MagicExtractAdapter(runner=None),
        {
            "operation": OPERATION,
            "workdir": str(tmp_path),
            "timeout_s": 9,
        },
        {
            "tech_arg": "scmos",
            "cell": "cell",
            "cell_file": str(cell),
            "timeout_s": 9,
        },
    )


def test_netgen_lvs_execute_threads_checked_timeout(tmp_path):
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter, OPERATION

    layout = tmp_path / "layout.spice"
    schematic = tmp_path / "schematic.spice"
    layout.write_text("R1 a b 1k\n")
    schematic.write_text("R1 a b 1k\n")
    _execute_threads_checked_timeout(
        NetgenLvsAdapter(runner=None),
        {
            "operation": OPERATION,
            "workdir": str(tmp_path),
            "timeout_s": 9,
        },
        {
            "layout_spice": str(layout),
            "schematic_spice": str(schematic),
            "setup_file": "setup.tcl",
            "cell": None,
            "timeout_s": 9,
        },
    )
