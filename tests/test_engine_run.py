"""Engine.run RED — first live operation end to end (DRC-GREEN).

Valid RED = `Engine` has no solver registry yet, so every test fails
with AttributeError. Magic-backed tests skip where magic is absent;
registry tests run everywhere.
"""

import shutil
from pathlib import Path

import pytest

from rocket_engine.composition import Engine

PROJECT = "analog_demo"
FIXTURES = Path("tests/adapters/fixtures/drc")

magic_present = shutil.which("magic") is not None
needs_magic = pytest.mark.skipif(not magic_present, reason="magic not installed")
slang_present = shutil.which("slang") is not None
needs_slang = pytest.mark.skipif(not slang_present, reason="slang not on PATH")


def _command(cell, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    cell_file = workdir / f"{cell}.mag"
    shutil.copy(Path(FIXTURES) / f"{cell}.mag", cell_file)
    command = {
        "project_id": PROJECT,
        "operation": "run_drc",
        "arguments": {
            "tech": "scmos",
            "cell": cell,
            "cell_file": str(cell_file),
            "workdir": str(workdir),
        },
    }
    command.update(over)
    return command


@needs_magic
def test_run_drc_good_cell_passes(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    out = engine.run(_command("good", tmp_path))
    assert out["state"] == "completed"
    assert out["verdict"]["status"] == "PASS"
    assert engine.findings(out["run_id"])["findings"] == []


@needs_magic
def test_run_drc_bad_cell_fails_with_violations(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    out = engine.run(_command("bad_spacing", tmp_path))
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any("spacing" in f["rule"] for f in found)
    assert all(len(f["location"]["bbox_lambda"]) == 4 for f in found)


def test_run_unregistered_operation_raises(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    command = _command("good", tmp_path, operation="run_em")
    try:
        engine.run(command)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_em")


def test_submit_unwired_operation_raises():
    engine = Engine(PROJECT, actor="tester")
    try:
        engine.submit(
            {
                "project_id": PROJECT,
                "operation": "run_em",
                "arguments": {"expected_revision": "p12"},
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_em")


def test_submit_run_syntax_accepted():
    engine = Engine(PROJECT, actor="tester")
    ack = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {"expected_revision": "p12"},
        }
    )
    assert ack["state"] == "completed"
    assert {"run_id", "snapshot_id", "event_cursor"} <= set(ack)
    assert ack["verdict"]["status"] == "NOT_RUN"


@needs_slang
def test_run_syntax_clean_passes_live(tmp_path):
    from rocket_engine.adapters.syntax import SyntaxAdapter  # noqa: F401

    engine = Engine(PROJECT, actor="tester")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = workdir / "counter.v"
    shutil.copy(
        Path("tests/adapters/fixtures/syntax/counter.v"), staged
    )
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "sources": [str(staged)],
                "workdir": str(workdir),
            },
        }
    )
    assert out["state"] == "completed"
    assert out["verdict"]["status"] == "PASS"
    assert engine.findings(out["run_id"])["findings"] == []


@needs_slang
def test_run_syntax_broken_fails_with_span_live(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    staged = workdir / "counter_broken.v"
    shutil.copy(
        Path("tests/adapters/fixtures/syntax/counter_broken.v"), staged
    )
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_syntax",
            "arguments": {
                "sources": [str(staged)],
                "workdir": str(workdir),
            },
        }
    )
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any(f["severity"] == "error" for f in found)
    assert all("line" in f["location"] for f in found)


@needs_magic
def test_run_records_not_run_on_preflight_refusal(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    command = _command("good", tmp_path)
    command["arguments"]["tech"] = "no_such_tech"
    out = engine.run(command)
    assert out["state"] == "completed"
    assert out["verdict"]["status"] == "NOT_RUN"
    assert "missing_dependency" in out["verdict"]["reason"]


class FakeAdapter:
    def capabilities(self, target):
        return {"operations": ["run_em"]}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return {"exit_code": 0, "stdout": "fake", "stderr": ""}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


def test_register_solver_wires_custom_operation(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", FakeAdapter())
    command = _command("good", tmp_path, operation="run_em")
    out = engine.run(command)
    assert out["verdict"]["status"] == "PASS"


def test_run_job_executes_queued_request():
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", FakeAdapter())
    ack = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": "req_job_001",
        }
    )
    assert ack["state"] == "completed"
    out = engine.run(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {"request_id": "req_job_001"},
        }
    )
    assert out["state"] == "completed"
    assert out["operation"] == "run_em"
    assert out["verdict"]["status"] == "PASS"


