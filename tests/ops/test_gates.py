"""OP-GATES RED — engine-side depends_on + gate-on-verdict guardrails.

Valid RED = `rocket_engine.ops.gates` does not exist yet.
"""
import pytest


def _mod():
    from rocket_engine.ops import gates  # RED: missing module

    return gates


def _events(*completions):
    """Ledger-style events from (run_id, operation, status) triples."""
    out = []
    # Ledger seqs are 1-based (ledger/events.py: seq = cursor + 1).
    for seq, (run_id, operation, status) in enumerate(completions, start=1):
        out.append(
            {
                "seq": seq,
                "event": "run_completed",
                "request_id": f"req_{run_id}",
                "data": {
                    "run_id": run_id,
                    "operation": operation,
                    "verdict": {"status": status},
                },
            }
        )
    return out


class _StubProject:
    def __init__(self, events):
        self._events = events

    def events_since(self, cursor):
        return [e for e in self._events if e.get("seq", 0) > cursor]


# hard deps -------------------------------------------------------------


def test_hard_dep_table_pins_lvs_behind_extraction():
    deps = _mod().hard_dependencies("run_lvs", "netgen")
    assert "run_extraction" in deps


def test_hard_dep_table_is_engine_declared_not_caller_args():
    mod = _mod()
    assert "run_extraction" in mod.hard_dependencies("run_lvs", "netgen")
    # Caller-supplied depends_on must never widen or narrow the table:
    assert mod.hard_dependencies(
        "run_lvs", "netgen", caller_depends_on=["run_spice"]
    ) == mod.hard_dependencies("run_lvs", "netgen")


def test_lvs_without_extraction_refuses_naming_gate():
    from rocket_engine.project.errors import ProjectError

    with pytest.raises(ProjectError) as exc:
        _mod().check_submit_gates(
            "run_lvs", {"deck": {"tool": "netgen"}},
            _StubProject(_events()), force=False,
        )
    assert exc.value.code == "unmet_dependency"
    assert "run_extraction" in str(exc.value)


def test_lvs_after_extraction_pass_admits():
    events = _events(("run_ext_001", "run_extraction", "PASS"))
    assert (
        _mod().check_submit_gates(
            "run_lvs", {"deck": {"tool": "netgen"}},
            _StubProject(events), force=False,
        )
        is None
    )


def test_hard_dep_ignores_force():
    from rocket_engine.project.errors import ProjectError

    with pytest.raises(ProjectError) as exc:
        _mod().check_submit_gates(
            "run_lvs", {"deck": {"tool": "netgen"}},
            _StubProject(_events()), force=True,
        )
    assert exc.value.code == "unmet_dependency"


def test_ungated_op_admits_without_history():
    assert (
        _mod().check_submit_gates(
            "run_drc", {"deck": {"tool": "magic"}},
            _StubProject(_events()), force=False,
        )
        is None
    )


# verdict gates ----------------------------------------------------------


def test_verdict_gate_latest_fail_refuses():
    from rocket_engine.project.errors import ProjectError

    events = _events(("run_sp_001", "run_spice", "FAIL"))
    with pytest.raises(ProjectError) as exc:
        _mod().check_submit_gates(
            "run_post_layout", {}, _StubProject(events), force=False
        )
    assert exc.value.code == "unmet_dependency"
    assert "run_spice" in str(exc.value)


def test_verdict_gate_latest_pass_admits():
    events = _events(
        ("run_sp_001", "run_spice", "FAIL"),
        ("run_sp_002", "run_spice", "PASS"),
    )
    assert (
        _mod().check_submit_gates(
            "run_post_layout", {}, _StubProject(events), force=False
        )
        is None
    )


def test_verdict_gate_force_bypasses():
    events = _events(("run_sp_001", "run_spice", "FAIL"))
    assert (
        _mod().check_submit_gates(
            "run_post_layout", {}, _StubProject(events), force=True
        )
        is None
    )


# engine wiring -----------------------------------------------------------


def test_submit_lvs_without_extraction_refuses_before_dispatch():
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("gates_demo", actor="tester")
    before = engine._project.snapshot()["current_revision"]
    with pytest.raises(ProjectError) as exc:
        engine.submit(
            {
                "project_id": "gates_demo",
                "operation": "run_lvs",
                "arguments": {"deck": {"tool": "netgen"}},
                "request_id": "req_gates_001",
            }
        )
    assert exc.value.code == "unmet_dependency"
    assert "run_extraction" in str(exc.value)
    # Refusal precedes admission: no solver touched, no revision advanced.
    assert engine._project.snapshot()["current_revision"] == before
