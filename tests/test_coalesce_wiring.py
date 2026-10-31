"""COALESCE-I33 wiring — Engine submit coalescing end to end.

The integrator runs this AFTER applying the
docs/work/COALESCE-I33 wiring patch: identical concurrent submits
share one execution (one run_id, every request_id logged mapping
to it), an intervening mutation forces separate executions, force
bypasses coalescing, and completed runs never coalesce (idempotent
fetch serves them). Every test skips until the patch lands
(ProjectService grows `log_coalesced_request`).
"""

import threading
import time

import pytest

from rocket_engine.composition import Engine
from rocket_engine.interfaces import ToolAdapter
from rocket_engine.project.service import ProjectService


def _wired():
    return hasattr(ProjectService, "log_coalesced_request")


needs_wiring = pytest.mark.skipif(
    not _wired(), reason="COALESCE-I33 wiring patch not applied"
)


class _GateSyntax(ToolAdapter):
    """run_syntax solver parked behind a test-controlled gate.

    execute() blocks until the test opens the gate, so overlapping
    submit lifetimes are deterministic: admissions pile up first,
    the run drains only when the test allows it.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = 0
        self._gate = threading.Event()

    @property
    def calls(self):
        with self._lock:
            return self._calls

    def open(self):
        self._gate.set()

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "gate"}

    def preflight(self, job):
        return {"deck": dict(job.get("deck") or {})}

    def execute(self, job):
        with self._lock:
            self._calls += 1
        if not self._gate.wait(timeout=30):
            from rocket_engine.adapters.errors import AdapterError

            raise AdapterError("runner_unavailable", "Test gate lapsed.")
        return {"exit_code": 0, "log": "gate-test"}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


def _engine():
    engine = Engine("i33_demo", actor="tester")
    gate = _GateSyntax()
    engine.register_solver("run_syntax", gate, tool="gate")
    return engine, gate


def _submit(engine, request_id, revision, force=False):
    command = {
        "project_id": "i33_demo",
        "operation": "run_syntax",
        "arguments": {
            "cell": "amp",
            "deck": {"tool": "gate"},
            "expected_revision": revision,
        },
        "request_id": request_id,
    }
    if force:
        command["force"] = True
    return engine.submit(command)


def _wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _mapped_request_ids(engine, run_id):
    """Every ledger event citing run_id, by requesting envelope."""
    hits = []
    for event in engine.events_since(0):
        data = event.get("data") or {}
        if data.get("run_id") != run_id:
            continue
        if event.get("event") in ("job_queued", "request_coalesced"):
            hits.append(event.get("request_id"))
    return hits


def _run_in_thread(engine, request_id, revision, out, force=False):
    try:
        out[request_id] = ("ok", _submit(engine, request_id, revision, force))
    except Exception as exc:  # noqa: BLE001 — surfaced by the test
        out[request_id] = ("error", exc)


def _join_all(threads):
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive()


@needs_wiring
def test_five_identical_submits_share_one_execution():
    engine, gate = _engine()
    head = engine.snapshot()["current_revision"]
    out = {}
    # All five carry the ORIGINAL head token: joiners skip the
    # revision gate (they mutate nothing), so spam-click still
    # coalesces after the owner's admission moves the head.
    threads = [
        threading.Thread(
            target=_run_in_thread, args=(engine, f"req-{n}", head, out)
        )
        for n in range(5)
    ]
    for thread in threads:
        thread.start()
    assert _wait_for(
        lambda: sum(
            1
            for event in engine.events_since(0)
            if event.get("event") in ("job_queued", "request_coalesced")
        )
        == 5
    )
    gate.open()
    _join_all(threads)
    assert gate.calls == 1
    results = []
    for n in range(5):
        status, payload = out[f"req-{n}"]
        assert status == "ok", payload
        results.append(payload)
    run_ids = {result["run_id"] for result in results}
    assert len(run_ids) == 1
    run_id = run_ids.pop()
    assert sorted(_mapped_request_ids(engine, run_id)) == sorted(
        f"req-{n}" for n in range(5)
    )
    assert sum(1 for r in results if r.get("coalesced") is True) == 4
    assert all(r["verdict"]["status"] == "PASS" for r in results)


@needs_wiring
def test_mutation_between_submits_forces_separate_executions():
    engine, gate = _engine()
    head = engine.snapshot()["current_revision"]
    out = {}
    owner = threading.Thread(
        target=_run_in_thread, args=(engine, "req-owner", head, out)
    )
    owner.start()
    assert _wait_for(lambda: gate.calls == 1)
    engine.submit(
        {
            "project_id": "i33_demo",
            "operation": "write_doc",
            "arguments": {
                "path": "notes.txt",
                "content": "bump",
                "expected_revision": engine.snapshot()["current_revision"],
            },
            "request_id": "req-mutate",
        }
    )
    late = threading.Thread(
        target=_run_in_thread,
        args=(engine, "req-late", engine.snapshot()["current_revision"], out),
    )
    late.start()
    assert _wait_for(lambda: gate.calls == 2)
    gate.open()
    _join_all([owner, late])
    assert out["req-owner"][0] == "ok", out["req-owner"][1]
    assert out["req-late"][0] == "ok", out["req-late"][1]
    first = out["req-owner"][1]["run_id"]
    second = out["req-late"][1]["run_id"]
    assert first != second
    assert "coalesced" not in out["req-late"][1]


@needs_wiring
def test_forced_duplicate_executes_fresh_and_registers_nothing():
    engine, gate = _engine()
    head = engine.snapshot()["current_revision"]
    out = {}
    owner = threading.Thread(
        target=_run_in_thread, args=(engine, "req-owner", head, out)
    )
    owner.start()
    assert _wait_for(lambda: gate.calls == 1)
    forced = threading.Thread(
        target=_run_in_thread,
        args=(
            engine,
            "req-forced",
            engine.snapshot()["current_revision"],
            out,
            True,
        ),
    )
    forced.start()
    assert _wait_for(lambda: gate.calls == 2)
    queued = [
        e
        for e in engine.events_since(0)
        if e.get("event") == "job_queued"
    ]
    assert len(queued) == 2
    owner_run = queued[0]["data"]["run_id"]
    forced_run = queued[1]["data"]["run_id"]
    assert owner_run != forced_run
    # The forced run bypasses the lane entirely: it never joins and
    # is never registered as a join target.
    assert engine._coalescer.requests_for(owner_run) == ["req-owner"]
    assert engine._coalescer.requests_for(forced_run) == []
    gate.open()
    _join_all([owner, forced])
    assert out["req-owner"][0] == "ok", out["req-owner"][1]
    assert out["req-forced"][0] == "ok", out["req-forced"][1]
    assert out["req-forced"][1]["run_id"] == forced_run
    assert "coalesced" not in out["req-forced"][1]


@needs_wiring
def test_completed_run_never_coalesces_fetch_serves_idempotently():
    engine, gate = _engine()
    gate.open()
    first = _submit(engine, "req-first", engine.snapshot()["current_revision"])
    second = _submit(engine, "req-second", engine.snapshot()["current_revision"])
    assert gate.calls == 2
    assert first["run_id"] != second["run_id"]
    assert "coalesced" not in second
    fetched = engine.run(
        {
            "project_id": "i33_demo",
            "operation": "run_job",
            "arguments": {"run_id": first["run_id"]},
        }
    )
    assert fetched["run_id"] == first["run_id"]
    assert fetched["verdict"] == first["verdict"]
    assert gate.calls == 2
