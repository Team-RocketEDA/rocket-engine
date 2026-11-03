"""BATCH-PARALLEL RED — concurrent drain, per-item cancel/states/summary.

Valid RED = ApigPool has no max_workers/discard, _run_batch has no
cancel/gate/summary handling, cancel_job knows only the pyexec lane.
"""
import threading

import pytest

PROJECT = "batch_demo"


class FakeSolver:
    """Hermetic solver: barrier-proven overlap, verdict on demand."""

    def __init__(self, barrier=None, violations=()):
        self.barrier = barrier
        self.violations = list(violations)
        self.calls = []

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "fake"}

    def preflight(self, job):
        return dict(job, tool="fake")

    def execute(self, job):
        self.calls.append(job)
        if self.barrier is not None:
            self.barrier.wait(timeout=30)
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


def _submit(engine, tag, deck_tool="fake"):
    head = engine._project.snapshot()["current_revision"]
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "cell": tag, "deck": {"tool": deck_tool},
                "expected_revision": head,
            },
            "request_id": f"req-{tag}",
        }
    )


# pool level --------------------------------------------------------------


def _text(operation, arguments):
    import io

    from ruamel.yaml import YAML

    buf = io.StringIO()
    YAML(typ="safe").dump(
        {"operation": operation, "arguments": arguments}, buf
    )
    return buf.getvalue()


def test_concurrent_drain_overlaps_independent_runs_in_order():
    from rocket_engine.execution.apig.pool import ApigPool
    from rocket_engine.project.service import ProjectService

    project = ProjectService("pool_demo", actor="test")
    barrier = threading.Barrier(3)
    calls = []

    def runner(operation, arguments, snapshot_id, request_id, run_id):
        calls.append(run_id)
        barrier.wait(timeout=30)
        project.append_run_event(
            "run_completed", run_id, operation, {"status": "PASS"},
            request_id,
        )
        return {
            "run_id": run_id, "state": "completed",
            "verdict": {"status": "PASS"}, "operation": operation,
        }

    pool = ApigPool(project, runner, max_depth=64, max_workers=3)
    head = project.snapshot()["current_revision"]

    ids = []
    for tag in ("a", "b", "c"):
        text = _text("run_syntax", {"cell": tag})
        ack = pool.submit_request(text, f"req-{tag}", expected_revision=head)
        ids.append(ack["run_id"])
        head = ack["current_revision"]
    completions = pool.drain_ids(list(ids))
    assert [c["run_id"] for c in completions] == ids
    assert all(c["verdict"]["status"] == "PASS" for c in completions)
    assert sorted(calls) == sorted(ids)


def test_discard_removes_queued_item_before_drain():
    from rocket_engine.execution.apig.pool import ApigPool
    from rocket_engine.project.service import ProjectService

    project = ProjectService("discard_demo", actor="test")
    calls = []

    def runner(operation, arguments, snapshot_id, request_id, run_id):
        calls.append(run_id)
        return {
            "run_id": run_id, "state": "completed",
            "verdict": {"status": "PASS"}, "operation": operation,
        }

    pool = ApigPool(project, runner, max_depth=64)
    head = project.snapshot()["current_revision"]

    ids = []
    for tag in ("a", "b", "c"):
        text = _text("run_syntax", {"cell": tag})
        ack = pool.submit_request(text, f"req-{tag}", expected_revision=head)
        ids.append(ack["run_id"])
        head = ack["current_revision"]
    assert pool.discard(ids[1]) is True
    assert pool.discard("run_missing") is False
    completions = pool.drain_ids(list(ids))
    assert ids[1] not in calls
    assert [c["run_id"] for c in completions] == ids
    by_id = {c["run_id"]: c for c in completions}
    assert by_id[ids[1]]["state"] == "cancelled"
    assert by_id[ids[1]]["reason"] == "cancelled before dispatch"
    assert by_id[ids[1]]["verdict"]["status"] == "NOT_RUN"


# engine level ------------------------------------------------------------


def test_batch_summary_worst_state_wins_with_per_item_states():
    failer = FakeSolver(
        violations=[{"rule": "r", "severity": "error", "message": "m"}]
    )
    passer = FakeSolver()
    engine = _engine(passer)
    engine.register_solver("run_syntax", failer, tool="checker-bad")

    ok1 = _submit(engine, "ok1")
    ok2 = _submit(engine, "ok2")
    bad = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "cell": "bad",
                "deck": {"tool": "checker-bad"},
                "expected_revision": engine._project.snapshot()[
                    "current_revision"
                ],
            },
            "request_id": "req-bad",
        }
    )
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {
                "run_ids": [ok1["run_id"], bad["run_id"], ok2["run_id"]]
            },
            "request_id": "req-batch-1",
        }
    )
    assert out["states"] == {
        ok1["run_id"]: "completed",
        bad["run_id"]: "failed",
        ok2["run_id"]: "completed",
    }
    assert out["summary"] == "failed"


def test_cancel_completed_solver_run_keeps_terminal_state():
    engine = _engine(FakeSolver())
    ack = _submit(engine, "solo")
    done = engine.cancel_job(ack["run_id"])
    assert done["state"] == "completed"


def test_cancel_unknown_run_refuses_loudly():
    from rocket_engine.execution.errors import ExecutionError

    engine = _engine(FakeSolver())
    with pytest.raises(ExecutionError) as exc:
        engine.cancel_job("run_nope_not_there")
    assert exc.value.code == "unknown_run"


def _submit_spice(engine, tag, request_id=None, extra_arguments=None):
    head = engine._project.snapshot()["current_revision"]
    arguments = {
        "cell": tag, "expected_revision": head,
        "deck": {"tool": "spice-fake"},
    }
    arguments.update(extra_arguments or {})
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_spice",
            "arguments": arguments,
            "request_id": request_id or f"req-spice-{tag}",
        }
    )


def test_batch_gate_refusal_leaves_independent_items_complete():
    from rocket_engine.interfaces.yaml_dump import dump_yaml_text

    spice_solver = FakeSolver()
    engine = _engine(FakeSolver())
    engine.register_solver("run_spice", spice_solver, tool="spice-fake")
    spice = _submit_spice(engine, "gain")
    assert spice["verdict"]["status"] == "PASS"
    # Admit post-layout straight through the pool: no inline drain,
    # so the batch pump is what first meets the drain-time gate.
    head = engine._project.snapshot()["current_revision"]
    post_text = dump_yaml_text(
        {
            "operation": "run_post_layout",
            "arguments": {
                "deck": {"tool": "fake"},
                "expected_revision": head,
            },
        }
    )
    engine.register_solver("run_post_layout", FakeSolver(), tool="fake")
    post_ack = engine._pool.submit_request(
        post_text, "req-post-1", expected_revision=head
    )
    post_run = post_ack["run_id"]
    # A fresh failing spice moves the latest verdict to FAIL.
    spice_solver.violations = [
        {"rule": "r", "severity": "error", "message": "m"}
    ]
    bad_spice = _submit_spice(engine, "loss", request_id="req-spice-loss")
    assert bad_spice["verdict"]["status"] == "FAIL"
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {"run_ids": [post_run, bad_spice["run_id"]]},
            "request_id": "req-batch-gate",
        }
    )
    by_id = {c.get("run_id"): c for c in out["completions"]}
    assert by_id[bad_spice["run_id"]]["verdict"]["status"] == "FAIL"
    assert any(
        r.get("code") == "unmet_dependency"
        and "run_spice" in r.get("message", "")
        and r.get("run_id") == post_run
        for r in out["refused"]
    )
