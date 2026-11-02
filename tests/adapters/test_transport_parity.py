"""TRANSPORT-PARITY — MCP/HTTP/IPC/CLI deliver one identical submit.

Every transport is a thin frame over `Engine.submit`: the same
logical call must arrive as the identical engine command, engine
errors must surface with the identical code/message, and scope
denials must agree. Cancel rides the same path on every transport.
"""

import io
import json

import pytest

from rocket_engine.adapters.errors import AdapterError
from rocket_engine.adapters.http import HttpTransport
from rocket_engine.adapters.ipc import IpcTransport
from rocket_engine.adapters.mcp import McpTransport
from rocket_engine.execution.dispatch import OpDispatcher
from rocket_engine.project.errors import ProjectError


class RecordingEngine:
    """Stand-in that records every submit and answers PASS."""

    def __init__(self):
        self.received = []

    def submit(self, command):
        self.received.append(command)
        return {"run_id": "run_parity", "state": "completed",
                "verdict": {"status": "PASS"},
                "operation": command["operation"]}


def _drive_all(received_commands):
    """Deliver the same logical call through all four transports."""
    engine = RecordingEngine()
    engine.received = received_commands
    mcp = McpTransport(engine)
    mcp.handle(json.dumps({
        "method": "tools/call",
        "params": {"name": "run_em",
                   "arguments": {"project_id": "p-parity", "x": 1}},
        "id": "r-parity",
    }))
    HttpTransport(engine).handle(json.dumps({
        "project_id": "p-parity", "operation": "run_em",
        "arguments": {"x": 1}, "request_id": "r-parity",
    }))
    IpcTransport(engine).handle(json.dumps({
        "project_id": "p-parity", "operation": "run_em",
        "arguments": {"x": 1}, "request_id": "r-parity",
    }))
    OpDispatcher(engine, project_id="p-parity").execute(
        "run_em", {"x": 1}, request_id="r-parity")


def test_submit_command_identical_across_transports():
    received = []
    _drive_all(received)
    assert len(received) == 4
    first, rest = received[0], received[1:]
    assert first == {"project_id": "p-parity", "operation": "run_em",
                     "arguments": {"x": 1}, "request_id": "r-parity"}
    assert all(command == first for command in rest)


class RefusingEngine:
    """Stand-in whose submit always fails with one engine error."""

    def submit(self, command):
        raise ProjectError("revision_conflict", "stale revision p9")


def _drive_all_against(engine):
    """Same call through all four transports; collect (code, message)."""
    outcomes = []
    calls = [
        lambda: McpTransport(engine).handle(json.dumps({
            "method": "tools/call",
            "params": {"name": "run_em",
                       "arguments": {"project_id": "p1", "x": 1}},
            "id": "r-err",
        })),
        lambda: HttpTransport(engine).handle(json.dumps({
            "project_id": "p1", "operation": "run_em",
            "arguments": {"x": 1}, "request_id": "r-err",
        })),
        lambda: IpcTransport(engine).handle(json.dumps({
            "project_id": "p1", "operation": "run_em",
            "arguments": {"x": 1}, "request_id": "r-err",
        })),
        lambda: OpDispatcher(engine, project_id="p1").execute(
            "run_em", {"x": 1}, request_id="r-err"),
    ]
    for call in calls:
        with pytest.raises(Exception) as excinfo:
            call()
        exc = excinfo.value
        outcomes.append((getattr(exc, "code", None), str(exc)))
    return outcomes


def test_engine_error_shape_identical_across_transports():
    outcomes = _drive_all_against(RefusingEngine())
    assert outcomes == [("revision_conflict", "stale revision p9")] * 4


def test_scope_denial_identical_mcp_http_ipc():
    engine = RecordingEngine()
    denials = []
    scoped = [
        McpTransport(engine, project_id="p1"),
        HttpTransport(engine, project_id="p1"),
        IpcTransport(engine, project_id="p1"),
    ]
    frames = [
        json.dumps({"method": "tools/call",
                    "params": {"name": "run_em",
                               "arguments": {"project_id": "p2"}},
                    "id": "r-scope"}),
        json.dumps({"project_id": "p2", "operation": "run_em",
                    "arguments": {}, "request_id": "r-scope"}),
        json.dumps({"project_id": "p2", "operation": "run_em",
                    "arguments": {}, "request_id": "r-scope"}),
    ]
    for transport, frame in zip(scoped, frames):
        with pytest.raises(AdapterError) as excinfo:
            transport.handle(frame)
        denials.append(excinfo.value.code)
    assert denials == ["cross_project_denied"] * 3
    assert engine.received == []


