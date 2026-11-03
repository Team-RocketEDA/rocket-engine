"""PYTHON-EXEC wiring — integrator-run AFTER the wiring patch lands.

These tests prove the Engine API + MCP tool + contract wiring the
integrator applies from docs/work/PYTHON-EXEC/wiring.patch. Before
the patch they skip loudly (python_execute unwired); after it they
run the full submit -> approve -> run_job -> status loop through
the real Engine, the MCP tool schema, and the regenerated contract
artifacts.

Run (post-patch, from the repo root):
    PYTHONPATH=/tmp/pyexec_rocket MPLCONFIGDIR=/tmp/mplcfg \
        .venv/bin/python -m pytest tests/execution/test_python_exec_wiring.py
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def _wired():
    """True once the integrator's wiring patch wires python_execute."""
    from rocket_engine.composition import Engine
    from rocket_engine.project.errors import ProjectError

    engine = Engine("wiring-probe", actor="wiring-probe")
    try:
        engine.submit({
            "project_id": "wiring-probe",
            "operation": "python_execute",
            "arguments": {},
            "request_id": "probe-python-execute",
        })
    except ProjectError as exc:
        return exc.code != "unsupported_operation"
    except Exception:
        return True
    return True


@pytest.fixture
def engine(tmp_path):
    if not _wired():
        pytest.skip("wiring patch not applied: python_execute unwired")
    from rocket_engine.composition import Engine

    proj = tmp_path / "proj"
    proj.mkdir()
    return Engine("wiring-live", actor="wiring-agent", project_dir=str(proj))


def test_submit_returns_approval_handle_not_a_run(engine):
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('wired')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-1",
    })
    assert ack["approval_state"] == "pending_approval"
    assert ack["approval_id"]
    assert ack["execution_id"]
    assert ack["run_id"]


def test_run_job_before_approval_refuses_without_running(engine):
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('too-early')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-early",
    })
    from rocket_engine.execution.errors import ExecutionError

    with pytest.raises(ExecutionError) as excinfo:
        engine.submit({
            "project_id": "wiring-live",
            "operation": "run_job",
            "arguments": {"run_id": ack["run_id"]},
            "request_id": "wire-early-run",
        })
    assert excinfo.value.code == "approval_pending"


def test_full_loop_marks_not_run_never_pass(engine):
    from rocket_engine.execution.worker import CellRunner

    host = CellRunner()
    if not host.admission["admitted"]:
        pytest.skip("no provable worker isolation")
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('wired-loop')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-loop",
    })
    resolved = engine.resolve_python_approval(
        ack["approval_id"], "approved", actor="wiring-human",
    )
    assert resolved["approval_state"] == "approved"
    assert resolved["run_id"] == ack["run_id"]
    assert engine.job_status(ack["run_id"])["state"] == "queued"
    done = engine.submit({
        "project_id": "wiring-live",
        "operation": "run_job",
        "arguments": {"run_id": ack["run_id"]},
        "request_id": "wire-loop-run",
    })
    assert done["state"] == "completed"
    assert done["verdict"]["status"] == "NOT_RUN"
    assert engine.job_status(ack["run_id"])["verdict"]["status"] == "NOT_RUN"
    page = engine.submit({
        "project_id": "wiring-live",
        "operation": "get_logs",
        "arguments": {"run_id": ack["run_id"]},
        "request_id": "wire-loop-logs",
    })
    assert "wired-loop" in "\n".join(page["lines"])


def test_cancel_job_marks_cancelled(engine):
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('cancel-me')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-cancel",
    })
    engine.resolve_python_approval(ack["approval_id"], "approved")
    assert engine.cancel_job(ack["run_id"])["state"] == "cancelled"


def test_cancel_job_via_submit_marks_cancelled(engine):
    from rocket_engine.composition import OPERATIONS

    assert "cancel_job" in OPERATIONS
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('cancel-via-submit')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-cancel-submit",
    })
    engine.resolve_python_approval(ack["approval_id"], "approved")
    out = engine.submit({
        "project_id": "wiring-live",
        "operation": "cancel_job",
        "arguments": {"run_id": ack["run_id"]},
        "request_id": "wire-cancel-submit-2",
    })
    assert out["state"] == "cancelled"
    assert out["run_id"] == ack["run_id"]
    assert engine.job_status(ack["run_id"])["state"] == "cancelled"


def test_cancel_job_via_submit_unknown_run(engine):
    from rocket_engine.execution import ExecutionError

    with pytest.raises(ExecutionError) as excinfo:
        engine.submit({
            "project_id": "wiring-live",
            "operation": "cancel_job",
            "arguments": {"run_id": "run_never_admitted"},
            "request_id": "wire-cancel-unknown",
        })
    assert excinfo.value.code == "unknown_run"


def test_cancel_job_via_submit_mid_run_kills_tree(engine):
    import threading
    import time

    from rocket_engine.execution.worker import CellRunner

    if not CellRunner().admission["admitted"]:
        pytest.skip("no provable worker isolation")
    ack = engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "import time\ntime.sleep(30)\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-cancel-midrun",
    })
    engine.resolve_python_approval(ack["approval_id"], "approved")
    run_id = ack["run_id"]
    outcome = {}

    def _drain():
        try:
            outcome["result"] = engine.submit({
                "project_id": "wiring-live",
                "operation": "run_job",
                "arguments": {"run_id": run_id},
                "request_id": "wire-cancel-midrun-drain",
            })
        except Exception as exc:  # record, never lose the thread
            outcome["error"] = exc

    worker = threading.Thread(target=_drain, daemon=True)
    worker.start()
    deadline = time.time() + 15
    while engine.job_status(run_id)["state"] != "running":
        assert time.time() < deadline, "run never reached running"
        time.sleep(0.05)
    out = engine.submit({
        "project_id": "wiring-live",
        "operation": "cancel_job",
        "arguments": {"run_id": run_id},
        "request_id": "wire-cancel-midrun-cancel",
    })
    assert out["state"] == "cancelled"
    worker.join(timeout=30)
    assert not worker.is_alive(), "drain thread stuck after cancel"
    assert "error" not in outcome, outcome.get("error")
    assert engine.job_status(run_id)["state"] == "cancelled"


def test_console_query_reads_generation_and_cells(engine):
    engine.submit({
        "project_id": "wiring-live",
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('query-me')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": "wire-query",
    })
    view = engine.submit({
        "project_id": "wiring-live",
        "operation": "get_python_console",
        "arguments": {},
        "request_id": "wire-query-read",
    })
    assert view["generation"]
    assert view["pending_approvals"] >= 1


def test_mcp_tool_schema_is_real_oneof():
    from rocket_engine.adapters.mcp.server import tool_definitions
    from rocket_engine.execution.python_exec import MCP_INPUT_SCHEMA

    tools = {tool.name: tool for tool in tool_definitions()}
    schema = tools["python_execute"].input_schema
    if schema == {"type": "object"}:
        pytest.skip("wiring patch not applied: generic MCP schema")
    assert schema == MCP_INPUT_SCHEMA
    assert len(schema["oneOf"]) == 2


def test_regenerated_contract_marks_python_execute_wired():
    schemas = json.loads((ROOT / "docs" / "api-schema.json").read_text())
    entry = schemas["operations"]["python_execute"]
    if entry["wired"] is not True:
        pytest.skip("contract not regenerated after wiring")
    assert entry["properties"], "wired schema carries real properties"
    contract = json.loads((ROOT / "docs" / "contract.json").read_text())
    assert contract["operations"]["python_execute"]["wired"] is True
