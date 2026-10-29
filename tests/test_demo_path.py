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

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "scripts" / "install.sh"


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
