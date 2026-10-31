"""API-GENERALIZE (a) worker pool: in-order drain, backpressure, boot replay.

RED: src/execution/apig_pool.py does not exist yet; the loader below
fails until the module lands.
"""

import importlib.util
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from rocket_engine.execution.errors import ExecutionError
from rocket_engine.project.service import ProjectService

ROOT = Path(__file__).resolve().parent.parent
_yaml = YAML(typ="safe")


def _load_pool():
    spec = importlib.util.spec_from_file_location(
        "apig_pool", ROOT / "src" / "execution" / "apig_pool.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(operation, arguments):
    import io

    buf = io.StringIO()
    _yaml.dump({"operation": operation, "arguments": arguments}, buf)
    return buf.getvalue()


def _submit(pool_mod, pool, project, tag, head, operation="run_syntax"):
    text = _text(operation, {"cell": tag})
    ack = pool.submit_request(text, f"req-{tag}", expected_revision=head)
    return ack, ack["current_revision"]


def _recorder(results=None, project=None):
    calls = []
    outcomes = results or []

    def runner(operation, arguments, snapshot_id, request_id, run_id):
        calls.append(
            {
                "operation": operation,
                "arguments": arguments,
                "snapshot_id": snapshot_id,
                "request_id": request_id,
                "run_id": run_id,
            }
        )
        # Mirror Engine._run_operation: every drain appends exactly
        # one run event, so replay can tell done from pending.
        if outcomes:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                if project is not None:
                    project.append_run_event(
                        "run_failed", run_id, operation,
                        {"status": "NOT_RUN", "reason": str(outcome)},
                        request_id,
                    )
                raise outcome
        if project is not None:
            project.append_run_event(
                "run_completed", run_id, operation, {"status": "PASS"},
                request_id,
            )
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": {"status": "PASS"},
            "operation": operation,
        }

    runner.calls = calls
    return runner


def test_spam_all_acked_exactly_once_in_drain_order():
    pool_mod = _load_pool()
    project = ProjectService("spam", actor="test")
    runner = _recorder()
    pool = pool_mod.ApigPool(project, runner, max_depth=64)
    head = "p12"
    acks = []
    for index in range(25):
        ack, head = _submit(pool_mod, pool, project, f"c{index:02d}", head)
        assert ack["state"] == "queued"
        acks.append(ack)
    assert len({ack["run_id"] for ack in acks}) == 25
    assert pool.pending() == [ack["run_id"] for ack in acks]
    completions = pool.drain()
    assert [c["run_id"] for c in completions] == [ack["run_id"] for ack in acks]
    assert [c["arguments"]["cell"] for c in runner.calls] == [
        f"c{index:02d}" for index in range(25)
    ]
    assert all(c["verdict"]["status"] == "PASS" for c in completions)
    assert pool.pending() == []
    assert pool.drain() == []


def test_replay_returns_same_ack_without_rerun():
    pool_mod = _load_pool()
    project = ProjectService("replay", actor="test")
    runner = _recorder()
    pool = pool_mod.ApigPool(project, runner)
    text = _text("run_syntax", {"cell": "x"})
    ack = pool.submit_request(text, "req-x", expected_revision="p12")
    assert pool.drain()[0]["run_id"] == ack["run_id"]
    assert len(runner.calls) == 1
    again = pool.submit_request(text, "req-x", expected_revision="p13")
    assert again == ack
    assert pool.pending() == []
    assert pool.drain() == []
    assert len(runner.calls) == 1


def test_backpressure_refuses_loudly_and_never_silent_drops():
    pool_mod = _load_pool()
    project = ProjectService("pressure", actor="test")
    pool = pool_mod.ApigPool(project, _recorder(), max_depth=2)
    head = "p12"
    _, head = _submit(pool_mod, pool, project, "a", head)
    _, head = _submit(pool_mod, pool, project, "b", head)
    with pytest.raises(ExecutionError) as caught:
        _submit(pool_mod, pool, project, "c", head)
    assert caught.value.code == "pool_full"
    assert "c" in str(caught.value) or "req-c" in str(caught.value)
    # Refused before admission: the ledger advanced exactly twice.
    assert project.snapshot()["current_revision"] == "p14"
    assert len(pool.pending()) == 2
    pool.drain(limit=1)
    ack, _ = _submit(pool_mod, pool, project, "c", head)
    assert ack["state"] == "queued"


def test_replay_never_refused_even_when_full():
    pool_mod = _load_pool()
    project = ProjectService("fullreplay", actor="test")
    pool = pool_mod.ApigPool(project, _recorder(), max_depth=1)
    text = _text("run_syntax", {"cell": "a"})
    ack = pool.submit_request(text, "req-a", expected_revision="p12")
    assert pool.submit_request(text, "req-a", expected_revision="p13") == ack


