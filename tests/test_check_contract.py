"""Contract drift check: stub shapes vs engine schemas (FUEL-CONTRACT).

scripts/check_contract.py is stdlib-only and runnable from either
repo: it extracts mcp-stub tool shapes by AST, resolves the overlap
map's engine refs against docs/contract.json, and fails loudly naming
the skewed field (or tool, or stale pin). Fixture stubs pin the
mechanics; the live test proves the check is green against the real
fuel checkout whenever it sits beside the engine.
"""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fuel_contract"


def _load_checker():
    # RED: scripts/check_contract.py does not exist yet.
    spec = importlib.util.spec_from_file_location(
        "check_contract", ROOT / "scripts" / "check_contract.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_artifact():
    # RED: docs/contract.json does not exist yet.
    return json.loads((ROOT / "docs" / "contract.json").read_text())


def _live_stub_server():
    """Real mcp-stub server.py beside this checkout, if present."""
    candidates = [
        ROOT.parent / "rocket_fuel" / "mcp-stub" / "src" / "rocket_stub" / "server.py",
        ROOT.parent / "mcp-stub" / "src" / "rocket_stub" / "server.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def test_extractor_reads_tool_signatures_and_response_keys():
    checker = _load_checker()
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_ok.py")
    assert sorted(shapes) == ["get_job_status", "get_logs", "run_job"]
    assert shapes["run_job"]["args"]["kind"]["required"] is True
    assert shapes["run_job"]["args"]["hypothesis"]["required"] is False
    assert shapes["get_logs"]["args"]["run_id"]["required"] is True
    assert "run_id" in shapes["run_job"]["response_keys"]
    assert "run_id" in shapes["get_job_status"]["response_keys"]
    assert "run_id" in shapes["get_logs"]["response_keys"]


def test_drift_green_on_matching_fixture():
    checker = _load_checker()
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_ok.py")
    assert checker.drift_errors(_read_artifact(), shapes) == []


def test_skewed_request_field_fails_naming_field():
    checker = _load_checker()
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_skewed_request.py")
    errors = checker.drift_errors(_read_artifact(), shapes)
    assert errors != []
    assert "run_id" in "\n".join(errors)
    assert "get_logs" in "\n".join(errors)


def test_skewed_response_field_fails_naming_field():
    checker = _load_checker()
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_skewed_response.py")
    errors = checker.drift_errors(_read_artifact(), shapes)
    assert errors != []
    assert "run_id" in "\n".join(errors)
    assert "run_job" in "\n".join(errors)


def test_removed_tool_fails_naming_tool():
    checker = _load_checker()
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_missing_tool.py")
    errors = checker.drift_errors(_read_artifact(), shapes)
    assert errors != []
    assert "get_job_status" in "\n".join(errors)


def test_engine_ref_removed_fails_naming_field():
    checker = _load_checker()
    artifact = copy.deepcopy(_read_artifact())
    artifact["envelopes"]["run_completion"]["keys"].remove("run_id")
    shapes = checker.extract_stub_shapes(FIXTURES / "stub_ok.py")
    errors = checker.drift_errors(artifact, shapes)
    assert errors != []
    assert "run_id" in "\n".join(errors)


def test_pin_ok_passes_and_stale_fails():
    checker = _load_checker()
    artifact = _read_artifact()
    pin = {
        "contract_version": artifact["contract_version"],
        "schema_sha256": artifact["schema_sha256"],
    }
    assert checker.pin_errors(artifact, pin) == []
    stale = dict(pin, schema_sha256="0" * 64)
    errors = checker.pin_errors(artifact, stale)
    assert errors != []
    assert artifact["schema_sha256"] in "\n".join(errors)


def test_pin_missing_warns_but_stays_green():
    checker = _load_checker()
    assert checker.pin_errors(_read_artifact(), None) == []
    assert "contract.pin" in checker.pin_warning()


def test_discovery_finds_engine_root():
    checker = _load_checker()
    assert checker.find_engine_root() == ROOT


def test_live_drift_green_against_current_fuel():
    server = _live_stub_server()
    if server is None:
        pytest.skip("no fuel checkout beside the engine")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_contract.py"),
            "--engine-root",
            str(ROOT),
            "--stub-root",
            str(server.parents[3]),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "contract OK" in proc.stdout