def _approved_run(engine, project_id, request_id):
    """Submit + approve a pyexec run; return its run_id (still queued)."""
    ack = engine.submit({
        "project_id": project_id,
        "operation": "python_execute",
        "arguments": {
            "mode": "lines",
            "lines": "print('cancel-me')\n",
            "expected_revision": engine.snapshot()["current_revision"],
        },
        "request_id": request_id,
    })
    engine.resolve_python_approval(ack["approval_id"], "approved")
    return ack["run_id"]


def _real_engine(tmp_path):
    from rocket_engine.composition import Engine

    proj = tmp_path / "proj"
    proj.mkdir(exist_ok=True)
    return Engine("parity-live", actor="parity", project_dir=str(proj))


def test_cancel_job_via_mcp_marks_cancelled(tmp_path):
    engine = _real_engine(tmp_path)
    run_id = _approved_run(engine, "parity-live", "parity-mcp")
    out = McpTransport(engine).handle(json.dumps({
        "method": "tools/call",
        "params": {"name": "cancel_job",
                   "arguments": {"project_id": "parity-live",
                                 "run_id": run_id}},
        "id": "parity-mcp-cancel",
    }))
    assert out["state"] == "cancelled"
    assert out["run_id"] == run_id


def test_cancel_job_via_http_marks_cancelled(tmp_path):
    engine = _real_engine(tmp_path)
    run_id = _approved_run(engine, "parity-live", "parity-http")
    out = HttpTransport(engine).handle(json.dumps({
        "project_id": "parity-live", "operation": "cancel_job",
        "arguments": {"run_id": run_id}, "request_id": "parity-http-cancel",
    }))
    assert out["state"] == "cancelled"
    assert out["run_id"] == run_id


def test_cancel_job_via_cli_marks_cancelled(tmp_path):
    from rocket_engine.adapters.cli import main

    engine = _real_engine(tmp_path)
    run_id = _approved_run(engine, "parity-live", "parity-cli")
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(["--json", "--project", "parity-live", "run", "cancel_job",
                 f"run_id={run_id}"],
                engine=engine, stdin=io.StringIO(""),
                stdout=stdout, stderr=stderr)
    assert code == 0
    envelope = json.loads(stdout.getvalue())
    assert envelope["ok"] is True
    assert envelope["result"]["state"] == "cancelled"
    assert envelope["result"]["run_id"] == run_id


class FieldedEngine:
    """Stand-in whose submit fails with code + message + fields."""

    def __init__(self):
        from rocket_engine.project.errors import ProjectError

        self.exc = ProjectError("invalid_run_param", "bad deck",
                                fields=["deck_opts"])

    def submit(self, command):
        raise self.exc


def test_error_fields_shape_per_transport():
    import json as jsonlib

    from rocket_engine.adapters.cli import main as cli_main
    from rocket_engine.adapters.mcp.server import _error as mcp_error
    from rocket_engine.adapters.stdio_console import (
        _emit_error as console_emit,
    )

    engine = FieldedEngine()
    # CLI JSON envelope carries code + message + fields.
    stdout, stderr = io.StringIO(), io.StringIO()
    code = cli_main(["--json", "run", "run_em"], engine=engine,
                    stdin=io.StringIO(""), stdout=stdout, stderr=stderr)
    assert code == 1
    envelope = jsonlib.loads(stdout.getvalue())
    assert envelope["error"] == {"code": "invalid_run_param",
                                 "message": "bad deck",
                                 "fields": ["deck_opts"]}
    # MCP wire error carries the same triple.
    wire = jsonlib.loads(mcp_error("invalid_run_param", "bad deck",
                                   ["deck_opts"]).content[0].text)
    assert wire == {"ok": False, "code": "invalid_run_param",
                    "message": "bad deck", "fields": ["deck_opts"]}
    # Console JSON error carries the same triple.
    stdout, stderr = io.StringIO(), io.StringIO()
    console_emit("run_em", engine.exc, True, stdout, stderr)
    assert jsonlib.loads(stdout.getvalue())["error"] == {
        "code": "invalid_run_param", "message": "bad deck",
        "fields": ["deck_opts"]}
    # MCP/IPC/HTTP transports propagate the coded error untouched.
    for transport in (McpTransport(engine), HttpTransport(engine),
                      IpcTransport(engine)):
        frame = {"project_id": "p1", "operation": "run_em",
                 "arguments": {"x": 1}, "request_id": "r-fields"}
        if isinstance(transport, McpTransport):
            text = jsonlib.dumps(
                {"method": "tools/call",
                 "params": {"name": "run_em",
                            "arguments": {"project_id": "p1", "x": 1}},
                 "id": "r-fields"})
        else:
            text = jsonlib.dumps(frame)
        with pytest.raises(ProjectError) as excinfo:
            transport.handle(text)
        assert excinfo.value.code == "invalid_run_param"
        assert excinfo.value.fields == ["deck_opts"]


