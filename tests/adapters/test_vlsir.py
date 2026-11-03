"""VLSIR RED — VlsirAdapter behind the ToolAdapter port.

Valid RED = `rocket_engine.adapters.vlsir` does not exist yet.
Dump-first: bindings for READING (`vlsirtools.netlist` for netlist
text, SimResult proto/numpy for sims); execution stays subprocess.
Live sims need a backend (ngspice/xyce/spectre) and skip loudly.
"""

import pytest


def test_vlsir_adapter_implements_tool_port():
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.vlsir import VlsirAdapter

    assert issubclass(VlsirAdapter, ToolAdapter)


def test_vlsir_capabilities_advertise_generate_views():
    from rocket_engine.adapters.vlsir import VlsirAdapter

    caps = VlsirAdapter().capabilities({})
    assert "generate_views" in caps["operations"]
    assert caps["tool"] == "vlsir"


def test_vlsir_preflight_refuses_bad_operation():
    from rocket_engine.adapters.vlsir import VlsirAdapter

    try:
        VlsirAdapter().preflight({"operation": "run_spice"})
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_operation"
    else:
        raise AssertionError("expected unsupported_operation")


def test_vlsir_emit_netlist_deterministic():
    from rocket_engine.adapters.vlsir import VlsirAdapter

    pkg = {"name": "top", "ports": ["a", "b"],
           "instances": [{"name": "x1", "cell": "nmos",
                          "conns": ["a", "b"]}], "params": {}}
    first = VlsirAdapter.emit_netlist(pkg, fmt="spice")
    second = VlsirAdapter.emit_netlist(pkg, fmt="spice")
    assert first == second
    assert ".SUBCKT top" in first


def test_vlsir_parse_good_simresult():
    from rocket_engine.adapters.vlsir import VlsirAdapter

    native = {"exit_code": 0,
              "results": {"op": {"vout": 1.8}},
              "netlist": "*.SUBCKT top*"}
    result = VlsirAdapter().parse(native)
    assert result["total"] == 0


def test_vlsir_parse_sim_error_reports_violation():
    from rocket_engine.adapters.vlsir import VlsirAdapter

    native = {"exit_code": 1, "stdout": "sim failed",
              "stderr": "SimError", "rundir": "rundir"}
    result = VlsirAdapter().parse(native)
    assert result["total"] >= 1
