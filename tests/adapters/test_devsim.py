"""Devsim RED — DevsimAdapter behind the ToolAdapter port (run_tcad).

Valid RED = `rocket_engine.adapters.devsim` does not exist yet, so
every test fails on ImportError. Dump-first: the driver calls
get_contact_current/get_*_model_values/solve(info=True) and dumps
JSON; the adapter parses the dump file, never stdout scraping.
Live runs need `devsim` importable (devsim==2.11.2) and skip loudly
without it (BLOCKED-needs-host, never fake-green).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import devsim  # noqa: F401

    devsim_present = True
except ImportError:
    devsim_present = False

needs_devsim = pytest.mark.skipif(
    not devsim_present, reason="BLOCKED-needs-host: devsim not importable"
)


def _job(tmp_path, **over):
    job = {"operation": "run_tcad", "script": str(tmp_path / "driver.py")}
    job.update(over)
    return job


def test_devsim_adapter_implements_tool_port(tmp_path):
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.devsim import DevsimAdapter

    assert issubclass(DevsimAdapter, ToolAdapter)


def test_devsim_capabilities_advertise_run_tcad():
    from rocket_engine.adapters.devsim import DevsimAdapter

    caps = DevsimAdapter().capabilities({})
    assert "run_tcad" in caps["operations"]
    assert caps["tool"] == "devsim"


def test_devsim_preflight_refuses_bad_operation(tmp_path):
    from rocket_engine.adapters.devsim import DevsimAdapter

    try:
        DevsimAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_devsim_preflight_missing_dependency_without_devsim(tmp_path):
    from rocket_engine.adapters.devsim import DevsimAdapter

    if devsim_present:
        pytest.skip("devsim present: live host, no gate to pin")
    try:
        DevsimAdapter().preflight(_job(tmp_path))
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "BLOCKED-needs-host" in str(exc)
    else:
        raise AssertionError("expected missing_dependency")


def test_devsim_parse_good_fixture():
    from rocket_engine.adapters.devsim import DevsimAdapter

    native = {
        "exit_code": 0,
        "dump": {
            "currents": {"drain": 1.2e-6},
            "potentials": [0.0, 0.7],
            "solve": {"converged": True, "iteration": 12},
        },
        "dump_file": "devsim_dump.json",
    }
    result = DevsimAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"]


def test_devsim_parse_bad_fixture_reports_violation():
    from rocket_engine.adapters.devsim import DevsimAdapter

    native = {
        "exit_code": 0,
        "dump": {"currents": {}, "potentials": [],
                 "solve": {"converged": False, "iteration": 50}},
        "dump_file": "devsim_dump.json",
    }
    result = DevsimAdapter().parse(native)
    assert result["total"] >= 1
    assert result["violations"][0]["severity"] == "error"


def test_devsim_parse_rejects_dump_less():
    from rocket_engine.adapters.devsim import DevsimAdapter

    try:
        DevsimAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable for missing dump")


@needs_devsim
def test_devsim_live_dump_roundtrip(tmp_path):
    from rocket_engine.adapters.devsim import DevsimAdapter

    driver = tmp_path / "driver.py"
    driver.write_text(
        "import json\n"
        "dump = {'currents': {'drain': 1e-6}, 'potentials': [0.0],\n"
        "        'solve': {'converged': True, 'iteration': 3}}\n"
        f"open({str(tmp_path / 'devsim_dump.json')!r}, 'w').write(json.dumps(dump))\n"
    )
    job = {"operation": "run_tcad", "script": str(driver),
           "workdir": str(tmp_path)}
    adapter = DevsimAdapter()
    native = adapter.execute(job)
    assert native["exit_code"] == 0
    assert adapter.parse(native)["total"] == 0
