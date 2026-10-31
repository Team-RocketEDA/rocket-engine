"""LEDGER-DURABLE RED — durable attributed ledger + advancing revisions (I30).

Tests assume the LEDGER-DURABLE contract:
  - `ProjectService.submit` advances the revision on every accepted
    mutation and reports it as `ack["current_revision"]`; a stale
    `expected_revision` raises `revision_conflict` with no effects.
  - Every event carries its actor; `run()` appends `run_completed` /
    `run_failed` with a verdict link.
  - With `engine_root`, the log + revision survive restart under
    `ENGINE_ROOT/projects/<id>/` (`events.yaml` + `ledger.yaml`,
    both in `layout_schema.yaml`).
  - `get_events_since` is a wired query with cursor + resync
    semantics; retention trims oldest-first and stale contiguity
    demands raise `resync_required`.
Valid RED = these fail on the pre-slice service (constant p12,
in-memory log, no run events, no such query).
"""

import io

import pytest
from ruamel.yaml import YAML

PROJECT = "analog_demo"


def _dump(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def _command_text(operation="run_drc", revision="p12"):
    return _dump(
        {
            "schema": "rocketeda/tooling/v0.1",
            "project_id": PROJECT,
            "expected_revision": revision,
            "operation": operation,
            "arguments": {"cell": "amplifier"},
        }
    )


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_revision_advances_on_every_accepted_mutation():
    from rocket_engine.project import ProjectService  # RED: constant p12

    service = ProjectService(project_id=PROJECT, actor="human")
    first = service.submit(_command_text(), request_id="req-adv-1")
    assert first["current_revision"] == "p13"
    assert service.snapshot()["current_revision"] == "p13"
    second = service.submit(
        _command_text(revision="p13"), request_id="req-adv-2"
    )
    assert second["current_revision"] == "p14"
    assert service.snapshot()["current_revision"] == "p14"


def test_second_stale_writer_rejected_without_effects():
    from rocket_engine.project import ProjectService  # RED: constant p12

    service = ProjectService(project_id=PROJECT, actor="human")
    service.submit(_command_text(), request_id="req-duel-1")
    before = service.snapshot()["event_cursor"]
    with pytest.raises(Exception) as excinfo:
        service.submit(_command_text(), request_id="req-duel-2")
    assert _code(excinfo) == "revision_conflict"
    assert service.snapshot()["current_revision"] == "p13"
    assert service.snapshot()["event_cursor"] == before
    assert len(service.events_since(0)) == 1


def test_idempotent_replay_does_not_advance():
    from rocket_engine.project import ProjectService  # RED: constant p12

    service = ProjectService(project_id=PROJECT, actor="human")
    first = service.submit(_command_text(), request_id="req-replay-1")
    retry = service.submit(_command_text(), request_id="req-replay-1")
    assert retry == first
    assert service.snapshot()["current_revision"] == "p13"
    assert service.snapshot()["event_cursor"] == 1


def test_submit_event_carries_actor_revision_and_run_link():
    from rocket_engine.project import ProjectService  # RED: constant p12

    service = ProjectService(project_id=PROJECT, actor="human")
    ack = service.submit(_command_text(), request_id="req-attr-1")
    (record,) = service.events_since(0)
    assert record["event"] == "job_queued"
    assert record["actor"] == "human"
    assert record["request_id"] == "req-attr-1"
    assert record["data"]["run_id"] == ack["run_id"]
    assert record["data"]["revision"] == "p13"
    assert record["data"]["operation"] == "run_drc"


def test_events_and_revision_survive_restart(tmp_path):
    from rocket_engine.project import ProjectService  # RED: no engine_root

    root = tmp_path / "engine-root"
    first = ProjectService(
        project_id=PROJECT, actor="human", engine_root=root
    )
    ack = first.submit(_command_text(), request_id="req-restart-1")
    assert (root / "projects" / PROJECT / "events.yaml").is_file()
    assert (root / "projects" / PROJECT / "ledger.yaml").is_file()
    second = ProjectService(
        project_id=PROJECT, actor="human", engine_root=root
    )
    assert second.snapshot() == first.snapshot()
    assert second.events_since(0) == first.events_since(0)
    assert second.snapshot()["current_revision"] == "p13"
    assert second.snapshot()["event_cursor"] == 1
    follow = second.submit(
        _command_text(revision="p13"), request_id="req-restart-2"
    )
    assert follow["current_revision"] == "p14"
    assert ack["run_id"] != follow["run_id"]


def test_two_writers_one_durable_root_no_lost_update(tmp_path):
    from rocket_engine.composition import Engine  # RED: constant p12
    from rocket_engine.project import ProjectService  # noqa: F401

    root = tmp_path / "engine-root"
    human = Engine(PROJECT, actor="human", engine_root=root)
    fuel = Engine(PROJECT, actor="rocket-fuel", engine_root=root)
    ack = human.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {"expected_revision": "p12"},
            "request_id": "req-duel-a",
        }
    )
    assert ack["current_revision"] == "p13"
    with pytest.raises(Exception) as excinfo:
        fuel.submit(
            {
                "project_id": PROJECT,
                "operation": "run_syntax",
                "arguments": {"expected_revision": "p12"},
                "request_id": "req-duel-b",
            }
        )
    assert _code(excinfo) == "revision_conflict"
    follow = fuel.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {"expected_revision": "p13"},
            "request_id": "req-duel-c",
        }
    )
    assert follow["current_revision"] == "p14"
    events = human.events_since(0)
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5, 6]
    assert [e["actor"] for e in events] == [
        "human", "human", "human",
        "rocket-fuel", "rocket-fuel", "rocket-fuel",
    ]
    assert [e["event"] for e in events] == [
        "job_queued", "run_started", "run_failed",
        "job_queued", "run_started", "run_failed",
    ]
    assert [e["request_id"] for e in events] == [
        "req-duel-a", "req-duel-a", "req-duel-a",
        "req-duel-c", "req-duel-c", "req-duel-c",
    ]


