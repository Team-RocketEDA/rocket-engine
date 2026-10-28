"""DRC-KL RED — KlayoutDrcAdapter behind the ToolAdapter port (I14).

Valid RED = `rocket_engine.adapters.drc_kl` does not exist yet, so
every test fails on ImportError. Fixtures are verified against real
KLayout 0.28.16: good→0, bad_space→1 space, bad_width→1 width.
Tests skip (never fake-green) where klayout is absent.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "drc_kl"

klayout_present = shutil.which("klayout") is not None
needs_klayout = pytest.mark.skipif(not klayout_present, reason="klayout not installed")

RULES = {"layer": [1, 0], "width_um": 3.0, "space_um": 3.0}


def _job(cell, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds_file = workdir / f"{cell}.gds"
    shutil.copy(FIXTURES / f"{cell}.gds", gds_file)
    job = {
        "operation": "run_drc",
        "gds_file": str(gds_file),
        "workdir": str(workdir),
        "rules": dict(RULES),
    }
    job.update(over)
    return job


def test_drc_kl_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    assert issubclass(KlayoutDrcAdapter, ToolAdapter)


@needs_klayout
def test_drc_kl_capabilities_advertise_run_drc():
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    caps = KlayoutDrcAdapter().capabilities({"cell": "TOP"})
    assert "run_drc" in caps["operations"]
    assert caps["tool"] == "klayout"


@needs_klayout
def test_drc_kl_preflight_refuses_missing_gds(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    job = _job("good", tmp_path)
    job["gds_file"] = str(tmp_path / "work" / "ghost.gds")
    try:
        KlayoutDrcAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a missing GDS")


@needs_klayout
def test_drc_kl_preflight_refuses_insane_rules(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    job = _job("good", tmp_path)
    job["rules"]["width_um"] = -1.0
    try:
        KlayoutDrcAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for negative width")


@needs_klayout
def test_drc_kl_good_cell_reports_zero(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    adapter = KlayoutDrcAdapter()
    native = adapter.execute(_job("good", tmp_path))
    assert isinstance(native["stdout"], str)
    result = adapter.parse(native)
    assert result["total"] == 0
    assert result["violations"] == []


@needs_klayout
def test_drc_kl_bad_cells_report_named_violations(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter  # RED: missing adapter

    adapter = KlayoutDrcAdapter()
    for cell, keyword in (("bad_space", "space"), ("bad_width", "width")):
        result = adapter.parse(adapter.execute(_job(cell, tmp_path)))
        assert result["total"] >= 1
        assert any(keyword in v["rule"] for v in result["violations"])
        for violation in result["violations"]:
            assert len(violation["bbox_um"]) == 4


@needs_klayout
def test_drc_kl_proves_fixture_labels_against_real_klayout(tmp_path):
    # Oracle check: the labels above are verified against klayout
    # itself, not against the adapter under test.
    from rocket_engine.adapters.drc_kl import (  # RED: missing adapter  # noqa: F401
        KlayoutDrcAdapter,
    )

    script = tmp_path / "oracle.py"
    script.write_text(
        "import pya\n"
        "layout = pya.Layout()\n"
        f"layout.read({str(FIXTURES / 'CELLNAME.gds')!r})\n"
        "top = layout.top_cell()\n"
        "region = pya.Region(top.begin_shapes_rec(layout.find_layer(1, 0)))\n"
        "print('width', sum(1 for _ in region.width_check(3000).each()))\n"
        "print('space', sum(1 for _ in region.space_check(3000).each()))\n"
    )
    for cell, want in (
        ("good", ("width 0", "space 0")),
        ("bad_space", ("width 0", "space 1")),
        ("bad_width", ("width 1", "space 0")),
    ):
        text = script.read_text().replace("CELLNAME", cell)
        run_script = tmp_path / f"oracle_{cell}.py"
        run_script.write_text(text)
        proc = subprocess.run(
            ["klayout", "-b", "-r", str(run_script)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        for line in want:
            assert line in proc.stdout


def test_klayout_uses_injected_runner(tmp_path):
    import subprocess

    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter

    seen = {}

    class FakeRunner:
        def run(self, command, workdir, timeout_s=120, extra_binds=()):
            seen["command"] = command
            seen["workdir"] = workdir
            return subprocess.CompletedProcess(command, 0, "", "")

    adapter = KlayoutDrcAdapter(runner=FakeRunner())  # RED: no runner slot
    proc = adapter._run(["klayout", "-b"], str(tmp_path))
    assert seen["command"][:2] == ["klayout", "-b"]
    assert seen["workdir"] == str(tmp_path)
    assert proc.returncode == 0


def test_klayout_converts_runner_errors(tmp_path):
    from rocket_engine.adapters.drc_kl import KlayoutDrcAdapter
    from rocket_engine.execution.errors import ExecutionError

    class BoomRunner:
        def run(self, *args, **kwargs):
            raise ExecutionError("runner_unavailable", "boom")

    adapter = KlayoutDrcAdapter(runner=BoomRunner())
    try:
        adapter._run(["klayout", "-b"], str(tmp_path))
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner error conversion")