def test_runner_error_recorded_and_drain_continues():
    pool_mod = _load_pool()
    project = ProjectService("boom", actor="test")
    runner = _recorder(results=[None, RuntimeError("solver exploded"), None])
    pool = pool_mod.ApigPool(project, runner)
    head = "p12"
    acks = []
    for tag in ("a", "b", "c"):
        ack, head = _submit(pool_mod, pool, project, tag, head)
        acks.append(ack)
    completions = pool.drain()
    assert [c["run_id"] for c in completions] == [a["run_id"] for a in acks]
    assert completions[0]["state"] == "completed"
    assert completions[1]["state"] == "failed"
    assert "solver exploded" in completions[1]["error"]
    assert completions[2]["state"] == "completed"


def test_kill_reboot_replays_pending_only_exactly_once(tmp_path):
    pool_mod = _load_pool()
    root = tmp_path / "eng"
    project_a = ProjectService("kill", actor="test", engine_root=root)
    runner_a = _recorder(project=project_a)
    pool_a = pool_mod.ApigPool(project_a, runner_a)
    head = "p12"
    acks = []
    for tag in ("a", "b", "c"):
        ack, head = _submit(pool_mod, pool_a, project_a, tag, head)
        acks.append(ack)
    assert [c["run_id"] for c in pool_a.drain(limit=1)] == [acks[0]["run_id"]]
    del pool_a, project_a, runner_a  # kill -9 mid-queue
    project_b = ProjectService("kill", actor="test", engine_root=root)
    runner_b = _recorder(project=project_b)
    pool_b = pool_mod.ApigPool(project_b, runner_b)
    report = pool_b.replay(
        project_b.events_since(0),
        lambda request_id: project_b.command_for(request_id),
    )
    assert report["replayed"] == [acks[1]["run_id"], acks[2]["run_id"]]
    assert [c["run_id"] for c in report["completions"]] == report["replayed"]
    assert [c["arguments"]["cell"] for c in runner_b.calls] == ["b", "c"]
    assert report["skipped"] == []
    # Every request completed exactly once across the reboot.
    assert pool_b.replay(
        project_b.events_since(0),
        lambda request_id: project_b.command_for(request_id),
    )["replayed"] == []


def test_resubmit_of_completed_run_never_requeues(tmp_path):
    pool_mod = _load_pool()
    root = tmp_path / "eng"
    project_a = ProjectService("done", actor="test", engine_root=root)
    pool_a = pool_mod.ApigPool(project_a, _recorder())
    text = _text("run_syntax", {"cell": "a"})
    ack = pool_a.submit_request(text, "req-a", expected_revision="p12")
    pool_a.drain()
    project_a.append_run_event(
        "run_completed", ack["run_id"], "run_syntax",
        {"status": "PASS"}, "req-a",
    )
    del pool_a, project_a
    project_b = ProjectService("done", actor="test", engine_root=root)
    runner_b = _recorder()
    pool_b = pool_mod.ApigPool(project_b, runner_b)
    assert pool_b.submit_request(text, "req-a", expected_revision="p13") == ack
    assert pool_b.pending() == []
    assert pool_b.drain() == []
    assert runner_b.calls == []


def test_replay_names_unresolvable_requests_loudly():
    pool_mod = _load_pool()
    project = ProjectService("ghost", actor="test")
    pool = pool_mod.ApigPool(project, _recorder())
    events = [
        {"seq": 1, "event": "job_queued", "request_id": "req-ghost",
         "data": {"run_id": "run-ghost", "revision": "p13"}},
    ]

    def resolve(request_id):
        return project.command_for(request_id)

    report = pool.replay(events, resolve)
    assert report["replayed"] == []
    assert report["completions"] == []
    assert len(report["skipped"]) == 1
    assert report["skipped"][0]["request_id"] == "req-ghost"
    assert "reason" in report["skipped"][0]


def test_pending_and_stored_completion_helpers_are_pure():
    pool_mod = _load_pool()
    events = [
        {"seq": 1, "event": "job_queued", "request_id": "r1",
         "data": {"run_id": "run-1"}},
        {"seq": 2, "event": "job_queued", "request_id": "r2",
         "data": {"run_id": "run-2"}},
        {"seq": 3, "event": "run_completed", "request_id": "r1",
         "data": {"run_id": "run-1", "operation": "run_syntax",
                 "verdict": {"status": "PASS"}}},
    ]
    assert pool_mod.pending_from_events(events) == [("r2", "run-2")]
    stored = pool_mod.stored_completion_from_events(events, "run-1")
    assert stored["verdict"] == {"status": "PASS"}
    assert stored["operation"] == "run_syntax"
    assert pool_mod.stored_completion_from_events(events, "run-2") is None
    assert pool_mod.request_for_run(events, "run-2") == "r2"
    assert pool_mod.request_for_run(events, "run-missing") is None


def test_drain_ids_runs_subset_in_given_order():
    pool_mod = _load_pool()
    project = ProjectService("subset", actor="test")
    runner = _recorder()
    pool = pool_mod.ApigPool(project, runner)
    head = "p12"
    acks = []
    for tag in ("a", "b", "c"):
        ack, head = _submit(pool_mod, pool, project, tag, head)
        acks.append(ack)
    completions = pool.drain_ids([acks[2]["run_id"], acks[0]["run_id"]])
    assert [c["run_id"] for c in completions] == [
        acks[2]["run_id"], acks[0]["run_id"]]
    assert pool.pending() == [acks[1]["run_id"]]
