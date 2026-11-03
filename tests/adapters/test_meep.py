"""Meep RED — MeepAdapter behind the ToolAdapter port (run_optical).

Valid RED = `rocket_engine.adapters.meep` does not exist yet, so
every test fails on ImportError. Dump-first: subprocess driver uses
in-API flux/DFT/Harminv plus HDF5 via h5py; the adapter reads the
JSON dump plus deterministic S1 telemetry as fallback. Live runs
need `meep` importable (pymeep 1.35.0) and skip loudly without it.
"""

import shutil
from pathlib import Path

import pytest

try:
    import meep  # noqa: F401

    meep_present = True
except ImportError:
    meep_present = False

needs_meep = pytest.mark.skipif(
    not meep_present, reason="BLOCKED-needs-host: meep not importable"
)


def test_meep_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.meep import MeepAdapter

    assert issubclass(MeepAdapter, ToolAdapter)


def test_meep_capabilities_advertise_run_optical():
    from rocket_engine.adapters.meep import MeepAdapter

    caps = MeepAdapter().capabilities({})
    assert "run_optical" in caps["operations"]
    assert caps["tool"] == "meep"


def test_meep_preflight_refuses_bad_operation():
    from rocket_engine.adapters.meep import MeepAdapter

    try:
        MeepAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_meep_preflight_missing_dependency_without_meep(tmp_path):
    from rocket_engine.adapters.meep import MeepAdapter

    if meep_present:
        pytest.skip("meep present: live host, no gate to pin")
    (tmp_path / "driver.py").write_text("import meep\n")
    job = {"operation": "run_optical",
           "script": str(tmp_path / "driver.py")}
    try:
        MeepAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "BLOCKED-needs-host" in str(exc)
    else:
        raise AssertionError("expected missing_dependency")


def test_meep_parse_good_dump():
    from rocket_engine.adapters.meep import MeepAdapter

    native = {"exit_code": 0,
              "dump": {"fluxes": [0.5], "modes": [],
                       "transmission": 0.9},
              "dump_file": "meep_dump.json"}
    result = MeepAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"]


def test_meep_parse_bad_dump_reports_violation():
    from rocket_engine.adapters.meep import MeepAdapter

    native = {"exit_code": 1, "stdout": "crashed, no telemetry",
              "dump": None, "dump_file": "meep_dump.json"}
    result = MeepAdapter().parse(native)
    assert result["total"] >= 1


def test_meep_parse_rejects_verdict_less():
    from rocket_engine.adapters.meep import MeepAdapter

    try:
        MeepAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")


@needs_meep
def test_meep_live_driver_roundtrip(tmp_path):
    from rocket_engine.adapters.meep import MeepAdapter

    driver = tmp_path / "driver.py"
    driver.write_text("import json; json.dump({'fluxes': [1.0],"
                      " 'modes': [], 'transmission': 1.0},"
                      f" open({str(tmp_path / 'meep_dump.json')!r}, 'w'))\n")
    job = {"operation": "run_optical", "script": str(driver),
           "workdir": str(tmp_path)}
    native = MeepAdapter().execute(job)
    assert MeepAdapter().parse(native)["total"] == 0
