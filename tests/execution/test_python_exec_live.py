"""PYTHON-EXEC RED — live worker runs: cell-build, curve fit, effects.

Tests assume `rocket_engine.execution.python_exec` (see
test_python_exec_modes.py). Live tests use the `live_service`
fixture, which skips loudly unless a provable bwrap worker with
the prepared interpreter admits runs — a shadowed bwrap skips,
never fake-greens (I16 rule).
"""

import sys

import pytest


def _mod():
    from rocket_engine.execution import python_exec  # RED: missing module

    return python_exec


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


@pytest.fixture
def live_service(tmp_path):
    mod = _mod()
    from rocket_engine.execution.service import ExecutionService

    runner = mod.PythonExecRunner(
        artifacts_root=str(tmp_path / "harvest"),
    )
    if not runner.admission["admitted"]:
        pytest.skip(
            "no provable worker isolation: %s" % runner.admission.get("reason")
        )
    proj = tmp_path / "proj"
    proj.mkdir()
    service = mod.PythonExecService(
        "pyexec-live", actor="probe-agent",
        root=str(tmp_path / "pyexec"),
        execution=ExecutionService("pyexec-live"),
        project_root=str(proj),
        runner=runner,
    )
    service.project_dir = proj
    return service


def _approved_run(service, **kwargs):
    handle = service.request_execution(request_id=None, **kwargs)
    admitted = service.resolve_approval(
        handle["approval_id"], "approved", via="ui",
    )
    return admitted["run_id"], service.run_job(admitted["run_id"])


def test_live_lines_gdsfactory_cell_build(live_service):
    pytest.importorskip("gdsfactory")
    _run_id, record = _approved_run(
        live_service, mode="lines",
        lines=(
            "import gdsfactory as gf\n"
            "from gdsfactory.generic_tech import get_generic_pdk\n"
            "get_generic_pdk().activate()\n"
            "cell = gf.Component('pyexec_demo')\n"
            "cell.add_polygon([(0, 0), (10, 0), (10, 5)], layer=(1, 0))\n"
            "cell.write_gds('cell.gds')\n"
            "print('polygons=%d' % len(cell.get_polygons()))\n"
            "box = cell.bbox()\n"
            "print('bbox=%.1f,%.1f' % (box.width(), box.height()))\n"
        ),
        artifacts=("cell.gds",),
        timeout_s=300,
    )
    assert record["state"] == "completed", record
    assert record["ok"] is True
    assert "polygons=1" in record["stdout"]
    assert "bbox=10.0,5.0" in record["stdout"]
    assert record["exception"] is None
    names = [entry["name"] for entry in record["artifacts"]]
    assert "cell.gds" in names
    gds = next(e for e in record["artifacts"] if e["name"] == "cell.gds")
    assert gds["bytes"] > 0 and len(gds["sha256"]) == 64


def test_live_path_curve_fit(live_service):
    pytest.importorskip("numpy")
    script = live_service.project_dir / "fit.py"
    script.write_text(
        "import numpy as np\n"
        "x = np.array([0.0, 1.0, 2.0, 3.0])\n"
        "y = 2.0 * x + 1.0\n"
        "slope, offset = np.polyfit(x, y, 1)\n"
        "print('slope=%.6f offset=%.6f' % (slope, offset))\n",
        encoding="utf-8",
    )
    _run_id, record = _approved_run(
        live_service, mode="path", path="fit.py",
    )
    assert record["state"] == "completed", record
    assert record["ok"] is True
    assert "slope=2.000000 offset=1.000000" in record["stdout"]


def test_live_effects_land_in_ledger_with_actor_and_revision(tmp_path):
    mod = _mod()
    from rocket_engine.composition import Engine
    from rocket_engine.execution.dispatch import OpDispatcher
    from rocket_engine.execution.service import ExecutionService

    runner = mod.PythonExecRunner(artifacts_root=str(tmp_path / "harvest"))
    if not runner.admission["admitted"]:
        pytest.skip(
            "no provable worker isolation: %s" % runner.admission.get("reason")
        )
    proj = tmp_path / "proj"
    proj.mkdir()
    engine = Engine("ledger-probe", actor="probe-agent")
    dispatcher = OpDispatcher(engine, project_id="ledger-probe",
                              actor="probe-agent")
    service = mod.PythonExecService(
        "ledger-probe", actor="probe-agent",
        root=str(tmp_path / "pyexec"),
        execution=ExecutionService("ledger-probe"),
        project_root=str(proj), runner=runner, dispatcher=dispatcher,
    )
    rev = engine.snapshot()["current_revision"]
    _run_id, record = _approved_run(
        service, mode="lines",
        lines=(
            "tools.write_doc(path='notes/fit.md', content='# fit\\n', "
            "expected_revision=%r)\n" % rev
        ),
    )
    assert record["state"] == "completed", record
    assert record["effects"]["ops_ok"] is True
    assert record["effects"]["replayed"] is True
    events = engine.events_since(0)
    writes = [e for e in events if e.get("data", {}).get("path") == "notes/fit.md"]
    assert writes, [e.get("event") for e in events]
    assert writes[0]["actor"] == "probe-agent"
    assert engine.snapshot()["current_revision"] != "p12"
    doc = dispatcher.execute("read_doc", {"path": "notes/fit.md"})
    assert doc["content"] == "# fit\n"


