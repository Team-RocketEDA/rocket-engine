"""The harness tests itself: a good scenario passes, a bad expectation fails loudly."""

import importlib.util
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

needs_magic = pytest.mark.skipif(
    shutil.which("magic") is None, reason="magic not installed"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "scenarios", ROOT / "scripts" / "scenarios.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_happy_scenario_passes():
    runner = _load_runner()
    result = runner.run_scenario(ROOT / "scenarios" / "drc_fake_fail.yaml")
    assert result["passed"] is True
    assert result["failures"] == []


@needs_magic
def test_live_scenarios_pass_against_real_magic():
    runner = _load_runner()
    for name in ("drc_live_pass.yaml", "drc_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


def test_broken_expectation_names_the_step(tmp_path):
    runner = _load_runner()
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (ROOT / "scenarios" / "drc_fake_fail.yaml")
        .read_text()
        .replace("assert_verdict: FAIL", "assert_verdict: PASS")
    )
    result = runner.run_scenario(bad)
    assert result["passed"] is False
    assert "step 3 (assert_verdict)" in result["failures"][0]
