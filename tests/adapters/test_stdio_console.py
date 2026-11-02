"""STDIO-CONSOLE RED — MATLAB-esque script console, stdio-only.

The console is a REPL gateway onto the SHARED op dispatch from
CLI-DISPATCH (same calls, interactive framing): every cell compiles
to the same op calls the batch CLI runs, replayable as CLI scripts.
Cells execute in fresh WORKERS workers with prebounds available and
zero setup; history persists as cells/*.py + executions/*.yaml; one
console per panel (no tabs). Approval flow is reused from
console.py: a human Run approves the exact displayed cell.

Valid RED = each import fails: the adapter does not exist yet.
Live tests use the `live_console` fixture, which skips loudly unless
a provable bwrap + in-sandbox python3 admit workers — same I16 rule
as the WORKERS suite. Framing/history/trust tests run everywhere via
a fake runner; the not_run path uses a provably broken CellRunner.

Local-only trust: stdio + OS identity, no tokens, no network. The
trust tests assert that boundary from the module source itself.
"""

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

CONSOLE_SRC = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "adapters" / "stdio_console.py"
)


def _console():
    from rocket_engine.adapters import stdio_console  # RED: missing adapter

    return stdio_console


class FakeEngine:
    """Deterministic stand-in: PASS for runs, queued for submits."""

    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.append(("run", command))
        return {"run_id": "run_fake", "state": "completed",
                "verdict": {"status": "PASS"},
                "operation": command["operation"]}

    def submit(self, command):
        self.commands.append(("submit", command))
        return {"state": "queued", "run_id": "run_fake_q"}


class FakeRunner:
    """Stand-in worker: real approval binding, canned worker record."""

    def __init__(self, tmp_path, stdout="fake-out\n", ops=(), state="completed"):
        self._tmp = Path(tmp_path)
        self._stdout = stdout
        self._ops = list(ops)
        self._state = state
        self.calls = []

    @property
    def admission(self):
        return {"admitted": True, "reason": None, "network_isolated": False}

    def run_cell(self, session, approval_id, code, history_cursor,
                 env_digest, expected_revision, artifacts=(), timeout_s=None,
                 on_live=None):
        session.admit_cell(  # real binding: tamper raises approval_invalid
            approval_id, code=code, history_cursor=history_cursor,
            env_digest=env_digest, expected_revision=expected_revision,
        )
        if on_live is not None:
            on_live("run_fake", "token_fake")
        self.calls.append({"code": code, "history_cursor": history_cursor,
                           "env_digest": env_digest,
                           "expected_revision": expected_revision,
                           "artifacts": tuple(artifacts),
                           "timeout_s": timeout_s})
        harvested = []
        if self._ops:
            ops_file = self._tmp / "fake_harvest.jsonl"
            ops_file.write_text(
                "".join(json.dumps(op) + "\n" for op in self._ops),
                encoding="utf-8",
            )
            harvested.append({"name": "__console_ops.jsonl",
                              "path": str(ops_file),
                              "bytes": ops_file.stat().st_size,
                              "sha256": "0" * 64})
        return {"run_id": "run_fake", "state": self._state,
                "ok": self._state == "completed", "reason": None,
                "exit_code": 0 if self._state == "completed" else 3,
                "stdout": self._stdout, "stderr": "", "partial": False,
                "artifacts": harvested, "rejected_artifacts": [],
                "network_isolated": False, "credential_revoked": True,
                "tree_killed": True, "scratch": str(self._tmp)}


def _open(engine=None, tmp_path=None, **kwargs):
    mod = _console()
    return mod.StdioConsole(
        engine=engine or FakeEngine(), root=str(tmp_path), **kwargs
    )


@pytest.fixture
def live_console(tmp_path):
    mod = _console()
    console = mod.StdioConsole(
        engine=FakeEngine(), project_id="console_probe",
        root=str(tmp_path / "console"),
    )
    if not console.admission["admitted"]:
        console.close()
        pytest.skip(
            f"no provable worker isolation: {console.admission.get('reason')}"
        )
    yield console
    console.close()


# --- Module shape: prebounds, trust, cell compiler ---

def test_module_shape_prebounds_and_trust():
    mod = _console()  # RED: missing adapter
    assert mod.PREBOUND_NAMES == ("project", "tools", "pdk", "gf", "np", "plot")
    assert mod.LOCAL_ONLY_TRUST is True
    assert isinstance(mod.TRUST_NOTE, str) and mod.TRUST_NOTE.strip()
    assert mod.OPS_LOG_NAME == "__console_ops.jsonl"
    assert isinstance(mod.CELL_PRELUDE_TEMPLATE, str)
    assert "@PROJECT_ID@" in mod.CELL_PRELUDE_TEMPLATE
    assert mod.PRELUDE_DIGEST == hashlib.sha256(
        mod.CELL_PRELUDE_TEMPLATE.encode()
    ).hexdigest()
    assert callable(mod.StdioConsole)
    assert callable(mod.build_cell_source)
    assert callable(mod.format_op_call)
    assert callable(mod.main)