def test_live_runs_triggered_carry_run_ids(tmp_path):
    mod = _mod()
    from rocket_engine.composition import Engine
    from rocket_engine.execution.dispatch import OpDispatcher
    from rocket_engine.execution.service import ExecutionService

    runner = mod.PythonExecRunner(artifacts_root=str(tmp_path / "harvest"))
    if not runner.admission["admitted"]:
        pytest.skip(
            "no provable worker isolation: %s" % runner.admission.get("reason")
        )

    class _PassAdapter:
        def preflight(self, job):
            return {"ready": True}

        def execute(self, job):
            return {"exit_code": 0, "stdout": "probe", "stderr": ""}

        def parse(self, native_output):
            return {"total": 0, "violations": []}

    proj = tmp_path / "proj"
    proj.mkdir()
    engine = Engine("runs-probe", actor="probe-agent")
    engine.register_solver("run_em", _PassAdapter(), tool="meow")
    dispatcher = OpDispatcher(engine, project_id="runs-probe",
                              actor="probe-agent")
    service = mod.PythonExecService(
        "runs-probe", actor="probe-agent",
        root=str(tmp_path / "pyexec"),
        execution=ExecutionService("runs-probe"),
        project_root=str(proj), runner=runner, dispatcher=dispatcher,
    )
    _run_id, record = _approved_run(
        service, mode="lines",
        lines="tools.run_em(cell='amp')\n",
    )
    assert record["state"] == "completed", record
    assert record["effects"]["ops_ok"] is True
    assert len(record["effects"]["run_ids"]) == 1
    child = engine.job_status(record["effects"]["run_ids"][0])
    assert child["state"] == "completed"


def test_live_failure_reports_exception_location(live_service):
    _run_id, record = _approved_run(
        live_service, mode="lines",
        lines="def fit(data):\n    raise ValueError('bad curve')\nfit([1])\n",
    )
    assert record["state"] == "failed"
    assert record["ok"] is False
    assert record["exit_code"] == 1
    assert record["exception"]["type"] == "ValueError"
    assert record["exception"]["location"] == "cell.py:2 in fit"
    assert record["verdict"]["status"] == "NOT_RUN"


def test_live_timeout_keeps_partials(live_service):
    _run_id, record = _approved_run(
        live_service, mode="lines", timeout_s=3,
        lines="import time\nprint('before-sleep', flush=True)\ntime.sleep(60)\n",
    )
    assert record["state"] == "timeout", record
    assert record["ok"] is False
    assert "before-sleep" in record["stdout"]
    assert record["tree_killed"] is True
    assert record["credential_revoked"] is True


def test_live_cancel_kills_tree_and_reports_cancelled(live_service):
    handle = live_service.request_execution(
        mode="lines", lines="import time\ntime.sleep(60)\n",
    )
    admitted = live_service.resolve_approval(
        handle["approval_id"], "approved", via="ui",
    )
    run_id = admitted["run_id"]

    def _cancel_on_live(_run_id, _token):
        live_service.cancel(run_id)

    record = live_service.run_job(run_id, on_live=_cancel_on_live)
    assert record["state"] == "cancelled", record
    assert record["spawned"] is True
    assert record["tree_killed"] is True
    assert live_service.status(run_id)["state"] == "cancelled"


def test_live_crash_is_not_ok(live_service):
    _run_id, record = _approved_run(
        live_service, mode="lines",
        lines="import os\nos.kill(os.getpid(), 9)\n",
    )
    assert record["state"] == "crashed", record
    assert record["ok"] is False


def test_live_worker_uses_prepared_interpreter(live_service):
    _run_id, record = _approved_run(
        live_service, mode="lines",
        lines="import sys\nprint(sys.executable)\n",
    )
    assert record["state"] == "completed", record
    assert record["stdout"].strip() == sys.executable


def test_live_completed_verdict_never_pass(live_service):
    run_id, record = _approved_run(
        live_service, mode="lines", lines="print('ok')\n",
    )
    assert record["exit_code"] == 0
    assert record["verdict"]["status"] == "NOT_RUN"
    assert live_service.status(run_id)["verdict"]["status"] == "NOT_RUN"
