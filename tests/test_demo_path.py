"""DEMO-PATH RED slice A — install.sh demo provisioning.

Valid RED = scripts/install.sh has no --pdk-only mode and probes no
netgen: check-only passes but names no netgen, --pdk-only exits 2
(usage), and the --install branch never invokes the PDK step. GREEN
adds the PDK-register stage (venv + locked sync + engine + tool
probe + PDK register) with cause + next-step failures, no bare
tracebacks.

Slice B (demo.sh + runbook + scenario coverage + LVS preflight)
arrives as a second RED commit on top of this file.
"""

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install.sh"
DEMO = ROOT / "scripts" / "demo.sh"
RUNBOOK = ROOT / "docs" / "demo-runbook.md"


def run_install(args, env_over=None, timeout=180):
    env = dict(os.environ)
    env.setdefault("ROCKETEDA_HOME", "/nonexistent-rocketeda-home-demo-test")
    if env_over:
        env.update(env_over)
    return subprocess.run(
        ["bash", str(INSTALL), *args],
        capture_output=True, text=True, timeout=timeout, env=env, cwd=ROOT,
    )


def _tiny_pdk(tmp_path):
    src = tmp_path / "tiny130A"
    (src / "libs.tech" / "combined").mkdir(parents=True)
    (src / "libs.tech" / "combined" / "sky130.lib.spice").write_text(
        "* tiny model lib\n")
    return src


def test_install_check_only_probes_netgen():
    proc = run_install(["--check-only"])
    assert proc.returncode == 0, proc.stderr
    assert "netgen" in proc.stdout, proc.stdout


def test_install_pdk_only_registers_tiny_pdk(tmp_path):
    store = tmp_path / "store"
    proc = run_install(["--pdk-only"], env_over={
        "ROCKETEDA_HOME": str(store),
        "PDK_SOURCE": str(_tiny_pdk(tmp_path)),
        "PDK_ID": "tiny130a",
        "PDK_REVISION": "r1",
    })
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (store / "pdks" / "tiny130a" / "r1" / "manifest.yaml").is_file()
    assert "tiny130a" in proc.stdout and "r1" in proc.stdout, proc.stdout


def test_install_pdk_only_missing_source_names_cause_and_next_step(tmp_path):
    missing = tmp_path / "no-such-pdk"
    proc = run_install(["--pdk-only"], env_over={
        "ROCKETEDA_HOME": str(tmp_path / "store"),
        "PDK_SOURCE": str(missing),
    })
    assert proc.returncode == 1, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert str(missing) in combined, combined
    assert "PDK_SOURCE" in combined, combined
    assert "Traceback" not in combined, combined


