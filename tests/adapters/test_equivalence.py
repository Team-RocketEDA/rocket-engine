"""Equivalence RED — EqyAdapter behind the ToolAdapter port.

Valid RED = `rocket_engine.adapters.equivalence` does not exist yet.
Dump-first: V1 verdict filename plus DONE line plus partition JSON;
the adapter never imports eqy.py (exit-unsafe). Live runs need eqy
on PATH (oss-cad-suite bundle) and skip loudly without it.
"""

import shutil
from pathlib import Path

import pytest

eqy_present = shutil.which("eqy") is not None
needs_eqy = pytest.mark.skipif(
    not eqy_present, reason="BLOCKED-needs-host: eqy absent"
)


def test_equivalence_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.equivalence import EqyAdapter

    assert issubclass(EqyAdapter, ToolAdapter)


def test_equivalence_capabilities_advertise_formal_eqy():
    from rocket_engine.adapters.equivalence import EqyAdapter

    caps = EqyAdapter().capabilities({})
    assert "run_formal" in caps["operations"]
    assert caps["tool"] == "eqy"


def test_equivalence_preflight_refuses_bad_operation():
    from rocket_engine.adapters.equivalence import EqyAdapter

    try:
        EqyAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_equivalence_parse_pass_verdict():
    from rocket_engine.adapters.equivalence import EqyAdapter

    native = {"exit_code": 0, "verdict_file": "PASS",
              "stdout": "EQY 00:00:01 [w] DONE (PASS, rc=0)",
              "partitions": []}
    result = EqyAdapter().parse(native)
    assert result["total"] == 0
    assert result["verdict"] == "PASS"


def test_equivalence_parse_fail_reports_violation():
    from rocket_engine.adapters.equivalence import EqyAdapter

    native = {"exit_code": 2, "verdict_file": "FAIL",
              "stdout": "EQY 00:00:02 [w] DONE (FAIL, rc=2)",
              "partitions": [{"name": "top.0", "status": "FAIL"}]}
    result = EqyAdapter().parse(native)
    assert result["total"] >= 1
    assert result["verdict"] == "FAIL"


def test_equivalence_parse_rejects_verdict_less():
    from rocket_engine.adapters.equivalence import EqyAdapter

    try:
        EqyAdapter().parse({"exit_code": 0, "stdout": "no done here"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")