def test_run_job_unknown_request_raises():
    engine = Engine(PROJECT, actor="tester")
    try:
        engine.run(
            {
                "project_id": PROJECT,
                "operation": "run_job",
                "arguments": {"request_id": "req_nope"},
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "unknown_request"
    else:
        raise AssertionError("expected unknown_request")


def test_submit_run_job_executes_immediately():
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", FakeAdapter())
    engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_em",
            "arguments": {"expected_revision": "p12"},
            "request_id": "req_job_002",
        }
    )
    out = engine.submit(
        {
            "project_id": PROJECT,
            "operation": "run_job",
            "arguments": {"request_id": "req_job_002"},
        }
    )
    assert out["state"] == "completed"
    assert out["verdict"]["status"] == "PASS"


class FailingAdapter(FakeAdapter):
    def execute(self, job):
        from rocket_engine.adapters.errors import AdapterError

        raise AdapterError("runner_unavailable", "fake tool exploded")


def test_run_records_not_run_when_tool_fails(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", FailingAdapter())
    command = _command("good", tmp_path, operation="run_em")
    out = engine.run(command)
    assert out["verdict"]["status"] == "NOT_RUN"
    assert "runner_unavailable" in out["verdict"]["reason"]


KL_FIXTURES = Path("tests/adapters/fixtures/drc_kl")

needs_klayout = pytest.mark.skipif(
    shutil.which("klayout") is None, reason="klayout not installed"
)


def _kl_command(cell, tmp_path, **over):
    workdir = tmp_path / "klwork"
    workdir.mkdir(exist_ok=True)
    gds_file = workdir / f"{cell}.gds"
    shutil.copy(Path(KL_FIXTURES) / f"{cell}.gds", gds_file)
    command = {
        "project_id": PROJECT,
        "operation": "run_drc",
        "arguments": {
            "tech": "synthetic-kl",
            "cell": cell,
            "gds_file": str(gds_file),
            "workdir": str(workdir),
            "rules": {"layer": [1, 0], "width_um": 3.0, "space_um": 3.0},
            "deck": {"tool": "klayout"},
        },
    }
    command.update(over)
    return command


@needs_klayout
def test_run_selects_solver_from_deck_tool(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    out = engine.run(_kl_command("bad_space", tmp_path))
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert any("space" in f["rule"] for f in found)
    assert all(len(f["location"]["bbox_um"]) == 4 for f in found)


@needs_magic
def test_run_defaults_to_first_registered_solver(tmp_path):
    # Characterization: no deck hint keeps today's behavior (magic).
    engine = Engine(PROJECT, actor="tester")
    out = engine.run(_command("bad_spacing", tmp_path))
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert all("bbox_lambda" in f["location"] for f in found)


def test_run_unknown_deck_tool_raises(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    command = _command("good", tmp_path)
    command["arguments"]["deck"] = {"tool": "no_such_tool"}
    try:
        engine.run(command)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for unknown deck tool")


class NamedFake(FakeAdapter):
    def __init__(self, rule):
        self._rule = rule

    def parse(self, native_output):
        return {"total": 1, "violations": [{"rule": self._rule}]}


def test_register_solver_names_tool_explicitly(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", NamedFake("rule-a"), tool="alpha")
    engine.register_solver("run_em", NamedFake("rule-b"), tool="beta")

    def _spice(deck):
        command = _command("good", tmp_path, operation="run_em")
        if deck is not None:
            command["arguments"]["deck"] = {"tool": deck}
        return engine.run(command)

    out_alpha = _spice("alpha")
    found_alpha = engine.findings(out_alpha["run_id"])["findings"]
    assert [f["rule"] for f in found_alpha] == ["rule-a"]
    out_beta = _spice("beta")
    found = engine.findings(out_beta["run_id"])["findings"]
    assert [f["rule"] for f in found] == ["rule-b"]
    out_default = _spice(None)
    found_default = engine.findings(out_default["run_id"])["findings"]
    assert [f["rule"] for f in found_default] == ["rule-a"]


class FileFake(FakeAdapter):
    def parse(self, native_output):
        return {
            "total": 1,
            "violations": [
                {
                    "rule": "assert_error",
                    "severity": "error",
                    "message": "counter sequence wrong",
                    "file": "tb_error.v",
                    "line": 17,
                    "sim_time": 112000,
                }
            ],
        }


def test_run_preserves_file_line_locations(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_em", FileFake(), tool="filefake")
    command = _command("good", tmp_path, operation="run_em")
    command["arguments"]["deck"] = {"tool": "filefake"}
    out = engine.run(command)
    assert out["verdict"]["status"] == "FAIL"
    found = engine.findings(out["run_id"])["findings"]
    assert found[0]["location"] == {"file": "tb_error.v", "line": 17, "sim_time": 112000}
