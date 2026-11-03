"""HDL providers RED — verilator/ghdl additions to run_hdl_test.

Valid RED = `rocket_engine.adapters.hdl_sim.verilator` and `.ghdl`
do not exist yet. Verilator uses --lint-only --diagnostics-sarif
first (SARIF file channel), ghdl uses -a/-e/-r with assert-line
parsing. Both refuse loudly without their binary (BLOCKED-needs-host
when absent; live legs run when present).
"""

import shutil

import pytest

verilator_present = shutil.which("verilator") is not None
ghdl_present = shutil.which("ghdl") is not None


def test_verilator_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    assert issubclass(VerilatorAdapter, ToolAdapter)


def test_verilator_capabilities_advertise_hdl_verilator():
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    caps = VerilatorAdapter().capabilities({})
    assert "run_hdl_test" in caps["operations"]
    assert caps["tool"] == "verilator"


def test_verilator_parse_sarif_errors():
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    sarif = {"runs": [{"results": [
        {"level": "error", "message": {"text": "syntax error"},
         "ruleId": "SYNTAX",
         "locations": [{"physicalLocation": {
             "artifactLocation": {"uri": "t.v"},
             "region": {"startLine": 3, "startColumn": 1}}}]}]}]}
    native = {"exit_code": 1, "sarif": sarif, "stderr": ""}
    result = VerilatorAdapter().parse(native)
    assert result["total"] >= 1
    assert result["violations"][0]["rule"] == "SYNTAX"


def test_verilator_parse_stderr_fallback():
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    stderr = "%Error: t.v:3:1: syntax error\n"
    native = {"exit_code": 1, "sarif": None, "stderr": stderr}
    result = VerilatorAdapter().parse(native)
    assert result["total"] >= 1


def test_ghdl_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    assert issubclass(GhdlAdapter, ToolAdapter)


def test_ghdl_capabilities_advertise_hdl_ghdl():
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    caps = GhdlAdapter().capabilities({})
    assert "run_hdl_test" in caps["operations"]
    assert caps["tool"] == "ghdl"


def test_ghdl_parse_assert_lines():
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    stdout = "tb.vhdl:42:7:@10ns:(assertion error): counter mismatch\n"
    native = {"exit_code": 1, "stdout": stdout, "stderr": ""}
    result = GhdlAdapter().parse(native)
    assert result["total"] >= 1
    assert result["violations"][0]["file"] == "tb.vhdl"


def test_ghdl_parse_clean_run():
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    native = {"exit_code": 0, "stdout": "simulation finished\n",
              "stderr": ""}
    result = GhdlAdapter().parse(native)
    assert result["total"] == 0