def test_build_cell_source_binds_project_without_touching_display():
    mod = _console()
    display = 'print("@PROJECT_ID@ is data, not a slot")\n'
    first = mod.build_cell_source(display, project_id="p1")
    second = mod.build_cell_source(display, project_id="p2")
    assert first.endswith(display)
    assert second.endswith(display)
    assert first != second
    for name in mod.PREBOUND_NAMES:
        assert name in first


def test_format_op_call_single_arg_matches_cli_style():
    mod = _console()
    assert mod.format_op_call("run_em", {"x": 1}) == "run_em x=1"
    assert mod.format_op_call("get_project_snapshot", {}) == (
        "get_project_snapshot"
    )


@pytest.mark.parametrize("operation,arguments", [
    ("run_em", {"x": 1}),
    ("run_drc", {"tech": "synthetic-kl", "deck": {"tool": "klayout"},
                 "note": "a b"}),
    ("run_drc", {"benches": ["ac", "tran"], "fast": True, "timeout_s": 30}),
    ("run_em", {"note": 'say "hi"'}),
    ("get_project_snapshot", {}),
])
def test_format_op_call_round_trips_through_shared_parser(
    operation, arguments
):
    from rocket_engine.execution.dispatch import parse_op_call

    mod = _console()
    line = mod.format_op_call(operation, arguments)
    assert parse_op_call(line) == (operation, arguments)


# --- Framing + history (fake runner: runs everywhere) ---

def test_submit_persists_exact_cell_and_execution(tmp_path):
    console = _open(tmp_path=tmp_path / "c1",
                    cell_runner=FakeRunner(tmp_path, stdout="hi-out\n"))
    try:
        code = "print('hi')\n"
        record = console.submit(code)
        assert record["state"] == "completed"
        assert record["ok"] is True
        assert record["stdout"] == "hi-out\n"
        assert record["history_cursor"] == 1
        root = Path(console.root)
        assert (root / record["cell"]).read_text() == code
        assert record["code_sha256"] == hashlib.sha256(
            code.encode()
        ).hexdigest()
        assert (root / "executions" / f"{record['execution_id']}.yaml"
                ).is_file()
        assert (root / "console.yaml").is_file()
        assert console.cursor == 1
    finally:
        console.close()


def test_multiline_cell_reaches_worker_verbatim_with_prebounds(tmp_path):
    runner = FakeRunner(tmp_path)
    console = _open(tmp_path=tmp_path / "c2", cell_runner=runner)
    try:
        code = (
            "def quad(x):\n"
            "    return 2 * x\n"
            "for i in range(3):\n"
            "    print(quad(i))\n"
        )
        console.submit(code, timeout_s=5)
        assert len(runner.calls) == 1
        call = runner.calls[0]
        assert call["code"].endswith(code)
        assert call["timeout_s"] == 5
        for name in ("project", "tools", "pdk", "gf", "np", "plot"):
            assert name in call["code"]
    finally:
        console.close()


def test_every_cell_harvests_the_ops_log(tmp_path):
    runner = FakeRunner(tmp_path)
    console = _open(tmp_path=tmp_path / "c3", cell_runner=runner)
    try:
        console.submit("print(1)\n")
        assert "__console_ops.jsonl" in runner.calls[0]["artifacts"]
    finally:
        console.close()


def test_history_survives_restart(tmp_path):
    root = str(tmp_path / "c4")
    first = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    try:
        first.submit("print('one')\n")
        first.submit("print('two')\n")
        assert [h["history_cursor"] for h in first.history()] == [1, 2]
        console_id = first.console_id
        generation = first.generation
    finally:
        first.close()
    second = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    try:
        assert second.console_id == console_id
        assert second.generation == generation
        assert [h["history_cursor"] for h in second.history()] == [1, 2]
        record = second.submit("print('three')\n")
        assert record["history_cursor"] == 3
        assert len(second.history()) == 3
    finally:
        second.close()


