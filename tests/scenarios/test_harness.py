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
def test_live_magic_scenarios_pass_against_real_magic():
    runner = _load_runner()
    for name in ("drc_live_pass.yaml", "drc_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_klayout = pytest.mark.skipif(
    shutil.which("klayout") is None, reason="klayout not installed"
)


@needs_klayout
def test_live_klayout_scenarios_pass_against_real_klayout():
    runner = _load_runner()
    for name in ("drc_live_kl_pass.yaml", "drc_live_kl_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


@needs_klayout
def test_live_sky130_scenarios_pass_against_real_deck():
    for name in ("good.gds", "bad.gds"):
        if not (ROOT / "tests" / "adapters" / "fixtures" / "drc_sky130" / name).is_file():
            pytest.skip(f"sky130 fixtures not generated: {name}")
    try:
        from rocket_engine.interfaces.pdks import list_pdks
    except Exception:
        pytest.skip("pdk store unavailable")
    try:
        entries = list_pdks()
    except Exception:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    if not [e for e in entries if e.get("id") == "sky130a"]:
        pytest.skip("sky130 PDK deck not registered (ROCKETEDA_HOME)")
    runner = _load_runner()
    for name in ("drc_sky130_pass.yaml", "drc_sky130_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


needs_icarus = pytest.mark.skipif(
    shutil.which("iverilog") is None or shutil.which("vvp") is None,
    reason="iverilog/vvp not on PATH",
)


@needs_icarus
def test_live_hdl_scenarios_pass_against_real_tools():
    runner = _load_runner()
    for name in ("hdl_live_pass.yaml", "hdl_live_fail.yaml"):
        result = runner.run_scenario(ROOT / "scenarios" / name)
        assert result["passed"] is True, result["failures"]


def test_hdl_run_live_without_sources_fails_loudly(tmp_path):
    runner = _load_runner()
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        (ROOT / "scenarios" / "hdl_live_pass.yaml")
        .read_text()
        .replace(
            "run_live: {backend: hdl, sources: [counter.v, tb_pass.v]}",
            "run_live: {backend: hdl}",
        )
    )
    result = runner.run_scenario(bad)
    assert result["passed"] is False
    assert "sources" in result["failures"][0]


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
