"""CONNECT-GRAPH wired integration — run AFTER the integrator applies the patch.

These tests prove the wiring patch, not the modules: a stock Engine
must serve run_connectivity/run_erc through the connectgraph solver
with verdicts judged from shared net names. They FAIL on an unwired
tree (unsupported_operation) and PASS once the integrator registers
the solver in composition.py, regenerates the API spec, and
reinstalls. Run: PYTHONPATH=/tmp/cgshim .venv/bin/python -m pytest
tests/workflows/test_connect_graph_wired.py -q (shim maps
rocket_engine -> src; see docs/work/CONNECT-GRAPH/report.md).
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "connect_graph_demo.json"


def _demo():
    return json.loads(FIXTURE.read_text())


def _engine():
    from rocket_engine.composition import Engine

    return Engine("connectgraph-probe", actor="probe")


def _submit(engine, operation, arguments, request_id):
    arguments = dict(arguments)
    arguments["expected_revision"] = engine.snapshot()["current_revision"]
    return engine.submit(
        {
            "project_id": "connectgraph-probe",
            "operation": operation,
            "arguments": arguments,
            "request_id": request_id,
        }
    )


def test_run_connectivity_serves_netlists_with_pass_verdict():
    engine = _engine()
    ack = _submit(engine, "run_connectivity", {"schematic": _demo()}, "cg-wired-1")
    done = engine.run(
        {
            "project_id": "connectgraph-probe",
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": "cg-wired-1-run",
        }
    )
    assert done["state"] == "completed"
    assert done["verdict"]["status"] == "PASS"
    netlists = done["verdict"]["measurements"]["netlists"]
    assert set(netlists) == {"spice", "verilog", "vhdl"}
    assert "X1 A net1 inv" in netlists["spice"]


def test_run_connectivity_short_fails_the_verdict():
    engine = _engine()
    schematic = _demo()
    schematic["labels"].append({"name": "Z", "xy": [-10, 10]})
    ack = _submit(engine, "run_connectivity", {"schematic": schematic}, "cg-wired-2")
    done = engine.run(
        {
            "project_id": "connectgraph-probe",
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": "cg-wired-2-run",
        }
    )
    assert done["verdict"]["status"] == "FAIL"


def test_run_erc_flags_unconnected_pin_as_fail():
    engine = _engine()
    schematic = _demo()
    schematic["pins"].append({"instance": "X1", "pin": "NC", "xy": [400, 400]})
    ack = _submit(engine, "run_erc", {"schematic": schematic}, "cg-wired-3")
    done = engine.run(
        {
            "project_id": "connectgraph-probe",
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": "cg-wired-3-run",
        }
    )
    assert done["verdict"]["status"] == "FAIL"


def test_job_kinds_lists_connectgraph_tools():
    kinds = {entry["operation"]: entry["tools"] for entry in _engine().job_kinds()["job_kinds"]}
    assert kinds["run_connectivity"] == ["connectgraph"]
    assert kinds["run_erc"] == ["connectgraph"]
