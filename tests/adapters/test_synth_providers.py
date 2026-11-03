"""Synth providers RED — ghdl/amaranth additions to run_synth.

Valid RED = `rocket_engine.adapters.synth_yosys.ghdl` and
`.amaranth` do not exist yet. ghdl --synth --out=verilog feeds the
yosys flow; amaranth emits backend Verilog (generated backend HDL
does not count as mixing per CANVAS-CST v1 amendment). Amaranth is
unpinned and skips BLOCKED-needs-host when absent.
"""

import shutil

import pytest

try:
    import amaranth  # noqa: F401

    amaranth_present = True
except ImportError:
    amaranth_present = False


def test_synth_ghdl_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.synth_yosys.ghdl import GhdlSynthAdapter

    assert issubclass(GhdlSynthAdapter, ToolAdapter)


def test_synth_ghdl_capabilities():
    from rocket_engine.adapters.synth_yosys.ghdl import GhdlSynthAdapter

    caps = GhdlSynthAdapter().capabilities({})
    assert "run_synth" in caps["operations"]
    assert caps["tool"] == "ghdl"


def test_synth_ghdl_parse_stats():
    from rocket_engine.adapters.synth_yosys.ghdl import GhdlSynthAdapter

    stdout = ("Statistics for netlists:\n"
              "  gates 12 nets 30\n")
    native = {"exit_code": 0, "stdout": stdout,
              "netlist": "synth.v", "top": "top"}
    result = GhdlSynthAdapter().parse(native)
    assert result["total"] == 0
    assert result["top"] == "top"


def test_amaranth_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.synth_yosys.amaranth import AmaranthAdapter

    assert issubclass(AmaranthAdapter, ToolAdapter)


def test_amaranth_capabilities():
    from rocket_engine.adapters.synth_yosys.amaranth import AmaranthAdapter

    caps = AmaranthAdapter().capabilities({})
    assert "run_synth" in caps["operations"]
    assert caps["tool"] == "amaranth"


def test_amaranth_emit_backend_verilog(tmp_path):
    from rocket_engine.adapters.synth_yosys.amaranth import AmaranthAdapter

    if not amaranth_present:
        pytest.skip("BLOCKED-needs-host: amaranth unpinned/absent")
    out = AmaranthAdapter.emit_verilog({"top": "top"}, str(tmp_path))
    assert "module top" in out
