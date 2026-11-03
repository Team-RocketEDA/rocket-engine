"""DURABLE-FINDINGS RED — verdict detail survives a reboot.

`run_completed` ledger events carry only the verdict; the
findings list and the native log live in process memory. After
a restart, findings() and run_logs() fail unknown_run even
though the ledger knows the run finished.

Valid RED = the completion event has no findings/log data and
a rebuilt engine cannot read either back.
"""

import pytest

PROJECT = "durable_demo"


class FakeSolver:
    """Hermetic solver with violations and a log on demand."""

    def __init__(self, violations=(), log="fake log"):
        self._violations = list(violations)
        self._log = log
        self.calls = []

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "fake"}

    def preflight(self, job):
        return dict(job, tool="fake")

    def execute(self, job):
        self.calls.append(dict(job))
        return {
            "exit_code": 0, "stdout": "", "stderr": "",
            "log": self._log,
        }

    def parse(self, native):
        return {"violations": list(self._violations)}


def _violation(tag):
    return {
        "rule": f"spacing-{tag}",
        "severity": "error",
        "message": f"too close {tag}",
        "bbox": [0, 0, 1, 1],
    }


def _engine(root, solver, project=PROJECT):
    from rocket_engine.composition import Engine

    engine = Engine(project, actor="tester", engine_root=str(root))
    engine.register_solver("run_syntax", solver, tool="fake")
    return engine


def _run(engine, tag, request_id=None):
    return engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "cell": tag, "deck": {"tool": "fake"},
            },
            "request_id": request_id or f"req-{tag}",
        }
    )


def _completion_event(engine, run_id):
    events = engine._project.events_since(0)
    matches = [
        e for e in events
        if e.get("event") == "run_completed"
        and (e.get("data") or {}).get("run_id") == run_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_completion_event_carries_findings_and_log_tail(tmp_path):
    engine = _engine(tmp_path, FakeSolver([_violation("a")], log="l1\nl2\nl3"))
    out = _run(engine, "a")
    assert out["verdict"]["status"] == "FAIL"
    data = _completion_event(engine, out["run_id"])["data"]
    assert data["findings"] == [
        {
            "severity": "error",
            "rule": "spacing-a",
            "message": "too close a",
            "location": {"bbox_lambda": [0, 0, 1, 1]},
        }
    ]
    assert data["log_excerpt"] == "l1\nl2\nl3"
    assert data["log_lines"] == 3


def test_findings_survive_engine_rebuild(tmp_path):
    engine = _engine(tmp_path, FakeSolver([_violation("a"), _violation("b")]))
    out = _run(engine, "a")
    run_id = out["run_id"]

    rebuilt = _engine(tmp_path, FakeSolver())
    page = rebuilt.findings(run_id)
    assert page["total_counts"] == {"error": 2}
    assert [f["rule"] for f in page["findings"]] == ["spacing-a", "spacing-b"]
    assert page["truncated"] is False


def test_findings_truncate_large_lists(tmp_path):
    many = [_violation(str(i)) for i in range(250)]
    engine = _engine(tmp_path, FakeSolver(many))
    out = _run(engine, "a")
    data = _completion_event(engine, out["run_id"])["data"]
    assert len(data["findings"]) == 100
    assert data["findings_truncated"] == 150

    rebuilt = _engine(tmp_path, FakeSolver())
    page = rebuilt.findings(out["run_id"], limit=200)
    assert len(page["findings"]) == 100
    assert page["truncated"] is True
    assert page["total_counts"] == {"error": 250}


def test_logs_fallback_serves_tail_after_rebuild(tmp_path):
    log = "\n".join(f"line {i}" for i in range(1, 51))
    engine = _engine(tmp_path, FakeSolver([], log=log))
    out = _run(engine, "a")

    rebuilt = _engine(tmp_path, FakeSolver())
    page = rebuilt.run_logs(out["run_id"], limit=200)
    assert page["excerpt"] is True
    assert page["total_lines"] == 50
    assert page["lines"][0].startswith("1: line 1")
    assert page["lines"][-1] == "50: line 50"