class _PassAdapter:
    def capabilities(self, target):
        return {"operations": ["run_em"]}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return {"exit_code": 0, "stdout": "fake", "stderr": ""}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


class _FailingAdapter(_PassAdapter):
    def execute(self, job):
        from rocket_engine.adapters.errors import AdapterError

        raise AdapterError("runner_unavailable", "fake tool exploded")


def test_run_appends_run_completed_with_verdict_link():
    from rocket_engine.composition import Engine  # RED: run appends nothing

    engine = Engine(PROJECT, actor="rocket-fuel")
    engine.register_solver("run_em", _PassAdapter())
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_em",
            "arguments": {"deck": {"tool": "_PassAdapter"}},
        }
    )
    assert out["verdict"]["status"] == "PASS"
    (record,) = engine.events_since(0)
    assert record["event"] == "run_completed"
    assert record["actor"] == "rocket-fuel"
    assert record["data"]["run_id"] == out["run_id"]
    assert record["data"]["operation"] == "run_em"
    assert record["data"]["verdict"] == out["verdict"]
    assert engine.findings(out["run_id"])["findings"] == []


def test_run_appends_run_failed_on_not_run():
    from rocket_engine.composition import Engine  # RED: run appends nothing

    engine = Engine(PROJECT, actor="system")
    engine.register_solver("run_em", _FailingAdapter(), tool="failing")
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_em",
            "arguments": {"deck": {"tool": "failing"}},
        }
    )
    assert out["verdict"]["status"] == "NOT_RUN"
    (record,) = engine.events_since(0)
    assert record["event"] == "run_failed"
    assert record["actor"] == "system"
    assert record["data"]["run_id"] == out["run_id"]
    assert record["data"]["verdict"]["status"] == "NOT_RUN"


def test_run_job_completion_links_the_queued_request():
    from rocket_engine.composition import Engine  # RED: run appends nothing

    engine = Engine(PROJECT, actor="human")
    engine.register_solver("run_em", _PassAdapter())
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": "req-link-001",
        }
    )
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {"request_id": "req-link-001"},
        }
    )
    assert out["state"] == "completed"
    events = engine.events_since(0)
    assert [e["event"] for e in events] == [
        "job_queued", "run_started", "run_completed",
    ]
    assert events[1]["request_id"] == "req-link-001"
    assert events[1]["data"]["run_id"] == out["run_id"]
    assert events[2]["request_id"] == "req-link-001"
    assert events[2]["data"]["run_id"] == out["run_id"]


def test_get_events_since_query_wired_with_cursor_and_resync():
    from rocket_engine.composition import Engine  # RED: query unwired

    engine = Engine(PROJECT, actor="human")
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {"expected_revision": "p12"},
            "request_id": "req-query-1",
        }
    )
    page = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "get_events_since",
            "arguments": {"cursor": 0},
            "request_id": "req-query-2",
        }
    )
    assert page["project_id"] == PROJECT
    assert [e["event"] for e in page["events"]] == [
        "job_queued", "run_started", "run_failed",
    ]
    assert page["cursor"] == 3
    empty = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "get_events_since",
            "arguments": {"cursor": page["cursor"]},
            "request_id": "req-query-3",
        }
    )
    assert empty["events"] == []
    with pytest.raises(Exception) as excinfo:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "get_events_since",
                "arguments": {
                    "cursor": 0,
                    "require_contiguous_from": 10**9,
                },
                "request_id": "req-query-4",
            }
        )
    assert _code(excinfo) == "resync_required"


def test_retention_trims_oldest_and_forces_resync():
    from rocket_engine.project import ProjectService  # RED: no retention

    service = ProjectService(
        project_id=PROJECT, actor="system", max_retained_events=3
    )
    revision = "p12"
    for index in range(5):
        ack = service.submit(
            _command_text(revision=revision),
            request_id=f"req-trim-{index}",
        )
        revision = ack["current_revision"]
    assert revision == "p17"
    assert service.snapshot()["event_cursor"] == 5
    assert [e["seq"] for e in service.events_since(0)] == [3, 4, 5]
    with pytest.raises(Exception) as excinfo:
        service.events_since(cursor=0, require_contiguous_from=1)
    assert _code(excinfo) == "resync_required"
    kept = service.events_since(cursor=2, require_contiguous_from=3)
    assert [e["seq"] for e in kept] == [3, 4, 5]


def test_corrupt_durable_ledger_refuses_loudly(tmp_path):
    from rocket_engine.project import ProjectService  # RED: no engine_root

    root = tmp_path / "engine-root"
    ledger_dir = root / "projects" / PROJECT
    ledger_dir.mkdir(parents=True)
    (ledger_dir / "events.yaml").write_text("not: [valid, ledger\n")
    with pytest.raises(Exception) as excinfo:
        ProjectService(project_id=PROJECT, actor="human", engine_root=root)
    assert _code(excinfo) == "invalid_ledger"
