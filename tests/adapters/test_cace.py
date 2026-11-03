"""CACE RED — CaceAdapter behind the ToolAdapter port.

Valid RED = `rocket_engine.adapters.cace` does not exist yet.
Dump-first: subprocess `cace` CLI gated on exit code, verdicts read
from summary.md plus simulation_summary.csv. Live runs need cace
2.13.0 and skip loudly without it (absent on this host).
"""

import shutil

import pytest

cace_present = shutil.which("cace") is not None
needs_cace = pytest.mark.skipif(
    not cace_present, reason="BLOCKED-needs-host: cace absent"
)


def test_cace_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.cace import CaceAdapter

    assert issubclass(CaceAdapter, ToolAdapter)


def test_cace_capabilities_advertise_characterize():
    from rocket_engine.adapters.cace import CaceAdapter

    caps = CaceAdapter().capabilities({})
    assert "run_characterize" in caps["operations"]
    assert caps["tool"] == "cace"


def test_cace_preflight_refuses_bad_operation():
    from rocket_engine.adapters.cace import CaceAdapter

    try:
        CaceAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_cace_preflight_missing_dependency_without_cace(tmp_path):
    from rocket_engine.adapters.cace import CaceAdapter

    if cace_present:
        pytest.skip("cace present: live host, no gate to pin")
    (tmp_path / "ds.yaml").write_text("name: t\n")
    job = {"operation": "run_characterize",
           "datasheet": str(tmp_path / "ds.yaml")}
    try:
        CaceAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
        assert "BLOCKED-needs-host" in str(exc)
    else:
        raise AssertionError("expected missing_dependency")


def test_cace_parse_pass_summary():
    from rocket_engine.adapters.cace import CaceAdapter

    summary = ("| dc_gain | ngspice | gain | - | - | - | - | - | - "
               "| Pass ✅ |\n")
    native = {"exit_code": 0, "summary_md": summary, "run_dir": "RUN_x"}
    result = CaceAdapter().parse(native)
    assert result["total"] == 0


def test_cace_parse_fail_summary_reports_violation():
    from rocket_engine.adapters.cace import CaceAdapter

    summary = ("| dc_gain | ngspice | gain | - | - | - | - | - | - "
               "| Fail ❌ |\n")
    native = {"exit_code": 2, "summary_md": summary, "run_dir": "RUN_x"}
    result = CaceAdapter().parse(native)
    assert result["total"] >= 1


def test_cace_parse_rejects_summary_less():
    from rocket_engine.adapters.cace import CaceAdapter

    try:
        CaceAdapter().parse({"exit_code": 0})
    except Exception as exc:
        assert getattr(exc, "code", None) == "runner_unavailable"
    else:
        raise AssertionError("expected runner_unavailable")
