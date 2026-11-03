"""PYTHON-EXEC RED — two modes, containment, approvals, bounds (no isolation).

Tests assume `rocket_engine.execution.python_exec` with
PythonExecService (request/resolve/run/cancel), PythonExecRunner,
resolve_script_path, parse_exception, build_worker_source, and
MCP_INPUT_SCHEMA. Valid RED = the import itself fails.

No worker isolation needed: service tests inject fake runners and
dispatchers; live workers are covered in test_python_exec_live.py.
"""

import hashlib
import json

import pytest


def _mod():
    from rocket_engine.execution import python_exec  # RED: missing module

    return python_exec


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


class _FakeRunner:
    """Runner double: canned terminal records, spawn counting."""

    def __init__(self, record=None):
        self._record = dict(record or {})
        self.spawns = 0
        self.seen = []

    @property
    def admission(self):
        return {"admitted": True, "reason": None, "network_isolated": False}

    def run(self, source, run_id=None, timeout_s=None, artifacts=(),
            extra_env=None, on_live=None, is_cancelled=None,
            cell_name="cell.py", cell_line_offset=0):
        self.spawns += 1
        self.seen.append({"timeout_s": timeout_s, "artifacts": tuple(artifacts)})
        if on_live is not None:
            on_live(run_id, "fake-token")
        record = {
            "run_id": run_id or "fake-run",
            "state": "completed",
            "ok": True,
            "reason": None,
            "exit_code": 0,
            "stdout": "fake-ok\n",
            "stderr": "",
            "partial": False,
            "artifacts": [],
            "rejected_artifacts": [],
            "network_isolated": False,
            "credential_revoked": True,
            "tree_killed": True,
            "exception": None,
            "spawned": True,
        }
        record.update(self._record)
        return record


class _FakeDispatcher:
    """Dispatch double: canned op results, call recording."""

    def __init__(self, results=None):
        self._results = dict(results or {})
        self.calls = []

    def execute(self, operation, arguments):
        self.calls.append((operation, dict(arguments)))
        if operation in self._results:
            return self._results[operation]
        return {"state": "recorded", "operation": operation}


def _service(tmp_path, mod=None, **kwargs):
    mod = mod or _mod()
    from rocket_engine.execution.service import ExecutionService

    kwargs.setdefault("execution", ExecutionService("pyexec-probe"))
    kwargs.setdefault("runner", _FakeRunner())
    return mod.PythonExecService(
        "pyexec-probe", actor="probe-agent", root=str(tmp_path / "pyexec"),
        **kwargs,
    )


# --- Module surface ---

def test_module_surface_exists():
    mod = _mod()
    assert callable(mod.PythonExecService)
    assert callable(mod.PythonExecRunner)
    assert callable(mod.resolve_script_path)
    assert callable(mod.parse_exception)
    assert callable(mod.build_worker_source)
    assert isinstance(mod.MCP_INPUT_SCHEMA, dict)
    assert isinstance(mod.PRELUDE_DIGEST, str)


def test_modes_are_exactly_lines_and_path():
    mod = _mod()
    assert mod.MODES == ("lines", "path")


# --- Mode validation ---

def test_request_lines_ok_and_persists_exact_bytes(tmp_path):
    mod = _mod()
    service = _service(tmp_path)
    code = "print('pyexec-lines')\n"
    handle = service.request_execution("lines", lines=code, request_id="r1")
    assert handle["approval_state"] == "pending_approval"
    assert handle["mode"] == "lines"
    assert handle["request_id"] == "r1"
    assert handle["code_sha256"] == hashlib.sha256(code.encode()).hexdigest()
    cell = tmp_path / "pyexec" / "cells" / (handle["execution_id"] + ".py")
    assert cell.read_text(encoding="utf-8") == code