def test_pool_full_shape_identical_across_transports():
    """PARITY leftover RED: pool_full refuses identically everywhere.

    A saturated execution backlog refuses before anything is queued;
    every transport must surface the identical code and message since
    the engine raises before any transport framing differs.
    """
    import json as jsonlib

    from rocket_engine.execution.errors import ExecutionError

    class SaturatedEngine:
        def submit(self, command):
            raise ExecutionError(
                "pool_full",
                "depth 0/0; drain (run_job) before submitting more",
            )

    outcomes = _drive_all_against(SaturatedEngine())
    assert outcomes == [
        ("pool_full",
         "depth 0/0; drain (run_job) before submitting more")
    ] * 4


def test_unknown_operation_shape_identical_across_transports():
    """PARITY leftover RED: cataloged-but-unwired refuses identically.

    run_thermal is cataloged but has no solver registered, so the
    engine raises unsupported_operation before admission on every
    transport — the same code and message, since transports pass
    cataloged names through untouched.
    """
    import json as jsonlib

    from rocket_engine.adapters.http import HttpTransport
    from rocket_engine.adapters.ipc import IpcTransport
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.composition import Engine
    from rocket_engine.execution.dispatch import OpDispatcher

    engine = Engine("parity-unknown", actor="parity")
    calls = [
        lambda: McpTransport(engine).handle(jsonlib.dumps({
            "method": "tools/call",
            "params": {"name": "run_thermal",
                       "arguments": {"project_id": "parity-unknown"}},
            "id": "r-unknown",
        })),
        lambda: HttpTransport(engine).handle(jsonlib.dumps({
            "project_id": "parity-unknown", "operation": "run_thermal",
            "arguments": {}, "request_id": "r-unknown",
        })),
        lambda: IpcTransport(engine).handle(jsonlib.dumps({
            "project_id": "parity-unknown", "operation": "run_thermal",
            "arguments": {}, "request_id": "r-unknown",
        })),
        lambda: OpDispatcher(engine, project_id="parity-unknown").execute(
            "run_thermal", {}, request_id="r-unknown"),
    ]
    outcomes = []
    for call in calls:
        with pytest.raises(Exception) as excinfo:
            call()
        outcomes.append((getattr(excinfo.value, "code", None),
                         str(excinfo.value)))
    assert outcomes[0][0] == "unsupported_operation"
    assert all(outcome == outcomes[0] for outcome in outcomes)


class _QuietSpiceAdapter:
    """Stub solver: records its job, answers PASS without tools."""

    def __init__(self):
        self.seen = []

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        self.seen.append(job)
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    def parse(self, native_output):
        return {"violations": []}


def _spice_engine(tmp_path):
    from rocket_engine.composition import Engine

    (tmp_path / "design").mkdir(exist_ok=True)
    (tmp_path / "design" / "opamp.cir").write_text("* opamp\n")
    engine = Engine("parity-spice", actor="parity",
                    project_dir=str(tmp_path))
    stub = _QuietSpiceAdapter()
    engine.register_solver("run_spice", stub, tool="ngspice")
    return engine, stub


def _submit_spice(transport_kind, engine, arguments, request_id):
    import json as jsonlib

    from rocket_engine.adapters.http import HttpTransport
    from rocket_engine.adapters.ipc import IpcTransport
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.execution.dispatch import OpDispatcher

    if transport_kind == "mcp":
        return McpTransport(engine).handle(jsonlib.dumps({
            "method": "tools/call",
            "params": {"name": "run_spice",
                       "arguments": {"project_id": "parity-spice",
                                     **arguments}},
            "id": request_id,
        }))
    if transport_kind == "http":
        return HttpTransport(engine).handle(jsonlib.dumps({
            "project_id": "parity-spice", "operation": "run_spice",
            "arguments": arguments, "request_id": request_id,
        }))
    if transport_kind == "ipc":
        return IpcTransport(engine).handle(jsonlib.dumps({
            "project_id": "parity-spice", "operation": "run_spice",
            "arguments": arguments, "request_id": request_id,
        }))
    return OpDispatcher(engine, project_id="parity-spice").execute(
        "run_spice", dict(arguments), request_id=request_id)


