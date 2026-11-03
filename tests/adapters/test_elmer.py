"""Elmer RED — ElmerAdapter behind the ToolAdapter port (run_thermal).

Valid RED = `rocket_engine.adapters.elmer` does not exist yet, so
every test fails on ImportError. Dump-first: SaveScalars JSON/CSV
plus VTU via pyvista; the adapter reads the JSON dump first, CSV
next, deterministic NS/SS stdout last. Live runs need ElmerSolver
on PATH and skip loudly without it.
"""

import shutil
from pathlib import Path

import pytest

solver_present = shutil.which("ElmerSolver") is not None
needs_solver = pytest.mark.skipif(
    not solver_present, reason="BLOCKED-needs-host: ElmerSolver absent"
)


def test_elmer_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.elmer import ElmerAdapter

    assert issubclass(ElmerAdapter, ToolAdapter)


def test_elmer_capabilities_advertise_run_thermal():
    from rocket_engine.adapters.elmer import ElmerAdapter

    caps = ElmerAdapter().capabilities({})
    assert "run_thermal" in caps["operations"]
    assert caps["tool"] == "elmer"


def test_elmer_preflight_refuses_bad_operation():
    from rocket_engine.adapters.elmer import ElmerAdapter

    try:
        ElmerAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_elmer_preflight_refuses_missing_sif(tmp_path):
    from rocket_engine.adapters.elmer import ElmerAdapter

    job = {"operation": "run_thermal",
           "sif": str(tmp_path / "ghost.sif")}
    try:
        ElmerAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference")


def test_elmer_parse_good_dump():
    from rocket_engine.adapters.elmer import ElmerAdapter

    native = {"exit_code": 0,
              "dump": {"scalars": {"max_temp": 350.0}, "converged": True},
              "dump_file": "savescalars.json"}
    result = ElmerAdapter().parse(native)
    assert result["total"] == 0
    assert result["measurements"]


def test_elmer_parse_failed_convergence_reports_violation():
    from rocket_engine.adapters.elmer import ElmerAdapter

    native = {"exit_code": 0,
              "dump": {"scalars": {}, "converged": False},
              "dump_file": "savescalars.json"}
    result = ElmerAdapter().parse(native)
    assert result["total"] >= 1


def test_elmer_parse_rejects_dump_less():
    from rocket_engine.adapters.elmer import ElmerAdapter

    try:
        ElmerAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")