def test_request_path_ok_and_records_source(tmp_path):
    mod = _mod()
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "analysis").mkdir()
    script = proj / "analysis" / "fit.py"
    script.write_text("print('pyexec-path')\n", encoding="utf-8")
    service = _service(tmp_path, project_root=str(proj))
    handle = service.request_execution(
        "path", path="analysis/fit.py", request_id="r1"
    )
    assert handle["approval_state"] == "pending_approval"
    assert handle["mode"] == "path"
    assert handle["source_file"] == "analysis/fit.py"


def test_request_rejects_both_modes_and_neither_and_bad_mode(tmp_path):
    service = _service(tmp_path, project_root=str(tmp_path))
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines", lines="x=1\n", path="a.py")
    assert _code(excinfo) == "invalid_command"
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines")
    assert _code(excinfo) == "invalid_command"
    with pytest.raises(Exception) as excinfo:
        service.request_execution("path", lines="x=1\n")
    assert _code(excinfo) == "invalid_command"
    with pytest.raises(Exception) as excinfo:
        service.request_execution("shell", lines="x=1\n")
    assert _code(excinfo) == "invalid_command"


def test_request_rejects_empty_nontext_oversize_lines(tmp_path):
    mod = _mod()
    service = _service(tmp_path)
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines", lines="  \n")
    assert _code(excinfo) == "empty_cell"
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines", lines=b"x=1\n")
    assert _code(excinfo) == "invalid_cell"
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines", lines="x\n" * (mod.MAX_LINES_BYTES // 2 + 1))
    assert _code(excinfo) == "invalid_command"


# --- Path containment ---

def test_path_traversal_rejected_loudly(tmp_path):
    service = _service(tmp_path, project_root=str(tmp_path / "proj"))
    (tmp_path / "proj").mkdir()
    for evil in ("../escape.py", "a/../../escape.py", "/etc/hostname",
                 "C:/evil.py", ".."):
        with pytest.raises(Exception) as excinfo:
            service.request_execution("path", path=evil)
        assert _code(excinfo) == "path_escape", evil


def test_path_symlink_escape_rejected(tmp_path):
    mod = _mod()
    proj = tmp_path / "proj"
    proj.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    (proj / "link.py").symlink_to(outside)
    with pytest.raises(Exception) as excinfo:
        mod.resolve_script_path(str(proj), "link.py")
    assert _code(excinfo) == "path_escape"


def test_path_missing_and_directory_rejected(tmp_path):
    mod = _mod()
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "adir").mkdir()
    with pytest.raises(Exception) as excinfo:
        mod.resolve_script_path(str(proj), "nope.py")
    assert _code(excinfo) == "invalid_path"
    with pytest.raises(Exception) as excinfo:
        mod.resolve_script_path(str(proj), "adir")
    assert _code(excinfo) == "invalid_path"


