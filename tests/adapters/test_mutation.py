"""Mutation RED — McyAdapter behind the ToolAdapter port.

Valid RED = `rocket_engine.adapters.mutation` does not exist yet.
Dump-first: database/db.sqlite3 via stdlib sqlite3 plus output.txt
streaming verdicts. Live runs need mcy on PATH and skip loudly
without it.
"""

import shutil

import pytest

mcy_present = shutil.which("mcy") is not None
needs_mcy = pytest.mark.skipif(
    not mcy_present, reason="BLOCKED-needs-host: mcy absent"
)


def test_mutation_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.mutation import McyAdapter

    assert issubclass(McyAdapter, ToolAdapter)


def test_mutation_capabilities_advertise_run_mutation():
    from rocket_engine.adapters.mutation import McyAdapter

    caps = McyAdapter().capabilities({})
    assert "run_mutation" in caps["operations"]
    assert caps["tool"] == "mcy"


def test_mutation_preflight_refuses_bad_operation():
    from rocket_engine.adapters.mutation import McyAdapter

    try:
        McyAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_mutation_parse_covered_design():
    from rocket_engine.adapters.mutation import McyAdapter

    native = {"exit_code": 0,
              "results": [{"mutation_id": 1, "result": "COVERED"},
                          {"mutation_id": 2, "result": "COVERED"}],
              "db_file": "database/db.sqlite3"}
    result = McyAdapter().parse(native)
    assert result["total"] == 0
    assert result["coverage"] == 1.0


def test_mutation_parse_uncovered_reports_violation():
    from rocket_engine.adapters.mutation import McyAdapter

    native = {"exit_code": 0,
              "results": [{"mutation_id": 1, "result": "COVERED"},
                          {"mutation_id": 2, "result": "UNCOVERED"}],
              "db_file": "database/db.sqlite3"}
    result = McyAdapter().parse(native)
    assert result["total"] >= 1


def test_mutation_parse_output_txt_lines():
    from rocket_engine.adapters.mutation import McyAdapter

    lines = McyAdapter.parse_output_txt("1 PASS\n2 FAIL\n")
    assert lines == [{"mutation_id": 1, "result": "PASS"},
                     {"mutation_id": 2, "result": "FAIL"}]


def test_mutation_parse_rejects_result_less():
    from rocket_engine.adapters.mutation import McyAdapter

    try:
        McyAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")
