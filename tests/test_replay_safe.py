"""REPLAY-SAFE: report-not-run survivors + explicit resume + quarantine.

RED: src/execution/replay_safe.py does not exist yet; the loader below
fails until the module lands.
"""

import importlib.util
import logging
from pathlib import Path

import pytest

from rocket_engine.project.service import ProjectService

ROOT = Path(__file__).resolve().parent.parent


def _load_replay():
    spec = importlib.util.spec_from_file_location(
        "replay_safe", ROOT / "src" / "execution" / "replay_safe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLedger:
    """Post-wiring ledger port: job_queued carries content_key."""

    def __init__(self, mod):
        self._mod = mod
        self._events = []
        self._commands = {}
        self._seq = 0

    def events_since(self, cursor):
        return [dict(e) for e in self._events if e["seq"] > cursor]

    def command_for(self, request_id):
        return self._commands[request_id]

    def append_replay_event(self, event, request_id, data):
        self._seq += 1
        record = {
            "seq": self._seq,
            "event": event,
            "request_id": request_id,
            "project_id": "t",
            "actor": "test",
            "data": dict(data),
        }
        self._events.append(record)
        return record

    def admit(self, operation, arguments, request_id, run_id=None,
            with_key=True):
        run_id = run_id or f"run-{request_id}"
        command = {"operation": operation, "arguments": dict(arguments)}
        ack = {
            "request_id": request_id,
            "run_id": run_id,
            "snapshot_id": f"snap-{request_id}",
        }
        self._commands[request_id] = (command, ack)
        data = {"run_id": run_id, "operation": operation}
        if with_key:
            data["content_key"] = self._mod.content_key_for(
                operation, arguments
            )
        self.append_replay_event("job_queued", request_id, data)
        return ack

    def start(self, run_id, request_id, operation, content_key):
        self.append_replay_event(
            "run_started", request_id,
            {"run_id": run_id, "operation": operation,
             "content_key": content_key},
        )

    def complete(self, run_id, request_id, operation):
        self.append_replay_event(
            "run_completed", request_id,
            {"run_id": run_id, "operation": operation,
             "verdict": {"status": "PASS"}},
        )


def _recorder(ledger):
    calls = []

    def run(operation, arguments, snapshot_id, request_id, run_id):
        calls.append({
            "operation": operation,
            "arguments": dict(arguments),
            "snapshot_id": snapshot_id,
            "request_id": request_id,
            "run_id": run_id,
        })
        ledger.complete(run_id, request_id, operation)
        return {
            "run_id": run_id,
            "state": "completed",
            "verdict": {"status": "PASS"},
            "operation": operation,
        }

    run.calls = calls
    return run


def _text(operation, arguments, revision):
    import io

    from ruamel.yaml import YAML

    buf = io.StringIO()
    YAML(typ="safe").dump(
        {"operation": operation, "arguments": arguments}, buf
    )
    return buf.getvalue()


def test_boot_reports_survivors_and_never_executes():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    ledger.admit("run_syntax", {"cell": "b"}, "req-b")
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    report = replay.boot()
    assert report["unfinished"] == 2
    assert [s["run_id"] for s in report["survivors"]] == [
        "run-req-a", "run-req-b",
    ]
    assert all(s["kind"] == mod.RETRYABLE for s in report["survivors"])
    assert all(s["actions"] == ["resume", "discard"]
               for s in report["survivors"])
    assert replay._executor.calls == []


def test_pkill_then_boot_message_shape():
    mod = _load_replay()
    one = mod.boot_message(1)
    assert "ended unexpectedly" in one
    assert "1 run unfinished" in one
    assert "nothing re-ran automatically" in one
    assert "Resume" in one and "Discard" in one
    five = mod.boot_message(5)
    assert "5 runs unfinished" in five
    assert "nothing re-ran automatically" in five
    clean = mod.boot_message(0)
    assert "nothing re-ran automatically" not in clean
    assert "No unfinished runs" in clean


def test_kill9_midqueue_reboot_zero_executions_full_report(tmp_path):
    mod = _load_replay()
    root = str(tmp_path / "eng")
    live = ProjectService("kill9", actor="t", engine_root=root)
    head = "p12"
    for tag in ("a", "b", "c"):
        live.submit(
            _text("run_syntax", {"cell": tag}, head), f"req-{tag}",
            expected_revision=head,
        )
        head = live.snapshot()["current_revision"]
    rebooted = ProjectService("kill9", actor="t", engine_root=root)

    class _Port:
        def events_since(self, cursor):
            return rebooted.events_since(cursor)

        def command_for(self, request_id):
            return rebooted.command_for(request_id)

        def append_replay_event(self, event, request_id, data):
            raise AssertionError("boot must not execute or mark this")

    calls = []
    replay = mod.ReplaySafe(_Port(), lambda *a: calls.append(a))
    report = replay.boot()
    assert report["unfinished"] == 3
    assert calls == []
    assert "nothing re-ran automatically" in report["message"]


def test_never_started_is_retryable_with_resume():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    (survivor,) = replay.boot()["survivors"]
    assert survivor["kind"] == mod.RETRYABLE
    assert survivor["quarantined"] is False
    assert survivor["interrupts"] == 0
    completion = replay.resume(survivor["run_id"])
    assert completion["state"] == "completed"
    assert replay._executor.calls != []


def test_started_uncompleted_is_ambiguous_resume_once_no_force():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ack = ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    key = mod.content_key_for("run_syntax", {"cell": "a"})
    ledger.start(ack["run_id"], "req-a", "run_syntax", key)
    executor = _recorder(ledger)
    replay = mod.ReplaySafe(ledger, executor)
    report = replay.boot()
    (survivor,) = report["survivors"]
    assert survivor["kind"] == mod.AMBIGUOUS
    assert survivor["interrupts"] == 1
    assert survivor["quarantined"] is False
    assert executor.calls == []
    completion = replay.resume(survivor["run_id"])
    assert completion["verdict"] == {"status": "PASS"}
    assert len(executor.calls) == 1


def test_twice_interrupted_key_quarantines_poison_force_only():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    args = {"cell": "hung-deck"}
    first = ledger.admit("run_drc", args, "req-1")
    key = mod.content_key_for("run_drc", args)
    ledger.start(first["run_id"], "req-1", "run_drc", key)
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    assert replay.boot()["survivors"][0]["kind"] == mod.AMBIGUOUS
    # Crash again mid-resume: same key interrupted a second time.
    ledger.start(first["run_id"], "req-1", "run_drc", key)
    replay2 = mod.ReplaySafe(ledger, _recorder(ledger))
    report = replay2.boot()
    (survivor,) = report["survivors"]
    assert survivor["kind"] == mod.POISON
    assert survivor["quarantined"] is True
    assert survivor["interrupts"] == 2
    assert report["quarantined"] == [survivor["run_id"]]
    with pytest.raises(Exception) as refused:
        replay2.resume(survivor["run_id"])
    assert refused.value.code == "poison_quarantined"
    completion = replay2.resume(survivor["run_id"], force=True)
    assert completion["state"] == "completed"


def test_poisoned_key_quarantines_fresh_retryable_sibling():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    args = {"cell": "hung-deck"}
    first = ledger.admit("run_drc", args, "req-1")
    key = mod.content_key_for("run_drc", args)
    ledger.start(first["run_id"], "req-1", "run_drc", key)
    mod.ReplaySafe(ledger, _recorder(ledger)).boot()
    ledger.start(first["run_id"], "req-1", "run_drc", key)
    mod.ReplaySafe(ledger, _recorder(ledger)).boot()
    sibling = ledger.admit("run_drc", args, "req-2")
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    kinds = {s["run_id"]: s for s in replay.boot()["survivors"]}
    assert kinds[sibling["run_id"]]["quarantined"] is True
    assert kinds[sibling["run_id"]]["kind"] == mod.POISON
    batch = replay.resume_all_retryable()
    assert batch["resumed"] == []
    assert batch["skipped"][0]["code"] in (
        "poison_quarantined", "ambiguous_requires_explicit_resume",
    )


def test_refusals_typed_friendly_no_internals(caplog):
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    replay.boot()
    with caplog.at_level(logging.INFO, logger="replay_safe"):
        with pytest.raises(Exception) as unknown:
            replay.resume("run-nope")
    assert unknown.value.code == "unknown_survivor"
    assert "run-nope" not in str(unknown.value)
    assert "ck_" not in str(unknown.value)
    assert any("run-nope" in r.message for r in caplog.records)
    done = ledger.admit("run_syntax", {"cell": "b"}, "req-b")
    ledger.complete(done["run_id"], "req-b", "run_syntax")
    with pytest.raises(Exception) as finished:
        replay.resume(done["run_id"])
    assert finished.value.code == "already_completed"
    assert done["run_id"] not in str(finished.value)


def test_already_decided_refuses_second_action():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ack = ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    replay.boot()
    replay.discard(ack["run_id"])
    with pytest.raises(Exception) as second:
        replay.resume(ack["run_id"])
    assert second.value.code == "already_decided"


def test_discard_removes_survivor_forever():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ack = ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    executor = _recorder(ledger)
    replay = mod.ReplaySafe(ledger, executor)
    replay.boot()
    outcome = replay.discard(ack["run_id"])
    assert outcome["state"] == "discarded"
    assert executor.calls == []
    fresh = mod.ReplaySafe(ledger, _recorder(ledger))
    assert fresh.boot()["survivors"] == []
    with pytest.raises(Exception) as gone:
        fresh.resume(ack["run_id"])
    assert gone.value.code == "unknown_survivor"


def test_resume_all_retryable_skips_ambiguous_and_poison():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ok_ack = ledger.admit("run_syntax", {"cell": "ok"}, "req-ok")
    hung_args = {"cell": "hung"}
    hung = ledger.admit("run_drc", hung_args, "req-hung")
    hung_key = mod.content_key_for("run_drc", hung_args)
    ledger.start(hung["run_id"], "req-hung", "run_drc", hung_key)
    executor = _recorder(ledger)
    replay = mod.ReplaySafe(ledger, executor)
    replay.boot()
    batch = replay.resume_all_retryable()
    assert batch["resumed"] == [ok_ack["run_id"]]
    assert len(batch["completions"]) == 1
    assert [s["run_id"] for s in batch["skipped"]] == [hung["run_id"]]
    assert batch["skipped"][0]["code"] == (
        "ambiguous_requires_explicit_resume"
    )
    assert hung["run_id"] not in str(batch["skipped"][0]["message"])


def test_finished_runs_never_reexecuted_no_transcript_rerun():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ack = ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    ledger.complete(ack["run_id"], "req-a", "run_syntax")
    executor = _recorder(ledger)
    replay = mod.ReplaySafe(ledger, executor)
    report = replay.boot()
    assert report["survivors"] == []
    assert report["unfinished"] == 0
    assert replay.resume_all_retryable() == {
        "resumed": [], "completions": [], "skipped": [],
    }
    assert executor.calls == []
    assert not hasattr(replay, "replay_transcript")
    assert not hasattr(replay, "replay_all")


def test_boot_interrupt_marks_idempotent():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ack = ledger.admit("run_syntax", {"cell": "a"}, "req-a")
    key = mod.content_key_for("run_syntax", {"cell": "a"})
    ledger.start(ack["run_id"], "req-a", "run_syntax", key)
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    replay.boot()
    replay.boot()
    marks = [e for e in ledger.events_since(0)
             if e["event"] == "run_interrupted"]
    assert len(marks) == 1
    assert marks[0]["data"]["content_key"] == key


def test_content_key_stable_over_normalization():
    mod = _load_replay()
    base = mod.content_key_for("run_drc", {"cell": "a", "deck": "d1"})
    assert base == mod.content_key_for(
        "run_drc", {"deck": "d1", "cell": "a"}
    )
    assert base != mod.content_key_for("run_drc", {"cell": "a"})
    assert base != mod.content_key_for(
        "run_drc", {"cell": "a", "deck": "d2"}
    )
    assert base != mod.content_key_for("run_lvs", {"cell": "a"})
    assert base.startswith("ck_")


def test_pre_wiring_ledger_resolves_keys_via_command_for():
    mod = _load_replay()
    ledger = FakeLedger(mod)
    ledger.admit("run_syntax", {"cell": "a"}, "req-a", with_key=False)
    events = ledger.events_since(0)
    survivors = mod.survivors_from_events(events, ledger.command_for)
    assert survivors[0]["content_key"] == mod.content_key_for(
        "run_syntax", {"cell": "a"}
    )
    keyless = mod.survivors_from_events(events)
    assert keyless[0]["content_key"] is None
    assert keyless[0]["quarantined"] is False


def test_quarantine_refusal_logs_full_dev_context(caplog):
    mod = _load_replay()
    ledger = FakeLedger(mod)
    args = {"cell": "hung-deck"}
    ack = ledger.admit("run_drc", args, "req-1")
    key = mod.content_key_for("run_drc", args)
    ledger.start(ack["run_id"], "req-1", "run_drc", key)
    mod.ReplaySafe(ledger, _recorder(ledger)).boot()
    ledger.start(ack["run_id"], "req-1", "run_drc", key)
    replay = mod.ReplaySafe(ledger, _recorder(ledger))
    replay.boot()
    with caplog.at_level(logging.INFO, logger="replay_safe"):
        with pytest.raises(Exception):
            replay.resume(ack["run_id"])
    blob = " ".join(r.message for r in caplog.records)
    assert ack["run_id"] in blob
    assert key in blob
    assert "2" in blob
