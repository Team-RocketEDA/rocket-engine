"""CLI-DISPATCH RED — `rocket-engine` entry: REPL, run, batch, --json.

Tests assume `main` on `rocket_engine.adapters.cli` with the shape
`main(argv, engine, stdin, stdout, stderr) -> int`, plus a
`python -m rocket_engine` entry point over it. Valid RED = each
import fails and the `-m` entry is missing: the CLI inbound adapter
does not exist yet (parked stub).

Honest exits: execution-ok is 0 EVEN when the verdict is FAIL
(verdict lives in the payload); engine errors are 1; unknown
op/args are usage errors (exit 2). Verdicts from data, never from
exit codes.
"""

import io
import json
import subprocess
import sys

import pytest


def _main():
    from rocket_engine.adapters.cli import main  # RED: missing adapter

    return main


def _run_cli(argv, engine, stdin_text=""):
    main = _main()
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(argv, engine=engine, stdin=io.StringIO(stdin_text),
                stdout=stdout, stderr=stderr)
    return code, stdout.getvalue(), stderr.getvalue()


class FakeEngine:
    """Deterministic stand-in: submit-immediate completed PASS acks."""

    def __init__(self):
        self.commands = []

    def run(self, command):
        self.commands.append(("run", command))
        return {"run_id": "run_fake", "state": "completed",
                "verdict": {"status": "PASS"},
                "operation": command["operation"]}

    def submit(self, command):
        self.commands.append(("submit", command))
        return {"run_id": "run_fake_q", "state": "completed",
                "verdict": {"status": "PASS"},
                "operation": command["operation"]}


class FailingEngine(FakeEngine):
    def submit(self, command):
        from rocket_engine.adapters.errors import AdapterError

        raise AdapterError("runner_unavailable", "fake tool exploded")


def test_bare_args_repl_runs_lines_until_eof():
    code, out, _ = _run_cli([], FakeEngine(), "run_em x=1\nrun_em x=2\n")
    assert code == 0
    assert out.count("PASS") == 2
    assert "run_em" in out


def test_repl_reports_bad_line_inline_and_quits_clean():
    engine = FakeEngine()
    code, _, err = _run_cli([], engine, "frobnicate x=1\nquit\n")
    assert code == 0
    assert "frobnicate" in err
    assert engine.commands == []


def test_run_single_op_good_exits_zero():
    engine = FakeEngine()
    code, out, _ = _run_cli(["run", "run_em", "x=1"], engine)
    assert code == 0
    assert "PASS" in out
    kind, command = engine.commands[0]
    assert kind == "submit"
    assert command["operation"] == "run_em"
    assert command["arguments"] == {"x": 1}


def test_run_routes_query_to_submit():
    engine = FakeEngine()
    code, _, _ = _run_cli(["run", "get_project_snapshot"], engine)
    assert code == 0
    assert engine.commands[0][0] == "submit"


def test_run_respects_project_flag():
    engine = FakeEngine()
    code, _, _ = _run_cli(["--project", "p1", "run", "run_em"], engine)
    assert code == 0
    assert engine.commands[0][1]["project_id"] == "p1"


def test_run_single_accepts_caller_request_id():
    engine = FakeEngine()
    code, _, _ = _run_cli(
        ["--request-id", "caller-1", "run", "run_em"], engine)
    assert code == 0
    kind, command = engine.commands[0]
    assert kind == "submit"
    assert command["request_id"] == "caller-1"


def test_run_single_mints_request_id_when_flag_absent():
    engine = FakeEngine()
    code, _, _ = _run_cli(["run", "run_em"], engine)
    assert code == 0
    assert engine.commands[0][1]["request_id"]


def test_run_unknown_op_is_usage_error():
    engine = FakeEngine()
    code, _, err = _run_cli(["run", "frobnicate"], engine)
    assert code == 2
    assert "frobnicate" in err
    assert engine.commands == []


def test_run_malformed_args_is_usage_error():
    code, _, err = _run_cli(["run", "run_em", "oops"], FakeEngine())
    assert code == 2
    assert "usage" in err.lower()


def test_run_engine_error_exits_one():
    code, _, err = _run_cli(["run", "run_em"], FailingEngine())
    assert code == 1
    assert "runner_unavailable" in err


