"""MCP-AGENT-PATH RED: an agent can run a job over MCP and read its result.

Uses the real Engine with a stand-in run_spice solver whose execute()
fakes ngspice output; verdicts come from the real NgspiceAdapter.parse().
Valid RED = Engine has no drain()/wired queries/constraints, and the MCP
server neither binds a project nor describes tool arguments.
"""

import asyncio
import json

import pytest

PROJECT = "opamp_demo"
GAIN = {"name": "dc_gain_db", "expr": "vdb(out)[0]", "unit": "dB"}
CONSTRAINTS = {"dc_gain_db": {"min": 60.0, "unit": "dB"}}


class StandInSpice:
    """Fakes only the ngspice process; parsing is the real adapter's."""

    def __init__(self, values):
        self.values = values

    def preflight(self, job):
        return job

    def execute(self, job):
        lines = ["ngspice-44 (stand-in)", "Circuit: opamp"]
        lines += [f"meas_{name} = {value}" for name, value in self.values.items()]
        return {
            "exit_code": 0, "stdout": "", "stderr": "", "log": "\n".join(lines),
            "sources": job.get("sources", []), "measurements": job["measurements"],
        }

    def parse(self, native):
        from rocket_engine.adapters.ngspice import NgspiceAdapter

        return NgspiceAdapter().parse(native)


def _engine(values, constraints=None):
    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp", constraints=constraints)
    engine.register_solver("run_spice", StandInSpice(values), tool="ngspice")
    return engine


def _submit(engine, name, arguments, request_id="r1"):
    return engine.submit({"project_id": PROJECT, "operation": name,
                          "arguments": arguments, "request_id": request_id})


def _query(engine, name, **arguments):
    return engine.submit({"project_id": PROJECT, "operation": name, "arguments": arguments})


def test_submitted_job_runs_under_the_same_run_id():
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    assert ack["state"] == "queued"
    assert _query(engine, "get_job_status", run_id=ack["run_id"])["state"] == "queued"

    engine.drain()
    status = _query(engine, "get_job_status", run_id=ack["run_id"])
    assert status["state"] == "completed"
    assert status["verdict"]["status"] == "FAIL"


def test_measurements_survive_a_pass():
    engine = _engine({"dc_gain_db": 62.5})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    engine.drain()
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "PASS"
    assert verdict["measurements"] == [{"name": "dc_gain_db", "value": 62.5, "unit": "dB",
                                        "target": {"min": 60}, "margin": 2.5, "status": "pass"}]


def test_check_results_logs_and_job_kinds_are_wired():
    engine = _engine({"dc_gain_db": 52.0})
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    engine.drain()

    results = _query(engine, "get_check_results")
    assert results["checks"]["run_spice"]["run_id"] == ack["run_id"]
    assert results["checks"]["run_spice"]["status"] == "FAIL"

    logs = _query(engine, "get_logs", run_id=ack["run_id"], query="meas_")
    assert logs["lines"] == ["3: meas_dc_gain_db = 52.0"]
    assert logs["total_lines"] == 3

    kinds = _query(engine, "list_job_kinds")
    assert {"operation": "run_spice", "tools": ["ngspice"]} in kinds["job_kinds"]


def test_unknown_run_is_a_clean_error():
    from rocket_engine.execution.errors import ExecutionError

    engine = _engine({})
    with pytest.raises(ExecutionError) as err:
        _query(engine, "get_job_status", run_id="nope")
    assert err.value.code == "unknown_run"


def test_targets_come_from_constraints_not_the_caller():
    from rocket_engine.project.errors import ProjectError

    engine = _engine({"dc_gain_db": 52.0}, constraints=CONSTRAINTS)
    with pytest.raises(ProjectError) as err:
        _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=40)]})
    assert err.value.code == "invalid_command"
    assert "constraints" in str(err.value)

    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [GAIN]}, request_id="r2")
    engine.drain()
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "FAIL"
    assert verdict["measurements"][0]["target"] == {"min": 60.0}


def test_a_crashing_solver_is_not_run_not_a_crash():
    class Boom(StandInSpice):
        def execute(self, job):
            raise RuntimeError("solver exploded")

    from rocket_engine.composition import Engine

    engine = Engine(PROJECT, actor="mcp")
    engine.register_solver("run_spice", Boom({}), tool="ngspice")
    ack = _submit(engine, "run_spice", {"expected_revision": "p12", "measurements": [dict(GAIN, min=60)]})
    engine.drain()
    verdict = _query(engine, "get_job_status", run_id=ack["run_id"])["verdict"]
    assert verdict["status"] == "NOT_RUN"
    assert "solver exploded" in verdict["reason"]


# --- MCP server: bound project, argument schemas, clean errors ---------------

def _call(handler, name, arguments):
    from mcp.types import CallToolRequestParams

    result = asyncio.run(handler(None, CallToolRequestParams(name=name, arguments=arguments)))
    return result, json.loads(result.content[0].text)


def test_tools_describe_their_arguments():
    from rocket_engine.adapters.mcp.server import tool_definitions

    tools = {tool.name: tool for tool in tool_definitions()}
    spice = tools["run_spice"].input_schema
    assert {"sources", "measurements"} <= set(spice["properties"])
    assert "min" not in json.dumps(spice["properties"]["measurements"])
    assert tools["get_logs"].input_schema["required"] == ["run_id"]


def test_bound_server_fills_project_and_revision_and_returns_results():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({"dc_gain_db": 62.5}, constraints=CONSTRAINTS)
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)

    _, ack = _call(call, "run_spice", {"measurements": [GAIN]})
    assert ack["state"] == "queued"
    _, status = _call(call, "get_job_status", {"run_id": ack["run_id"]})
    assert status["state"] == "completed"
    assert status["verdict"]["status"] == "PASS"


def test_engine_errors_come_back_as_json_not_exceptions():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({})
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)
    result, body = _call(call, "run_spice", {"expected_revision": "p11", "measurements": [GAIN]})
    assert result.is_error is True
    assert body == {"ok": False, "code": "revision_conflict", "message": body["message"]}

    result, body = _call(call, "get_job_status", {"run_id": "nope"})
    assert result.is_error is True and body["code"] == "unknown_run"


def test_bound_server_rejects_other_projects():
    from rocket_engine.adapters.mcp.server import make_handlers

    engine = _engine({})
    _, call = make_handlers(lambda project_id: engine, project_scope=PROJECT)
    result, body = _call(call, "get_project_snapshot", {"project_id": "someone_else"})
    assert result.is_error is True and body["code"] == "cross_project_denied"


def test_constraints_yaml_becomes_targets(tmp_path):
    from rocket_engine.adapters.mcp.server import load_constraints

    (tmp_path / "constraints.yaml").write_text(
        "checks:\n"
        "  - {id: opamp.dc_gain, metric: dc_gain_db, comparison: '>=', value: 60, unit: dB}\n"
        "  - {id: opamp.power, metric: power_uw, comparison: '<=', value: 500, unit: uW}\n"
        "  - {id: opamp.note, metric: label, comparison: '==', value: 1}\n"
    )
    assert load_constraints(tmp_path) == {
        "dc_gain_db": {"min": 60, "unit": "dB"},
        "power_uw": {"max": 500, "unit": "uW"},
    }
    assert load_constraints(tmp_path / "missing") is None
