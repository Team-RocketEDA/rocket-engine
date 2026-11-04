"""FINDINGS-QUERY RED — get_findings serves per-run finding pages.

`Engine.findings()` exists but no vocabulary name routes to it:
per-run finding pages are reachable only in-process. Valid RED
= these fail with unsupported_operation on the pre-slice engine.
"""

import pytest

PROJECT = "findings_demo"


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


class FakeSolver:
    """Hermetic solver with violations on demand."""

    def __init__(self, violations=()):
        self._violations = list(violations)

    def capabilities(self, target):
        return {"operations": ["run_syntax"], "tool": "fake"}

    def preflight(self, job):
        return dict(job, tool="fake")

    def execute(self, job):
        return {"exit_code": 0, "stdout": "", "stderr": "", "log": ""}

    def parse(self, native):
        return {"violations": list(self._violations)}


def _violation(tag):
    return {
        "rule": f"spacing-{tag}",
        "severity": "error",
        "message": f"too close {tag}",
        "bbox": [0, 0, 1, 1],
    }


def _engine(tmp_path):
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="tester",
                    engine_root=str(tmp_path))
    engine.register_solver(
        "run_syntax",
        FakeSolver([_violation("a"), _violation("b")]),
        tool="fake")
    return engine


def _submit(engine, operation, arguments, request_id):
    return engine.submit(
        {
            "project_id": PROJECT,
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def test_vocabulary_carries_get_findings():
    from rocket_engine.interfaces.vocabulary import QUERIES

    assert "get_findings" in set(QUERIES)


def test_get_findings_unknown_run_fails_loudly(tmp_path):
    engine = _engine(tmp_path)
    with pytest.raises(Exception) as excinfo:
        _submit(engine, "get_findings", {"run_id": "no-such-run"},
                "req-findings-unknown")
    assert _code(excinfo) == "unknown_run"


def test_get_findings_pages_completed_run(tmp_path):
    engine = _engine(tmp_path)
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "cell": "a", "deck": {"tool": "fake"},
            },
            "request_id": "req-findings-run",
        }
    )
    page = _submit(
        engine, "get_findings", {"run_id": out["run_id"]},
        "req-findings-page")
    assert [f["rule"] for f in page["findings"]] == [
        "spacing-a", "spacing-b"]
    assert page["total_counts"] == {"error": 2}


def test_get_findings_respects_limit(tmp_path):
    engine = _engine(tmp_path)
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "cell": "a", "deck": {"tool": "fake"},
            },
            "request_id": "req-findings-limit-run",
        }
    )
    page = _submit(
        engine, "get_findings",
        {"run_id": out["run_id"], "limit": 1},
        "req-findings-limit")
    assert len(page["findings"]) == 1
    assert page["truncated"] is True