def test_batch_file_skips_comments_and_blanks(tmp_path):
    engine = FakeEngine()
    batch = tmp_path / "ops.txt"
    batch.write_text("# console history\n\nrun_em x=1\nrun_em x=2\n")
    code, out, _ = _run_cli(["--batch", str(batch)], engine)
    assert code == 0
    assert out.count("PASS") == 2
    assert [c[1]["arguments"] for c in engine.commands] == [{"x": 1}, {"x": 2}]


def test_batch_stdin_dash():
    engine = FakeEngine()
    code, out, _ = _run_cli(["--batch", "-"], engine, "run_em x=7\n")
    assert code == 0
    assert "PASS" in out
    assert engine.commands[0][1]["arguments"] == {"x": 7}


def test_batch_missing_file_is_engine_error():
    code, _, err = _run_cli(["--batch", "/no/such/file"], FakeEngine())
    assert code == 1
    assert err.strip() != ""


def test_batch_aggregates_line_errors(tmp_path):
    batch = tmp_path / "ops.txt"
    batch.write_text("run_em x=1\nfrobnicate\n")
    code, _, err = _run_cli(["--batch", str(batch)], FailingEngine())
    assert code == 2  # usage error present beats engine error
    assert "frobnicate" in err


def test_json_shape_single_ok():
    code, out, _ = _run_cli(["--json", "run", "run_em", "x=1"], FakeEngine())
    assert code == 0
    envelope = json.loads(out)
    assert envelope["operation"] == "run_em"
    assert envelope["ok"] is True
    assert envelope["result"]["verdict"]["status"] == "PASS"


def test_json_shape_usage_error_on_stdout():
    code, out, _ = _run_cli(["--json", "run", "frobnicate"], FakeEngine())
    assert code == 2
    envelope = json.loads(out)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "unsupported_operation"


def test_json_batch_is_json_lines(tmp_path):
    batch = tmp_path / "ops.txt"
    batch.write_text("run_em x=1\nrun_em x=2\n")
    code, out, _ = _run_cli(["--json", "--batch", str(batch)], FakeEngine())
    assert code == 0
    lines = [json.loads(line) for line in out.splitlines()]
    assert [e["ok"] for e in lines] == [True, True]
    assert all(e["operation"] == "run_em" for e in lines)


def test_fail_verdict_exits_zero_with_fail_in_payload():
    from rocket_engine.composition import Engine

    class Violating:
        def capabilities(self, target):
            return {"operations": ["run_em"]}

        def preflight(self, job):
            return {"ready": True}

        def execute(self, job):
            return {"exit_code": 0, "stdout": "fake", "stderr": ""}

        def parse(self, native_output):
            return {"total": 1, "violations": [
                {"rule": "e-rule", "severity": "error"}]}

    engine = Engine("cli_demo", actor="tester")
    engine.register_solver("run_em", Violating(), tool="fake")
    code, out, _ = _run_cli(
        ["--json", "--project", "cli_demo", "run", "run_em",
         "deck={tool: fake}"], engine)
    assert code == 0
    envelope = json.loads(out)
    assert envelope["ok"] is True
    assert envelope["result"]["verdict"]["status"] == "FAIL"


def test_console_history_replays_as_cli_batch(tmp_path):
    from rocket_engine.execution.dispatch import OpDispatcher

    history = ["run_em x=1", "run_em x=2", "get_project_snapshot"]
    console_results = [OpDispatcher(FakeEngine()).execute_line(line)[1]
                       for line in history]
    batch = tmp_path / "history.txt"
    batch.write_text("\n".join(history) + "\n")
    code, out, _ = _run_cli(["--json", "--batch", str(batch)], FakeEngine())
    assert code == 0
    cli_results = [json.loads(line)["result"] for line in out.splitlines()]
    assert cli_results == console_results


def test_help_exits_zero():
    code, out, _ = _run_cli(["--help"], FakeEngine())
    assert code == 0
    assert "usage" in out.lower()


def test_run_and_batch_conflict_is_usage_error():
    code, _, err = _run_cli(["--batch", "f", "run", "run_em"], FakeEngine())
    assert code == 2
    assert "usage" in err.lower()


def test_module_entry_point_help():
    proc = subprocess.run([sys.executable, "-m", "rocket_engine", "--help"],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "usage" in proc.stdout.lower()


def test_module_entry_point_unknown_op_exit_2():
    proc = subprocess.run(
        [sys.executable, "-m", "rocket_engine", "run", "frobnicate"],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 2
    assert "frobnicate" in proc.stderr