def test_path_mode_without_project_root_rejected(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(Exception) as excinfo:
        service.request_execution("path", path="a.py")
    assert _code(excinfo) == "invalid_command"


# --- Approvals distinct from job state ---

def test_pending_approval_creates_no_run(tmp_path):
    from rocket_engine.execution.errors import ExecutionError

    service = _service(tmp_path)
    handle = service.request_execution("lines", lines="x=1\n")
    assert handle["approval_state"] == "pending_approval"
    assert "run_id" not in handle
    status = service.approval_status(handle["approval_id"])
    assert status["approval_state"] == "pending_approval"
    assert status.get("run_id") is None
    with pytest.raises(ExecutionError) as excinfo:
        service.status("never-admitted")
    assert _code(excinfo) == "unknown_run"


def test_agent_cannot_self_approve(tmp_path):
    service = _service(tmp_path)
    handle = service.request_execution("lines", lines="x=1\n")
    for via in ("mcp", "agent", "tool", ""):
        with pytest.raises(Exception) as excinfo:
            service.resolve_approval(handle["approval_id"], "approved", via=via)
        assert _code(excinfo) == "approval_forbidden", via
    assert service.approval_status(handle["approval_id"])["approval_state"] == "pending_approval"


def test_denied_stays_distinct_and_creates_no_run(tmp_path):
    service = _service(tmp_path)
    handle = service.request_execution("lines", lines="x=1\n")
    out = service.resolve_approval(handle["approval_id"], "denied", via="ui")
    assert out["approval_state"] == "denied"
    assert "run_id" not in out
    assert service.approval_status(handle["approval_id"])["approval_state"] == "denied"
    with pytest.raises(Exception) as excinfo:
        service.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert _code(excinfo) == "approval_denied"


def test_expired_approval_creates_no_run(tmp_path):
    mod = _mod()
    clock = [1000.0]
    service = _service(
        tmp_path, approval_ttl_s=10, clock=lambda: clock[0],
    )
    handle = service.request_execution("lines", lines="x=1\n")
    clock[0] += 11.0
    assert service.approval_status(handle["approval_id"])["approval_state"] == "expired"
    with pytest.raises(Exception) as excinfo:
        service.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert _code(excinfo) == "approval_expired"


def test_approved_admits_one_queued_run(tmp_path):
    service = _service(tmp_path)
    handle = service.request_execution("lines", lines="x=1\n")
    out = service.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert out["approval_state"] == "approved"
    assert out["run_id"]
    assert service.status(out["run_id"])["state"] == "queued"


def test_history_drift_invalidates_approval(tmp_path):
    service = _service(tmp_path)
    first = service.request_execution("lines", lines="a=1\n", request_id="a")
    second = service.request_execution("lines", lines="b=2\n", request_id="b")
    admitted = service.resolve_approval(first["approval_id"], "approved", via="ui")
    service.run_job(admitted["run_id"])
    with pytest.raises(Exception) as excinfo:
        service.resolve_approval(second["approval_id"], "approved", via="ui")
    assert _code(excinfo) == "approval_invalid"


def test_request_id_replay_and_conflict(tmp_path):
    service = _service(tmp_path)
    first = service.request_execution("lines", lines="x=1\n", request_id="same")
    replay = service.request_execution("lines", lines="x=1\n", request_id="same")
    assert replay["execution_id"] == first["execution_id"]
    assert replay["approval_id"] == first["approval_id"]
    with pytest.raises(Exception) as excinfo:
        service.request_execution("lines", lines="x=2\n", request_id="same")
    assert _code(excinfo) == "request_conflict"


# --- Engine-shared run ids and console view ---

def test_submit_time_run_id_shared_across_phases(tmp_path):
    service = _service(tmp_path)
    handle = service.request_execution(
        "lines", lines="x=1\n", run_id="shared-1",
    )
    assert handle["run_id"] == "shared-1"
    with pytest.raises(Exception) as excinfo:
        service.run_job("shared-1")
    assert _code(excinfo) == "approval_pending"
    admitted = service.resolve_approval(
        handle["approval_id"], "approved", via="ui",
    )
    assert admitted["run_id"] == "shared-1"
    record = service.run_job("shared-1")
    assert record["run_id"] == "shared-1"


def test_console_view_reads_generation_and_pending(tmp_path):
    service = _service(tmp_path)
    view = service.console_view()
    assert view["generation"] == service.generation
    assert view["pending_approvals"] == 0
    service.request_execution("lines", lines="x=1\n", request_id="v1")
    assert service.console_view()["pending_approvals"] == 1


def test_validate_request_is_pure_and_shared(tmp_path):
    service = _service(tmp_path)
    display, source, budget, names = service.validate_request(
        "lines", lines="x=1", artifacts=("a.txt",), timeout_s=30,
    )
    assert (display, source, budget, names) == ("x=1\n", None, 30, ["a.txt"])
    assert service.cursor == 0
    assert list((tmp_path / "pyexec" / "cells").glob("*.py")) == []
    with pytest.raises(Exception) as excinfo:
        service.validate_request("lines")
    assert _code(excinfo) == "invalid_command"


def test_revision_provider_drift_fails_closed(tmp_path):
    service = _service(tmp_path, revision_provider=lambda: "p13")
    handle = service.request_execution(
        "lines", lines="x=1\n", expected_revision="p12",
    )
    with pytest.raises(Exception) as excinfo:
        service.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert _code(excinfo) == "approval_invalid"
    pinned = _service(tmp_path, revision_provider=lambda: "p12")
    handle = pinned.request_execution(
        "lines", lines="x=1\n", expected_revision="p12",
    )
    out = pinned.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert out["approval_state"] == "approved"


# --- Timeouts, cancellation, reset ---

def test_timeout_bounds(tmp_path):
    mod = _mod()
    assert mod.DEFAULT_TIMEOUT_S == 120
    service = _service(tmp_path)
    for bad in (0, -5, mod.MAX_TIMEOUT_S + 1, "30", 2.5):
        with pytest.raises(Exception) as excinfo:
            service.request_execution("lines", lines="x=1\n", timeout_s=bad)
        assert _code(excinfo) == "invalid_command", bad
    handle = service.request_execution("lines", lines="x=1\n", timeout_s=30)
    assert handle["timeout_s"] == 30


def test_cancel_before_run_never_spawns(tmp_path):
    runner = _FakeRunner()
    service = _service(tmp_path, runner=runner)
    handle = service.request_execution("lines", lines="x=1\n")
    admitted = service.resolve_approval(handle["approval_id"], "approved", via="ui")
    assert service.cancel(admitted["run_id"])["state"] == "cancelled"
    record = service.run_job(admitted["run_id"])
    assert record["state"] == "cancelled"
    assert record["spawned"] is False
    assert runner.spawns == 0


def test_cancel_unknown_run_raises(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(Exception) as excinfo:
        service.cancel("no-such-run")
    assert _code(excinfo) == "unknown_run"


def test_reset_retires_generation_expires_pending_cancels_queued(tmp_path):
    service = _service(tmp_path)
    before = service.generation
    pending = service.request_execution("lines", lines="a=1\n", request_id="a")
    queued = service.request_execution("lines", lines="b=2\n", request_id="b")
    admitted = service.resolve_approval(queued["approval_id"], "approved", via="ui")
    out = service.reset()
    assert out["generation"] != before
    assert service.generation == out["generation"]
    assert service.approval_status(pending["approval_id"])["approval_state"] == "expired"
    assert service.status(admitted["run_id"])["state"] == "cancelled"


# --- Exceptions, verdicts, prelude ---

TRACEBACK = """\
Traceback (most recent call last):
  File "cell.py", line 9, in <module>
    fit(data)
  File "cell.py", line 5, in fit
    raise ValueError('bad curve')
ValueError: bad curve
"""


def test_parse_exception_reports_cell_location():
    mod = _mod()
    parsed = mod.parse_exception(TRACEBACK)
    assert parsed["type"] == "ValueError"
    assert "bad curve" in parsed["message"]
    assert parsed["location"] == "cell.py:5 in fit"
    assert [f["line"] for f in parsed["frames"] if f["in_cell"]] == [9, 5]


def test_parse_exception_none_without_traceback():
    mod = _mod()
    assert mod.parse_exception("all good\n") is None
    assert mod.parse_exception("") is None


def test_zero_exit_never_pass(tmp_path):
    mod = _mod()
    assert mod.not_run_verdict("probe")["status"] == "NOT_RUN"
    service = _service(tmp_path)
    handle = service.request_execution("lines", lines="x=1\n")
    admitted = service.resolve_approval(handle["approval_id"], "approved", via="ui")
    record = service.run_job(admitted["run_id"])
    assert record["ok"] is True
    assert record["exit_code"] == 0
    assert record["verdict"]["status"] == "NOT_RUN"
    assert service.status(admitted["run_id"])["verdict"]["status"] == "NOT_RUN"


def test_prelude_pinned_and_verbatim():
    mod = _mod()
    assert mod.PRELUDE_DIGEST == hashlib.sha256(
        mod.PRELUDE_TEMPLATE.encode("utf-8")).hexdigest()
    code = "print('@PROJECT_ID@')\n"
    source = mod.build_worker_source(code, project_id="demo")
    assert source.endswith(code)
    assert '"demo"' in source.split(code)[0]


# --- Effects replay ---

def test_effects_replay_collects_run_ids(tmp_path):
    mod = _mod()
    ops_log = tmp_path / "ops.jsonl"
    ops_log.write_text(
        json.dumps({"operation": "run_em", "arguments": {"cell": "amp"}}) + "\n"
        + "not-json\n"
        + json.dumps({"operation": "write_doc", "arguments": {"path": "d.md"}}) + "\n",
        encoding="utf-8",
    )
    runner = _FakeRunner(record={
        "artifacts": [{"name": mod.OPS_LOG_NAME, "path": str(ops_log)}],
    })
    dispatcher = _FakeDispatcher(results={
        "run_em": {"run_id": "child-1", "state": "completed"},
        "write_doc": {"new_revision": "p13", "events": [{"seq": 4}]},
    })
    service = _service(tmp_path, runner=runner, dispatcher=dispatcher)
    handle = service.request_execution("lines", lines="x=1\n")
    admitted = service.resolve_approval(handle["approval_id"], "approved", via="ui")
    record = service.run_job(admitted["run_id"])
    assert record["effects"]["run_ids"] == ["child-1"]
    assert record["effects"]["ops_ok"] is True
    assert record["effects"]["ops_skipped"] == 1
    assert [c[0] for c in dispatcher.calls] == ["run_em", "write_doc"]


def test_unreplayed_ops_marked_not_ok(tmp_path):
    mod = _mod()
    ops_log = tmp_path / "ops.jsonl"
    ops_log.write_text(
        json.dumps({"operation": "run_em", "arguments": {}}) + "\n",
        encoding="utf-8",
    )
    runner = _FakeRunner(record={
        "artifacts": [{"name": mod.OPS_LOG_NAME, "path": str(ops_log)}],
    })
    service = _service(tmp_path, runner=runner, dispatcher=None)
    handle = service.request_execution("lines", lines="x=1\n")
    admitted = service.resolve_approval(handle["approval_id"], "approved", via="ui")
    record = service.run_job(admitted["run_id"])
    assert record["effects"]["replayed"] is False
    assert record["effects"]["ops_ok"] is False
    assert len(record["effects"]["ops"]) == 1


# --- MCP input schema ---

def test_mcp_schema_mode_oneof_with_bounds():
    import jsonschema

    mod = _mod()
    schema = mod.MCP_INPUT_SCHEMA
    assert schema["type"] == "object"
    assert schema["required"] == ["mode"]
    assert len(schema["oneOf"]) == 2
    jsonschema.validate({"mode": "lines", "lines": "x=1\n"}, schema)
    jsonschema.validate({"mode": "path", "path": "a.py"}, schema)
    for bad in ({"mode": "lines"}, {"mode": "path"},
                {"mode": "lines", "lines": "x", "path": "a.py"},
                {"mode": "lines", "path": "a.py"},
                {"mode": "path", "lines": "x"},
                {"mode": "shell", "lines": "x"},
                {"lines": "x=1\n"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"mode": "lines", "lines": "x" * (mod.MAX_LINES_BYTES + 1)}, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {"mode": "lines", "lines": "x", "timeout_s": mod.MAX_TIMEOUT_S + 1},
            schema)
    props = schema["properties"]
    assert props["mode"]["enum"] == ["lines", "path"]
    assert props["timeout_s"]["minimum"] == 1