def test_script_file_cell_binds_persisted_copy(tmp_path):
    script = tmp_path / "job.py"
    script.write_text("print('from-file')\n", encoding="utf-8")
    runner = FakeRunner(tmp_path)
    console = _open(tmp_path=tmp_path / "c5", cell_runner=runner)
    try:
        record = console.submit_file(str(script))
        assert record["state"] == "completed"
        assert record["source_file"] == str(script)
        root = Path(console.root)
        assert (root / record["cell"]).read_text() == "print('from-file')\n"
        assert runner.calls[0]["code"].endswith("print('from-file')\n")
    finally:
        console.close()


def test_script_file_missing_is_usage_error(tmp_path):
    console = _open(tmp_path=tmp_path / "c6",
                    cell_runner=FakeRunner(tmp_path))
    try:
        with pytest.raises(Exception) as excinfo:
            console.submit_file(str(tmp_path / "nope.py"))
        assert getattr(excinfo.value, "code", None) == "cell_unreadable"
    finally:
        console.close()


def test_empty_cell_rejected(tmp_path):
    console = _open(tmp_path=tmp_path / "c7",
                    cell_runner=FakeRunner(tmp_path))
    try:
        with pytest.raises(Exception) as excinfo:
            console.submit("  \n")
        assert getattr(excinfo.value, "code", None) == "empty_cell"
    finally:
        console.close()


# --- Shared dispatch: same calls the batch CLI runs ---

def test_cell_ops_replay_through_shared_dispatch(tmp_path):
    from rocket_engine.execution.dispatch import parse_op_call

    ops = [{"operation": "run_em", "arguments": {"x": 1}},
           {"operation": "get_project_snapshot", "arguments": {}}]
    engine = FakeEngine()
    console = _open(tmp_path=tmp_path / "c8",
                    cell_runner=FakeRunner(tmp_path, ops=ops), engine=engine)
    try:
        record = console.submit("tools.run_em(x=1)\n")
        assert record["ops"] == ops
        assert [r["operation"] for r in record["op_results"]] == [
            "run_em", "get_project_snapshot"]
        assert all(r["ok"] for r in record["op_results"])
        assert record["ops_ok"] is True
        assert engine.commands[0][0] == "submit"
        assert engine.commands[0][1]["operation"] == "run_em"
        assert engine.commands[0][1]["arguments"] == {"x": 1}
        assert engine.commands[1][0] == "submit"
        assert len(record["cli_script"]) == 2
        for line, op in zip(record["cli_script"], ops):
            assert parse_op_call(line) == (op["operation"], op["arguments"])
    finally:
        console.close()


def test_unknown_op_in_cell_is_truthful_per_op_error(tmp_path):
    ops = [{"operation": "frobnicate", "arguments": {}}]
    engine = FakeEngine()
    console = _open(tmp_path=tmp_path / "c9",
                    cell_runner=FakeRunner(tmp_path, ops=ops), engine=engine)
    try:
        record = console.submit("tools.frobnicate()\n")
        assert record["ok"] is True  # the worker itself ran fine
        assert record["ops_ok"] is False
        assert record["op_results"][0]["ok"] is False
        assert record["op_results"][0]["error"]["code"] == (
            "unsupported_operation"
        )
        assert engine.commands == []
    finally:
        console.close()


def test_console_history_replays_as_cli_batch(tmp_path):
    from rocket_engine.adapters.cli import main as cli_main

    ops = [{"operation": "run_em", "arguments": {"x": 1}},
           {"operation": "run_em", "arguments": {"x": 2}}]
    console = _open(tmp_path=tmp_path / "c10",
                    cell_runner=FakeRunner(tmp_path, ops=ops))
    try:
        script = console.submit("tools.run_em(x=1)\n")["cli_script"]
    finally:
        console.close()
    batch = tmp_path / "console_history.txt"
    batch.write_text("\n".join(script) + "\n")
    replay = FakeEngine()
    code = cli_main(["--batch", str(batch)], engine=replay,
                    stdin=io.StringIO(), stdout=io.StringIO(),
                    stderr=io.StringIO())
    assert code == 0
    assert [(c[1]["operation"], c[1]["arguments"]) for c in replay.commands
            ] == [(op["operation"], op["arguments"]) for op in ops]


# --- Approvals reused from console.py; reset kills worker + approvals ---

def test_tampered_cell_rejected_by_reused_binding(tmp_path):
    console = _open(tmp_path=tmp_path / "c11",
                    cell_runner=FakeRunner(tmp_path))
    try:
        approval = console.request_approval("print(1)\n")
        assert approval["state"] == "pending_approval"
        with pytest.raises(Exception) as excinfo:
            console.run_approved(approval["approval_id"], "print(2)\n")
        assert getattr(excinfo.value, "code", None) == "approval_invalid"
        record = console.run_approved(approval["approval_id"], "print(1)\n")
        assert record["ok"] is True
    finally:
        console.close()