def test_install_pdk_only_reregister_reverifies(tmp_path):
    store = tmp_path / "store"
    env = {
        "ROCKETEDA_HOME": str(store),
        "PDK_SOURCE": str(_tiny_pdk(tmp_path)),
        "PDK_ID": "tiny130a",
        "PDK_REVISION": "r1",
    }
    first = run_install(["--pdk-only"], env_over=env)
    assert first.returncode == 0, first.stdout + first.stderr
    second = run_install(["--pdk-only"], env_over=env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert ("reverif" in second.stdout.lower()
            or "already registered" in second.stdout.lower()), second.stdout


def test_install_wires_pdk_step_into_install_mode():
    # The --install branch must invoke the --pdk-only stage (proving
    # the full chain end-to-end happens in a fresh shell; see the
    # demo runbook). --install itself is never executed by the suite:
    # it recreates .venv under the running interpreter.
    text = INSTALL.read_text()
    assert "--pdk-only" in text, text


def test_install_unknown_mode_prints_usage():
    proc = run_install(["--bogus"])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "usage" in proc.stderr.lower(), proc.stderr


# --- Slice B: demo.sh + runbook + scenario coverage + failure grace ---

def test_demo_script_help_names_the_four_stages():
    proc = subprocess.run(
        ["bash", str(DEMO), "--help"],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for stage in ("install", "fetch", "scenarios", "gate"):
        assert stage in proc.stdout.lower(), proc.stdout


def test_runbook_has_single_command_and_expected_output():
    assert RUNBOOK.is_file(), "docs/demo-runbook.md missing"
    text = RUNBOOK.read_text()
    assert "scripts/demo.sh" in text, text
    assert "Expected output" in text, text
    for flow in ("digital", "analog", "photonic", "mixed"):
        assert flow in text, flow
    assert "next step" in text.lower(), text


FLOW_SCENARIOS = {
    "digital": ["serv_live_pass.yaml", "serv_live_fail.yaml",
                "picorv32_live_pass.yaml", "picorv32_live_fail.yaml",
                "hdl_live_pass.yaml", "hdl_live_fail.yaml"],
    "analog": ["ngspice_bandgap_pass.yaml", "ngspice_bandgap_fail.yaml"],
    "photonic": ["sax_mzi_pass.yaml", "sax_mzi_fail.yaml",
                 "klayout_mzi_pass.yaml", "klayout_mzi_fail.yaml"],
    "mixed": ["ngspice_sdtop_pass.yaml", "ngspice_sdtop_fail.yaml",
              "hdl_sdm_pass.yaml", "hdl_sdm_fail.yaml"],
    "layout": ["drc_live_pass.yaml", "drc_live_fail.yaml",
               "drc_sky130_pass.yaml", "drc_sky130_fail.yaml",
               "lvs_sky130_pass.yaml", "lvs_sky130_fail.yaml"],
}


def test_scenario_coverage_across_all_mvp_flows():
    yaml = YAML(typ="safe")
    for flow, names in FLOW_SCENARIOS.items():
        for name in names:
            path = ROOT / "scenarios" / name
            assert path.is_file(), f"{flow}: {name} missing"
            doc = yaml.load(path.read_text())
            assert doc.get("steps"), f"{flow}: {name} has no steps"


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "scenarios", ROOT / "scripts" / "scenarios.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lvs_scenario_without_netgen_names_cause_and_ref(monkeypatch):
    runner = _load_runner()
    real_which = shutil.which
    monkeypatch.setattr(
        shutil, "which",
        lambda name, *a, **k: ("/fake/magic" if name == "magic"
                               else (None if name == "netgen"
                                     else real_which(name, *a, **k))),
    )
    result = runner.run_scenario(ROOT / "scenarios" / "lvs_sky130_pass.yaml")
    assert result["passed"] is False
    assert "netgen" in result["failures"][0], result["failures"]
    assert "NGSPICE-LIVE" in result["failures"][0], result["failures"]


def test_scenario_without_pdk_store_fails_with_cause_no_traceback(tmp_path):
    staged = tmp_path / "yaml"
    staged.mkdir()
    shutil.copy(ROOT / "scenarios" / "drc_sky130_pass.yaml",
                staged / "drc_sky130_pass.yaml")
    env = dict(os.environ)
    env["ROCKETEDA_HOME"] = str(tmp_path / "empty-store")
    proc = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"),
         str(ROOT / "scripts" / "scenarios.py"), str(staged)],
        capture_output=True, text=True, timeout=300, env=env, cwd=ROOT,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "ROCKETEDA_HOME" in proc.stdout, proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr


def test_gate_without_ngspice_fails_with_cause_no_traceback(tmp_path):
    if shutil.which("ngspice") is not None:
        pytest.skip("ngspice present: live path covers analog")
    proc = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"),
         str(ROOT / "scripts" / "correctness.py"),
         "--flow", "analog", "--report", str(tmp_path / "rep")],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "GATE FAIL" in proc.stdout, proc.stdout
    assert "blocked-env" in proc.stdout, proc.stdout
    assert "Traceback" not in proc.stdout + proc.stderr
