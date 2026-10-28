"""DRC-RED — MagicDrcAdapter behind the ToolAdapter port (I14).

Valid RED = `rocket_engine.adapters.drc` does not exist yet, so every
test fails on ImportError. Fixtures are verified against real magic
8.3.685/scmos: good→0, bad_spacing→rule #7.2, bad_width→rule #7.1.
Tests skip (never fake-green) where magic is absent.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "drc"

magic_present = shutil.which("magic") is not None
needs_magic = pytest.mark.skipif(not magic_present, reason="magic not installed")


def _job(cell, tmp_path, **over):
    workdir = tmp_path / "work"
    workdir.mkdir()
    cell_file = workdir / f"{cell}.mag"
    shutil.copy(FIXTURES / f"{cell}.mag", cell_file)
    job = {
        "operation": "run_drc",
        "tech": "scmos",
        "cell": cell,
        "cell_file": str(cell_file),
        "workdir": str(workdir),
    }
    job.update(over)
    return job


def test_drc_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter  # live surface
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter

    assert issubclass(MagicDrcAdapter, ToolAdapter)


@needs_magic
def test_drc_capabilities_advertise_run_drc():
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter

    caps = MagicDrcAdapter().capabilities({"cell": "good"})
    assert "run_drc" in caps["operations"]
    assert caps["tech"] == "scmos"


@needs_magic
def test_drc_preflight_refuses_unknown_tech(tmp_path):
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter

    try:
        MagicDrcAdapter().preflight(_job("good", tmp_path, tech="no_such_tech"))
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for unknown tech")


@needs_magic
def test_drc_good_cell_reports_zero(tmp_path):
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter

    adapter = MagicDrcAdapter()
    native = adapter.execute(_job("good", tmp_path))
    assert isinstance(native["stdout"], str)
    result = adapter.parse(native)
    assert result["total"] == 0
    assert result["violations"] == []


@needs_magic
def test_drc_bad_cells_report_named_violations(tmp_path):
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter

    adapter = MagicDrcAdapter()
    for cell, keyword in (("bad_spacing", "spacing"), ("bad_width", "width")):
        result = adapter.parse(adapter.execute(_job(cell, tmp_path)))
        assert result["total"] >= 1
        assert any(keyword in v["rule"] for v in result["violations"])
        for violation in result["violations"]:
            assert len(violation["bbox"]) == 4


@needs_magic
def test_drc_proves_fixture_labels_against_real_magic(tmp_path):
    # Oracle check: the labels above are verified against magic itself,
    # not against the adapter under test.
    from rocket_engine.adapters.drc import MagicDrcAdapter  # RED: missing adapter  # noqa: F401

    script = (
        "load {cell}\nbox values -5 -5 15 10\n"
        "drc check\ndrc catchup\ndrc count total\ndrc why\nquit\n"
    )
    for cell, want_total, want_rule in (
        ("good", 0, "No errors found."),
        ("bad_spacing", 1, "rule #7.2"),
        ("bad_width", 1, "rule #7.1"),
    ):
        proc = subprocess.run(
            ["magic", "-dnull", "-noconsole", "-T", "scmos"],
            input=script.format(cell=cell),
            capture_output=True,
            text=True,
            timeout=120,
            cwd=FIXTURES,
        )
        assert f"Total DRC errors found: {want_total}" in proc.stdout
        assert want_rule in proc.stdout