def test_reset_kills_approvals_and_renews_generation(tmp_path):
    console = _open(tmp_path=tmp_path / "c12",
                    cell_runner=FakeRunner(tmp_path))
    try:
        approval = console.request_approval("print(1)\n")
        before = console.generation
        out = console.reset()
        assert out["generation"] != before
        assert console.generation == out["generation"]
        with pytest.raises(Exception) as excinfo:
            console.run_approved(approval["approval_id"], "print(1)\n")
        assert getattr(excinfo.value, "code", None) == "approval_invalid"
    finally:
        console.close()


def test_reset_generation_persists_across_restart(tmp_path):
    root = str(tmp_path / "c13")
    first = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    try:
        generation = first.reset()["generation"]
    finally:
        first.close()
    second = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    try:
        assert second.generation == generation
    finally:
        second.close()


def test_single_console_per_panel_busy(tmp_path):
    root = str(tmp_path / "c14")
    first = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    try:
        with pytest.raises(Exception) as excinfo:
            _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
        assert getattr(excinfo.value, "code", None) == "console_busy"
    finally:
        first.close()
    second = _open(tmp_path=root, cell_runner=FakeRunner(tmp_path))
    second.close()


def test_not_run_without_isolation_persists_truthfully(tmp_path):
    from rocket_engine.execution.worker import CellRunner

    broken = CellRunner(binary="/nonexistent-bwrap-for-console",
                        artifacts_root=str(tmp_path / "harvest"))
    assert broken.admission["admitted"] is False
    console = _open(tmp_path=tmp_path / "c15", cell_runner=broken)
    try:
        record = console.submit("print('never-runs')\n")
        assert record["state"] == "not_run"
        assert record["ok"] is False
        assert record["code"] == "isolation_unavailable"
        assert record["ops"] == []
        root = Path(console.root)
        assert (root / record["cell"]).read_text() == "print('never-runs')\n"
        assert (root / "executions" / f"{record['execution_id']}.yaml"
                ).is_file()
        assert len(console.history()) == 1
    finally:
        console.close()


# --- Local-only trust boundary (asserted from source) ---

def test_local_only_trust_documented():
    mod = _console()
    assert mod.LOCAL_ONLY_TRUST is True
    assert "Local-only" in mod.TRUST_NOTE
    assert "stdio" in mod.TRUST_NOTE
    assert "no auth" in mod.TRUST_NOTE


def test_no_auth_or_network_code_paths():
    source = CONSOLE_SRC.read_text()  # RED: file missing
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert not any(
                stripped.startswith(prefix)
                for prefix in ("import socket", "import http", "import ssl",
                               "import urllib", "import requests",
                               "import fastapi", "from socket",
                               "from http", "from urllib", "from fastapi")
            ), f"network import in stdio console: {stripped}"
    lowered = source.lower()
    assert "def login" not in lowered
    assert "def authenticate" not in lowered
    assert "password" not in lowered


def test_adapters_never_call_each_other():
    source = CONSOLE_SRC.read_text()  # RED: file missing
    assert "execution.dispatch" in source or "execution import" in source
    for other in ("adapters.cli", "adapters.mcp", "adapters.http",
                  "adapters.ipc"):
        assert other not in source


# --- Live worker behavior (skips loudly without provable isolation) ---

def test_live_on_the_fly_cell(live_console):
    record = live_console.submit("print('cell-ok')\n", timeout_s=30)
    assert record["state"] == "completed"
    assert record["ok"] is True
    assert "cell-ok" in record["stdout"]
    assert record["ops"] == []
    assert record["credential_revoked"] is True
    assert record["tree_killed"] is True


def test_live_prebounds_available_zero_setup(live_console):
    code = (
        "print('project=' + project.id)\n"
        "print('tools=' + str(tools.run_em(x=1)))\n"
        "print('pdk=' + str(pdk.describe()))\n"
        "print('gf=' + repr(gf))\n"
        "print('np=' + repr(np))\n"
        "print('plot-available=' + str(plot.available))\n"
    )
    record = live_console.submit(code, timeout_s=30)
    assert record["state"] == "completed"
    assert "project=console_probe" in record["stdout"]
    assert "run_em" in record["stdout"]
    assert "plot-available=" in record["stdout"]
    assert len(record["ops"]) == 1
    assert record["ops"][0]["operation"] == "run_em"


def test_live_multiline_cell(live_console):
    code = (
        "def quad(x):\n"
        "    return 2 * x\n"
        "total = 0\n"
        "for i in range(4):\n"
        "    total += quad(i)\n"
        "print('total=%d' % total)\n"
    )
    record = live_console.submit(code, timeout_s=30)
    assert record["state"] == "completed"
    assert "total=12" in record["stdout"]


