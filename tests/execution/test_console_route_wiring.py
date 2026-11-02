"""CONSOLE-ROUTE wiring — integrator-run AFTER the wiring patch lands.

These tests prove the console replay wiring the integrator applies
from docs/work/CONSOLE-ROUTE/wiring.patch: tier-2 op calls recorded
in a cell are stamped with the live head revision (plus a request
id) before they replay through the shared dispatch, so they admit
through ProjectService admission exactly like CRUD/MCP; caller-bound
revisions are preserved verbatim; effects report with run_ids.

Before the patch they skip loudly (console replay unstamped);
after it they run terminal sessions through the real Engine.
"""

import json
from pathlib import Path

import pytest


def _patched():
    """True once the integrator's wiring patch stamps console replay."""
    from rocket_engine.adapters import stdio_console

    source = Path(stdio_console.__file__).read_text(encoding="utf-8")
    return "stamp_tier2_call" in source and "collect_run_ids" in source


class _FakeRunner:
    """Stand-in worker: real approval binding, canned record + ops."""

    def __init__(self, tmp_path, ops=()):
        self._tmp = Path(tmp_path)
        self._tmp.mkdir(parents=True, exist_ok=True)
        self._ops = list(ops)

    @property
    def admission(self):
        return {"admitted": True, "reason": None,
                "network_isolated": False}

    def run_cell(self, session, approval_id, code, history_cursor,
                 env_digest, expected_revision, artifacts=(),
                 timeout_s=None, on_live=None):
        session.admit_cell(
            approval_id, code=code, history_cursor=history_cursor,
            env_digest=env_digest, expected_revision=expected_revision,
        )
        harvested = []
        if self._ops:
            ops_file = self._tmp / "fake_harvest.jsonl"
            ops_file.write_text(
                "".join(json.dumps(op) + "\n" for op in self._ops),
                encoding="utf-8",
            )
            harvested.append({"name": "__console_ops.jsonl",
                              "path": str(ops_file),
                              "bytes": ops_file.stat().st_size,
                              "sha256": "0" * 64})
        return {"run_id": "run_fake", "state": "completed", "ok": True,
                "reason": None, "exit_code": 0, "stdout": "fake-out\n",
                "stderr": "", "partial": False, "artifacts": harvested,
                "rejected_artifacts": [], "network_isolated": False,
                "credential_revoked": True, "tree_killed": True,
                "scratch": str(self._tmp)}


class _StubEngine:
    """Recording engine: canned head plus canned run payloads."""

    def __init__(self, head="p7", run_payload=None):
        self._head = head
        self._run_payload = run_payload or {"run_id": "run-x"}
        self.commands = []

    def snapshot(self):
        return {"project_id": "stub", "current_revision": self._head,
                "event_cursor": 0}

    def run(self, command):
        self.commands.append(("run", command))
        return dict(self._run_payload)

    def submit(self, command):
        self.commands.append(("submit", command))
        return {"state": "queued", **self._run_payload}


def _open_console(engine, tmp_path, ops):
    from rocket_engine.adapters.stdio_console import StdioConsole

    root = tmp_path / "console"
    return StdioConsole(
        engine, project_id="wire-live", actor="wire-agent",
        root=str(root),
        cell_runner=_FakeRunner(tmp_path / "harvest", ops=ops),
    )


@pytest.fixture
def engine():
    if not _patched():
        pytest.skip("wiring patch not applied: console replay unstamped")
    from rocket_engine.composition import Engine

    return Engine("wire-live", actor="wire-agent")


def test_console_cell_mutation_admits_at_live_head(engine, tmp_path):
    ops = [{"operation": "write_doc",
            "arguments": {"path": "notes/a.txt", "content": "hi\n"}}]
    with _open_console(engine, tmp_path, ops) as console:
        record = console.submit("tools.write_doc(path='notes/a.txt')\n")
    assert record["ops_ok"] is True
    assert engine.snapshot()["current_revision"] == "p13"
    assert engine.submit({
        "project_id": "wire-live", "operation": "read_doc",
        "arguments": {"path": "notes/a.txt"}, "request_id": "wire-read",
    })["content"] == "hi\n"
    events = engine.events_since(0)
    assert len(events) == 1
    assert events[0]["actor"] == "wire-agent"
    assert events[0]["data"]["revision"] == "p13"


def test_place_cell_from_console_session(engine, tmp_path):
    from rocket_engine.library.apig_catalog import static_provider

    engine.register_cells([{
        "cell": "nand2", "pdk": "demo", "pdk_revision": "r1",
        "ports": ["A", "B", "Y"], "default_params": {"w": 1.0},
    }], source="wiring")
    ops = [{"operation": "place_cell",
            "arguments": {"cell": "nand2", "instance_id": "top_nand"}}]
    with _open_console(engine, tmp_path, ops) as console:
        record = console.submit("tools.place_cell(cell='nand2')\n")
    assert record["ops_ok"] is True
    assert engine.snapshot()["current_revision"] == "p13"
    stored = engine.submit({
        "project_id": "wire-live", "operation": "read_doc",
        "arguments": {"path": "components/top_nand.yaml"},
        "request_id": "wire-read-cell",
    })["content"]
    assert "nand2" in stored