def test_spice_confinement_identical_across_transports(tmp_path):
    """PARITY leftover RED: run_spice confinement lives in the engine.

    Sources resolve inside the project dir and the workdir is chosen
    by the engine on every transport — not just the MCP server. A
    caller-supplied workdir is refused with the identical shape.
    """
    for kind in ("mcp", "http", "ipc", "cli"):
        engine, stub = _spice_engine(tmp_path)
        arguments = {"sources": ["design/opamp.cir"],
                     "expected_revision": "p12"}
        out = _submit_spice(kind, engine, arguments, f"r-spice-{kind}")
        assert out["state"] == "completed", kind
        assert stub.seen[0]["sources"] == [
            str(tmp_path / "design" / "opamp.cir")], kind
        assert stub.seen[0]["workdir"] == str(
            tmp_path / "results" / "engine-runs"), kind

    engine, _stub = _spice_engine(tmp_path)
    with pytest.raises(Exception) as excinfo:
        _submit_spice("http", engine,
                      {"sources": ["design/opamp.cir"],
                       "workdir": "/tmp/evil",
                       "expected_revision": "p12"}, "r-spice-evil")
    assert getattr(excinfo.value, "code", None) == "invalid_command"


def test_spice_evidence_written_beyond_mcp(tmp_path):
    """PARITY leftover RED: every transport leaves the evidence file.

    Completed solver runs land under results/engine-runs/<run_id>.json
    with the shared record shape, whoever submitted them — the MCP
    server path already did; HTTP/IPC/CLI must match.
    """
    for kind in ("mcp", "http", "ipc", "cli"):
        engine, _stub = _spice_engine(tmp_path)
        out = _submit_spice(
            kind, engine,
            {"sources": ["design/opamp.cir"], "expected_revision": "p12"},
            f"r-evidence-{kind}")
        path = (tmp_path / "results" / "engine-runs"
                / f"{out['run_id']}.json")
        assert path.is_file(), kind
        record = json.loads(path.read_text(encoding="utf-8"))
        assert record["producer"] == "rocket-engine", kind
        assert record["run_id"] == out["run_id"], kind
        assert record["operation"] == "run_spice", kind
        assert record["verdict"]["status"] == "PASS", kind
        assert record["sources"] == ["design/opamp.cir"], kind


def test_evaluate_records_exit_code_without_judging_it():
    """REVIEW-TAILS evaluate() RED: the exit code is recorded, not dropped.

    The verdict still judges findings only (exit-independent, per the
    replay law); the native exit is recorded on the run and surfaced
    by status instead of being discarded.
    """
    from rocket_engine.execution.service import ExecutionService

    service = ExecutionService("parity-exit")
    verdict = service.evaluate(
        "run_exit_001", 3, "findings:\n  - {rule: probe, severity: error}\n")
    assert verdict == {"status": "FAIL", "finding_counts": {"error": 1}}
    assert service.status("run_exit_001")["exit_code"] == 3
    unparsable = service.evaluate("run_exit_002", 0, ":::not findings:::")
    assert unparsable["status"] == "NOT_RUN"
    assert service.status("run_exit_002")["exit_code"] == 0


def test_no_host_execution_surface_on_transports():
    """REVIEW-TAILS I19 RED: host execution stays unnamed and ungated.

    No tool outside the catalog exists on the wire, and the MCP
    default-deny flag is pinned False — any future host-execution
    surface must arrive as an explicit opt-in, never a silent tool.
    """
    from rocket_engine.adapters.mcp import McpTransport
    from rocket_engine.adapters.mcp.server import tool_definitions
    from rocket_engine.interfaces.vocabulary import OPERATIONS, QUERIES

    assert McpTransport.host_execution_enabled is False
    names = {tool.name for tool in tool_definitions()}
    assert names == set(OPERATIONS | QUERIES)
    assert not {n for n in names if "host" in n or "shell" in n}


def test_v1_status_parity_with_errors_catalog():
    import json as jsonlib
    from pathlib import Path

    from rocket_engine.adapters.errors import V0_TO_V1, status_for_code

    catalog = jsonlib.loads(
        (Path(__file__).resolve().parent.parent.parent
         / "contracts" / "v1" / "catalog" / "errors.json").read_text())
    assert V0_TO_V1
    for v0, v1 in V0_TO_V1.items():
        if v1 is None:
            continue
        assert status_for_code(v0) == catalog[v1], v0
