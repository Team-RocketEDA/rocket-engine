"""API-GENERALIZE (d) SUBMIT-IMMEDIATE: inline execution reference semantics.

RED: src/execution/apig_submit.py does not exist yet; the loader below
fails until the module lands.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest

from rocket_engine.composition import Engine

ROOT = Path(__file__).resolve().parent.parent


def _load_submit():
    spec = importlib.util.spec_from_file_location(
        "apig_submit", ROOT / "src" / "execution" / "apig_submit.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeEngine:
    """Scripted engine port: submit queues, run executes once per run_id."""

    def __init__(self):
        self.runs = 0
        self._acks = {}
        self._done = {}

    def submit(self, command):
        request_id = command["request_id"]
        if request_id in self._acks:
            return dict(self._acks[request_id])
        ack = {
            "request_id": request_id,
            "project_id": command["project_id"],
            "run_id": uuid.uuid4().hex,
            "snapshot_id": "snapshot_fake",
            "state": "queued",
            "current_revision": "p13",
        }
        self._acks[request_id] = ack
        return dict(ack)

    def run(self, command):
        run_id = command["arguments"]["run_id"]
        if run_id in self._done:
            return dict(self._done[run_id])
        self.runs += 1
        completion = {
            "run_id": run_id,
            "state": "completed",
            "verdict": {"status": "PASS", "finding_counts": {}},
            "operation": "run_syntax",
        }
        self._done[run_id] = completion
        return dict(completion)

    def status(self, run_id):
        if run_id in self._done:
            completion = self._done[run_id]
            return {
                "run_id": run_id,
                "operation": completion["operation"],
                "state": "completed",
                "snapshot_id": "snapshot_fake",
                "verdict": completion["verdict"],
            }
        return {"run_id": run_id, "state": "queued", "verdict": None}


class _StubAdapter:
    """Counting solver stub for the real-Engine round trip."""

    def __init__(self):
        self.runs = 0

    def preflight(self, job):
        return {"ok": True}

    def execute(self, job):
        self.runs += 1
        return {"exit_code": 0, "log": "stub ok"}

    def parse(self, native):
        return {"violations": [], "measurements": [{"name": "gain", "value": 3.0}]}


def test_merge_keeps_ack_shape_and_adds_verdict():
    submit_mod = _load_submit()
    ack = {
        "request_id": "r1",
        "project_id": "p",
        "run_id": "run-1",
        "snapshot_id": "s1",
        "state": "queued",
        "current_revision": "p13",
        "event_cursor": 1,
    }
    completion = {
        "run_id": "run-1",
        "state": "completed",
        "verdict": {"status": "PASS"},
        "operation": "run_syntax",
    }
    merged = submit_mod.merge_ack_completion(ack, completion)
    for key in ("request_id", "project_id", "run_id", "snapshot_id",
                "current_revision", "event_cursor"):
        assert merged[key] == ack[key]
    assert merged["state"] == "completed"
    assert merged["verdict"] == {"status": "PASS"}
    assert merged["operation"] == "run_syntax"


def test_submit_runs_inline_with_one_execution_for_replays():
    submit_mod = _load_submit()
    engine = _FakeEngine()
    immediate = submit_mod.SubmitImmediate(engine, "demo")
    first = immediate.submit("run_syntax", {"cell": "x"}, request_id="req-1")
    assert first["state"] == "completed"
    assert first["verdict"]["status"] == "PASS"
    assert first["request_id"] == "req-1"
    second = immediate.submit("run_syntax", {"cell": "x"}, request_id="req-1")
    assert second == first
    assert engine.runs == 1


def test_fetch_is_idempotent_after_completion():
    submit_mod = _load_submit()
    engine = _FakeEngine()
    immediate = submit_mod.SubmitImmediate(engine, "demo")
    submitted = immediate.submit("run_syntax", {"cell": "x"}, request_id="req-1")
    assert immediate.fetch(submitted["run_id"]) == submitted
    assert immediate.fetch(submitted["run_id"]) == submitted
    assert engine.runs == 1


def test_submit_passes_through_an_already_immediate_engine():
    submit_mod = _load_submit()

    class _WiredEngine(_FakeEngine):
        def submit(self, command):
            ack = super().submit(command)
            ack["state"] = "completed"
            ack["verdict"] = {"status": "PASS"}
            ack["operation"] = "run_syntax"
            return ack

    engine = _WiredEngine()
    immediate = submit_mod.SubmitImmediate(engine, "demo")
    merged = immediate.submit("run_syntax", {"cell": "x"}, request_id="req-1")
    assert merged["state"] == "completed"
    assert merged["verdict"] == {"status": "PASS"}
    assert engine.runs == 0


def test_real_engine_round_trip_through_public_port():
    submit_mod = _load_submit()
    engine = Engine("submitdemo", actor="test")
    stub = _StubAdapter()
    engine.register_solver("run_syntax", stub, tool="apig_stub")
    head = engine.snapshot()["current_revision"]
    immediate = submit_mod.SubmitImmediate(engine, "submitdemo")
    merged = immediate.submit(
        "run_syntax",
        {"cell": "x", "expected_revision": head,
         "deck": {"tool": "apig_stub"}},
        request_id="req-inline-1",
    )
    assert merged["state"] == "completed"
    assert merged["verdict"]["status"] == "PASS"
    assert merged["verdict"]["measurements"] == [{"name": "gain", "value": 3.0}]
    status = engine.submit({
        "project_id": "submitdemo",
        "operation": "get_job_status",
        "arguments": {"run_id": merged["run_id"]},
        "request_id": "req-status-1",
    })
    assert status["state"] == "completed"
    assert status["verdict"]["status"] == "PASS"
    assert stub.runs == 1
    assert immediate.fetch(merged["run_id"]) == merged