def test_stale_caller_binding_recorded_as_error(engine, tmp_path):
    ops = [{"operation": "write_doc",
            "arguments": {"path": "notes/a.txt", "content": "hi\n",
                          "expected_revision": "p999"}}]
    with _open_console(engine, tmp_path, ops) as console:
        record = console.submit("tools.write_doc(path='notes/a.txt')\n")
    assert record["ops_ok"] is False
    (result,) = record["op_results"]
    assert result["ok"] is False
    assert result["error"]["code"] == "revision_conflict"
    assert engine.snapshot()["current_revision"] == "p12"


def test_tier2_stamped_but_tier1_untouched(tmp_path):
    if not _patched():
        pytest.skip("wiring patch not applied: console replay unstamped")
    stub = _StubEngine(head="p7")
    ops = [
        {"operation": "write_doc",
         "arguments": {"path": "a.txt", "content": "b\n"}},
        {"operation": "read_doc", "arguments": {"path": "a.txt"}},
    ]
    with _open_console(stub, tmp_path, ops) as console:
        console.submit("tools.write_doc(path='a.txt')\n")
    by_op = {command["operation"]: command
             for _via, command in stub.commands}
    assert by_op["write_doc"]["arguments"]["expected_revision"] == "p7"
    assert "expected_revision" not in by_op["read_doc"]["arguments"]
    assert by_op["write_doc"]["request_id"]
    assert by_op["read_doc"]["request_id"]


def test_effects_carry_run_ids(tmp_path):
    if not _patched():
        pytest.skip("wiring patch not applied: console replay unstamped")
    stub = _StubEngine(head="p7", run_payload={"run_id": "run-x"})
    ops = [{"operation": "write_doc",
            "arguments": {"path": "a.txt", "content": "b\n"}}]
    with _open_console(stub, tmp_path, ops) as console:
        record = console.submit("tools.write_doc(path='a.txt')\n")
    assert record["effects"] == {"run_ids": ["run-x"], "replayed": True}


def test_rewind_covers_console_session(engine, tmp_path):
    ops = [{"operation": "write_doc",
            "arguments": {"path": "notes/a.txt", "content": "v1\n"}}]
    with _open_console(engine, tmp_path, ops) as console:
        console.submit("tools.write_doc(path='notes/a.txt')\n")
    assert engine.snapshot()["current_revision"] == "p13"
    rewound = engine.submit({
        "project_id": "wire-live", "operation": "rewind",
        "arguments": {"target_revision": "p12",
                      "expected_revision": "p13"},
        "request_id": "wire-rewind",
    })
    assert rewound["current_revision"] == "p14"
    assert rewound["events"][0]["event"] == "project_rewound"


def test_ecs_verb_live_when_peer_wired(tmp_path):
    if not _patched():
        pytest.skip("wiring patch not applied: console replay unstamped")
    from rocket_engine.execution.console.route import ConsoleNamespace
    from rocket_engine.project.errors import ProjectError
    from rocket_engine.project.service import ProjectService

    if not hasattr(ProjectService, "create_entity"):
        pytest.skip("ENGINE-ECS patch not applied: entity verbs unwired")
    project = ProjectService("wire-ecs", actor="wire-agent")
    namespace = ConsoleNamespace(project)
    created = namespace.create_entity(
        kind="block", request_id="wire-ecs-1", expected_revision="p12"
    )
    assert created["current_revision"] == "p13"
    assert created["events"][0]["event"] == "entity_created"
    assert created["events"][0]["actor"] == "wire-agent"


def test_wire_verb_admits_or_refuses_cleanly(tmp_path):
    if not _patched():
        pytest.skip("wiring patch not applied: console replay unstamped")
    from rocket_engine.execution.console.route import ConsoleNamespace
    from rocket_engine.project.errors import ProjectError
    from rocket_engine.project.service import ProjectService

    project = ProjectService("wire-wire", actor="wire-agent")
    namespace = ConsoleNamespace(project)
    kwargs = {
        "segments": [[[0, 0], [10, 0]]], "layer": "m1",
        "endpoints": [{"ref": None, "xy": [0, 0]},
                      {"ref": None, "xy": [10, 0]}],
    }
    if not hasattr(ProjectService, "place_wire"):
        with pytest.raises(ProjectError) as excinfo:
            namespace.place_wire(
                **kwargs, request_id="wire-w-1", expected_revision="p12"
            )
        assert excinfo.value.code == "unsupported_operation"
        assert project.snapshot()["current_revision"] == "p12"
        return
    try:
        receipt = namespace.place_wire(
            **kwargs, request_id="wire-w-1", expected_revision="p12"
        )
    except ProjectError as exc:
        assert exc.code == "unsupported_operation"
        assert project.snapshot()["current_revision"] == "p12"
        assert project.events_since(0) == []
    else:
        assert receipt["current_revision"] != "p12"
        assert receipt["events"]