def test_live_script_file_cell(tmp_path, live_console):
    script = tmp_path / "script_cell.py"
    script.write_text(
        "def f(n):\n    return n + 1\nprint('f=%d' % f(41))\n",
        encoding="utf-8",
    )
    record = live_console.submit_file(str(script), timeout_s=30)
    assert record["state"] == "completed"
    assert "f=42" in record["stdout"]
    assert record["source_file"] == str(script)


def test_live_fresh_worker_per_cell(live_console):
    first = live_console.submit(
        "open('marker.txt', 'w').write('A')\nprint('A-done')\n",
        timeout_s=30,
    )
    assert first["state"] == "completed"
    second = live_console.submit(
        "import os\n"
        "print('FRESH_OK' if not os.path.exists('marker.txt')"
        " else 'STALE')\n",
        timeout_s=30,
    )
    assert "FRESH_OK" in second["stdout"]
    assert "STALE" not in second["stdout"]
    assert first["run_id"] != second["run_id"]


def test_live_tool_calls_replay_on_host_dispatch(live_console):
    engine = live_console.engine
    before = len(engine.commands)
    record = live_console.submit(
        "tools.run_em(x=1)\nproject.snapshot()\n", timeout_s=30
    )
    assert record["state"] == "completed"
    assert [op["operation"] for op in record["ops"]] == [
        "run_em", "get_project_snapshot"]
    assert record["ops_ok"] is True
    assert len(engine.commands) == before + 2
    assert engine.commands[before][0] == "run"
    assert engine.commands[before + 1][0] == "submit"


def test_live_reset_kills_worker_tokens_and_approvals(live_console):
    seen = {}

    def on_live(run_id, token):
        seen.update(run_id=run_id, token=token)

    live_console.submit("print('tokenized')\n", timeout_s=30, on_live=on_live)
    assert seen["token"]
    approval = live_console.request_approval("print('stale')\n")
    live_console.reset()
    with pytest.raises(Exception) as excinfo:
        live_console.run_approved(approval["approval_id"], "print('stale')\n")
    assert getattr(excinfo.value, "code", None) == "approval_invalid"
    with pytest.raises(Exception) as excinfo:
        live_console.gate.invoke(seen["token"], {"op": "late"})
    assert getattr(excinfo.value, "code", None) == "credential_revoked"


# --- stdio framing for the xterm panel ---

def _run_main(argv, stdin_text, tmp_path, ops=()):
    mod = _console()
    stdout, stderr = io.StringIO(), io.StringIO()
    code = mod.main(
        argv + ["--root", str(tmp_path / "panel")], engine=FakeEngine(),
        cell_runner=FakeRunner(tmp_path, ops=ops),
        stdin=io.StringIO(stdin_text), stdout=stdout, stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_main_submit_history_reset_quit(tmp_path):
    code, out, _ = _run_main(
        [], "submit\nprint('panel-hi')\n:end\nhistory\nreset\nquit\n",
        tmp_path,
    )
    assert code == 0
    assert "panel-hi" not in out  # stdout comes from the worker record
    assert "fake-out" in out
    assert "cell" in out
    assert "history" in out.lower() or "cursor" in out.lower()
    assert "generation" in out.lower()


def test_main_json_envelopes(tmp_path):
    code, out, _ = _run_main(
        ["--json"], "submit\nprint(1)\n:end\n", tmp_path
    )
    assert code == 0
    envelopes = [json.loads(line) for line in out.splitlines()
                 if line.strip()]
    assert envelopes
    assert envelopes[0]["command"] == "submit"
    assert envelopes[0]["ok"] is True
    assert envelopes[0]["result"]["execution_id"]


def test_main_unknown_command_continues_clean(tmp_path):
    code, _, err = _run_main([], "bogus-command\nquit\n", tmp_path)
    assert code == 0
    assert "bogus-command" in err


def test_main_help_and_bad_flag(tmp_path):
    mod = _console()
    stdout = io.StringIO()
    assert mod.main(["--help"], engine=FakeEngine(),
                    stdin=io.StringIO(), stdout=stdout,
                    stderr=io.StringIO()) == 0
    assert "usage" in stdout.getvalue().lower()
    assert mod.main(["--bogus"], engine=FakeEngine(),
                    stdin=io.StringIO(), stdout=io.StringIO(),
                    stderr=io.StringIO()) == 2


def test_module_entry_point_help():
    proc = subprocess.run(
        [sys.executable, "-m", "rocket_engine.adapters.stdio_console",
         "--help"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()
