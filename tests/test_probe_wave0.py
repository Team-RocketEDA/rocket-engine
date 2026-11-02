"""Wave-0 env probe (cleanup plan step 1).

The probe reports the ticket-work environment, never fixes it: EDA
binaries, venv imports, pymeep env, PDK dirs, uv.lock pins, and
host-only capabilities (fuse/userns/build tools). Tests assert probe
*behavior* (stable across machines), not env state; the live run is
the acceptance check, green on a provisioned host.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "scripts" / "probe_wave0.py"


def load_probe():
    spec = importlib.util.spec_from_file_location("probe_wave0", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_probe(*args):
    return subprocess.run(
        [sys.executable, str(PROBE), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_probe_module_loads_and_lists_checks():
    mod = load_probe()
    checks = mod.CHECKS
    assert len(checks) >= 20
    ids = [c["id"] for c in checks]
    for want in ("bin.yosys", "bin.klayout", "py.sax", "py.pyslang",
                 "pymeep.import", "pdk.sky130A", "pin.amaranth",
                 "cap.fuse", "cap.userns"):
        assert want in ids
    for c in checks:
        assert c["kind"] in ("binary", "binary-klayout", "slang_flags",
                             "pyimport", "pymeep", "pdk", "pin",
                             "capability")
        assert isinstance(c["required"], bool)


def test_probe_json_is_machine_readable():
    proc = run_probe("--json")
    assert proc.returncode in (0, 1)
    payload = json.loads(proc.stdout)
    assert "checks" in payload and "summary" in payload
    assert payload["summary"]["total"] == len(payload["checks"])
    for row in payload["checks"]:
        assert row["status"] in ("ok", "missing", "host-only")
        assert row["id"] and "detail" in row


def test_probe_table_lists_every_check():
    proc = run_probe()
    assert proc.returncode in (0, 1)
    for want in ("bin.yosys", "py.gdsfactory", "pdk.sky130A",
                 "pin.vlsirtools", "cap.fuse"):
        assert want in proc.stdout
    assert "host-only" in proc.stdout or "HOST-ONLY" in proc.stdout


def test_probe_strict_fails_on_host_only():
    proc = run_probe("--json", "--strict")
    assert proc.returncode in (0, 1)
    payload = json.loads(proc.stdout)
    host_only = [r for r in payload["checks"]
                 if r["status"] == "host-only"]
    if host_only and payload["summary"]["missing_required"] == 0:
        assert proc.returncode == 1


def test_probe_never_crashes_on_missing_tool():
    mod = load_probe()
    row = mod.run_check({"id": "bin.nope", "kind": "binary",
                         "target": "definitely-not-a-binary-xyz",
                         "required": True, "host_only": False})
    assert row["status"] == "missing"
    assert "definitely-not-a-binary-xyz" in row["detail"]


def test_wave0_pins_locked():
    """uv.lock pins every wave-0 addition (step-1 acceptance)."""
    lock = (ROOT / "uv.lock").read_text()
    for pkg in ("sax", "circulax", "meow-sim", "gdsfactory",
                "pyslang", "pywellen", "vlsirtools", "amaranth",
                "cace", "devsim"):
        assert f'name = "{pkg}"' in lock, f"{pkg} not in uv.lock"


def test_wave0_groups_declared():
    """New libs live in dependency groups, base sync stays lean."""
    pyproject = (ROOT / "pyproject.toml").read_text()
    for pkg in ("pyslang", "pywellen", "vlsirtools", "amaranth"):
        assert pkg in pyproject, f"{pkg} not in pyproject groups"
