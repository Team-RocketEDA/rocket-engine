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
    command = _command("good", tmp_path, operation="run_spice")
    try:
        engine.run(command)
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation for run_spice")


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
        return {"operations": ["run_spice"]}

    def preflight(self, job):
        return {"ready": True}

    def execute(self, job):
        return {"exit_code": 0, "stdout": "fake", "stderr": ""}

    def parse(self, native_output):
        return {"total": 0, "violations": []}


def test_register_solver_wires_custom_operation(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_spice", FakeAdapter())
    command = _command("good", tmp_path, operation="run_spice")
    out = engine.run(command)
    assert out["verdict"]["status"] == "PASS"


class FailingAdapter(FakeAdapter):
    def execute(self, job):
        from rocket_engine.adapters.errors import AdapterError

        raise AdapterError("runner_unavailable", "fake tool exploded")


def test_run_records_not_run_when_tool_fails(tmp_path):
    engine = Engine(PROJECT, actor="tester")
    engine.register_solver("run_spice", FailingAdapter())
    command = _command("good", tmp_path, operation="run_spice")
    out = engine.run(command)
    assert out["verdict"]["status"] == "NOT_RUN"
    assert "runner_unavailable" in out["verdict"]["reason"]
