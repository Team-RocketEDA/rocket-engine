"""CLI-DISPATCH RED — op dispatch: the inbound port over one catalog.

Tests assume `parse_op_call` + `OpDispatcher` on
`rocket_engine.execution.dispatch` and `UsageError` on
`rocket_engine.execution` (defined in `.errors`). Valid RED = each
import fails: the dispatch port does not exist yet.

The dispatch is use-case-layer code: it turns op-call text into
validated (operation, arguments) against the one catalog
(`interfaces.vocabulary`, shared with MCP/console) and routes every
call — operations and read queries alike — to `submit`, the one
admission path. No adapter is imported here; adapters face this port.
"""

import pytest


def _dispatch():
    from rocket_engine.execution import dispatch  # RED: missing port

    return dispatch


def _usage_error():
    from rocket_engine.execution import UsageError  # RED: missing port

    return UsageError


def test_parse_good_call_yields_op_and_typed_args():
    parse_op_call = _dispatch().parse_op_call
    op, args = parse_op_call("run_drc tech=scmos timeout_s=30 fast=true benches=[ac,tran]")
    assert op == "run_drc"
    assert args == {"tech": "scmos", "timeout_s": 30, "fast": True,
                    "benches": ["ac", "tran"]}


def test_parse_nested_value_and_quoted_spaces():
    parse_op_call = _dispatch().parse_op_call
    op, args = parse_op_call(
        "run_drc tech=synthetic-kl deck='{tool: klayout}' note='a b'"
    )
    assert op == "run_drc"
    assert args == {"tech": "synthetic-kl", "deck": {"tool": "klayout"},
                    "note": "a b"}


def test_parse_bare_query_name_accepted():
    parse_op_call = _dispatch().parse_op_call
    assert parse_op_call("get_project_snapshot") == ("get_project_snapshot", {})


def test_parse_unknown_op_rejected_with_stable_code():
    UsageError = _usage_error()
    with pytest.raises(UsageError) as excinfo:
        _dispatch().parse_op_call("frobnicate x=1")
    assert excinfo.value.code == "unsupported_operation"
    assert "frobnicate" in str(excinfo.value)


def test_parse_host_shell_rejected_like_mcp():
    UsageError = _usage_error()
    with pytest.raises(UsageError) as excinfo:
        _dispatch().parse_op_call("host_shell cmd=whoami")
    assert excinfo.value.code == "unsupported_operation"


@pytest.mark.parametrize("line", ["", "   ", "run_drc tech", "run_drc =x",
                                  "run_drc tech="])
def test_parse_malformed_args_rejected(line):
    UsageError = _usage_error()
    with pytest.raises(UsageError) as excinfo:
        _dispatch().parse_op_call(line)
    assert excinfo.value.code == "invalid_command"


class FakeEngine:
    def __init__(self):
        self.runs = []
        self.submits = []

    def run(self, command):
        self.runs.append(command)
        return {"run_id": "run_fake", "state": "completed",
                "verdict": {"status": "PASS"}, "operation": command["operation"]}

    def submit(self, command):
        self.submits.append(command)
        return {"state": "queued", "run_id": "run_fake_q"}


def test_dispatcher_routes_operations_to_submit_with_envelope():
    dispatcher = _dispatch().OpDispatcher(FakeEngine(), project_id="p1",
                                          actor="cli")
    out = dispatcher.execute("run_em", {"x": 1}, request_id="r1")
    assert out["state"] == "queued"
    engine = dispatcher._engine
    assert len(engine.submits) == 1 and not engine.runs
    command = engine.submits[0]
    assert command["project_id"] == "p1"
    assert command["operation"] == "run_em"
    assert command["arguments"] == {"x": 1}
    assert command["request_id"] == "r1"


def test_dispatcher_routes_queries_to_submit():
    engine = FakeEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p1")
    out = dispatcher.execute("get_project_snapshot", {})
    assert out["state"] == "queued"
    assert len(engine.submits) == 1 and not engine.runs
    assert engine.submits[0]["operation"] == "get_project_snapshot"


def test_dispatcher_mints_request_id_when_missing():
    engine = FakeEngine()
    dispatcher = _dispatch().OpDispatcher(engine)
    dispatcher.execute("run_em", {})
    first = engine.submits[0]["request_id"]
    dispatcher.execute("run_em", {})
    assert first and engine.submits[1]["request_id"] and first != engine.submits[1]["request_id"]


def test_dispatcher_rejects_unknown_names_directly():
    UsageError = _usage_error()
    dispatcher = _dispatch().OpDispatcher(FakeEngine())
    with pytest.raises(UsageError) as excinfo:
        dispatcher.execute("frobnicate", {})
    assert excinfo.value.code == "unsupported_operation"


def test_execute_line_parses_and_submits():
    engine = FakeEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p9")
    op, out = dispatcher.execute_line("run_em x=2")
    assert op == "run_em"
    assert out["state"] == "queued"
    assert engine.submits[0]["arguments"] == {"x": 2}
    assert not engine.runs


class HeadEngine(FakeEngine):
    def snapshot(self):
        return {"current_revision": "p12"}


def test_dispatcher_fills_expected_revision_from_bound_head():
    engine = HeadEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p1")
    dispatcher.execute("run_em", {"x": 1})
    assert engine.submits[0]["arguments"] == {"x": 1,
                                              "expected_revision": "p12"}


def test_dispatcher_explicit_revision_wins_over_head():
    engine = HeadEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p1")
    dispatcher.execute("run_em", {"expected_revision": "p9"})
    assert engine.submits[0]["arguments"] == {"expected_revision": "p9"}


def test_dispatcher_leaves_call_unstamped_without_snapshot():
    engine = FakeEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p1")
    dispatcher.execute("run_em", {"x": 1})
    assert engine.submits[0]["arguments"] == {"x": 1}


def test_dispatcher_leaves_queries_untouched_with_head():
    engine = HeadEngine()
    dispatcher = _dispatch().OpDispatcher(engine, project_id="p1")
    dispatcher.execute("get_project_snapshot", {})
    assert engine.submits[0]["arguments"] == {}
