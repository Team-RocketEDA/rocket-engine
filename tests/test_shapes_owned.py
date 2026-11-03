"""Owned-adapter result shapes + structured escapes (SHAPE/ESCAPE).

Pins the cross-adapter contract for run_digital_flow, run_timing,
run_synth, run_hdl_test, run_syntax, and run_formal without running
any tool: every violation carries rule/severity/message with FLAT
location keys only, and every verdict-less output escapes loudly
instead of parsing as clean.
"""

import pytest

SEVERITIES = {"error", "warning"}
LOCATION_KEYS = {"file", "line", "col", "sim_time"}


def _check_shape(result):
    """Assert the violation/escape shape of one parsed result."""
    assert isinstance(result["total"], int)
    assert result["total"] == len(result["violations"])
    for violation in result["violations"]:
        assert set(violation) >= {"rule", "severity", "message"}
        assert violation["severity"] in SEVERITIES
        assert isinstance(violation["rule"], str) and violation["rule"]
        assert isinstance(violation["message"], str) and violation["message"]
        assert "location" not in violation
        for key in LOCATION_KEYS & set(violation):
            assert isinstance(violation[key], (str, int))


def test_shapes_digital_flow_failed_run():
    """Digital-flow failures shape with stage-named error findings."""
    from rocket_engine.adapters.digital_flow import LibrelaneFlowAdapter

    result = LibrelaneFlowAdapter().parse({"exit_code": 1, "forced": []})
    _check_shape(result)
    assert result["total"] >= 1
    assert any(v["severity"] == "error" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        LibrelaneFlowAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_shapes_timing_failed_run():
    """Timing failures shape with sta_error findings."""
    from rocket_engine.adapters.timing_sta import OpenStaTimingAdapter

    result = OpenStaTimingAdapter().parse({"exit_code": 1, "log": ""})
    _check_shape(result)
    assert any(v["rule"] == "sta_error" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        OpenStaTimingAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_shapes_synth_failed_run():
    """Synth failures shape with synth_error findings."""
    from rocket_engine.adapters.synth_yosys import YosysSynthAdapter

    result = YosysSynthAdapter().parse(
        {"exit_code": 1, "log": "", "stat": "", "netlist": None}
    )
    _check_shape(result)
    assert any(v["rule"] == "synth_error" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        YosysSynthAdapter().parse({})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_shapes_hdl_failed_compile():
    """HDL compile failures shape with flat file/line locations."""
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    result = HdlSimAdapter().parse(
        {"compile": {"exit_code": 1, "stdout": "", "stderr": ""}}
    )
    _check_shape(result)
    assert any(v["rule"] == "compile" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        HdlSimAdapter().parse(
            {
                "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
                "run": None,
            }
        )
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_shapes_syntax_error_diag():
    """Syntax diagnostics shape with file/line/col locations."""
    from rocket_engine.adapters.syntax import SyntaxAdapter

    result = SyntaxAdapter().parse(
        {
            "stdout": "x.v:1:2: error: boom\n"
            "Build failed: 1 errors, 0 warnings\n",
            "stderr": "",
        }
    )
    _check_shape(result)
    assert any(v["severity"] == "error" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        SyntaxAdapter().parse({"stdout": "", "stderr": ""})
    assert getattr(caught.value, "code", None) == "runner_unavailable"


def test_shapes_formal_timeout_and_verdict_less(tmp_path):
    """Formal timeouts shape; verdict-less output escapes loudly."""
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter

    result = FormalSbyAdapter().parse({"timed_out": True, "timeout_s": 30})
    _check_shape(result)
    assert any(v["rule"] == "formal_timeout" for v in result["violations"])
    with pytest.raises(Exception) as caught:
        FormalSbyAdapter().parse(
            {"timed_out": False, "stdout": "", "workdir": str(tmp_path)}
        )
    assert getattr(caught.value, "code", None) == "runner_unavailable"
