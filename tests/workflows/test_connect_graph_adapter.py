"""CONNECT-GRAPH adapter RED — run_connectivity/run_erc behind ToolAdapter.

The adapter is pure Python (no subprocess): preflight validates the
job, execute extracts plus emits, parse normalizes ERC findings and
carries netlists as measurements. It never names a net itself — every
name flows from the shared `net_name()` authority. Valid RED = the
import itself fails.
"""

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "connect_graph_demo.json"


def _demo():
    return json.loads(FIXTURE.read_text())


def _adapter():
    from rocket_engine.adapters.connectivity import ConnectivityAdapter

    return ConnectivityAdapter()


def test_capabilities_name_both_operations():
    from rocket_engine.adapters.connectivity import (  # RED: missing module
        OPERATIONS,
        TOOL,
    )

    assert TOOL == "connectgraph"
    assert tuple(OPERATIONS) == ("run_connectivity", "run_erc")
    caps = _adapter().capabilities(target=None)
    assert caps == {"operations": ["run_connectivity", "run_erc"], "tool": "connectgraph"}


def test_preflight_rejects_bad_jobs():
    from rocket_engine.adapters.errors import AdapterError

    adapter = _adapter()
    for job, code in (
        ({"operation": "run_drc"}, "unsupported_operation"),
        ({"operation": "run_connectivity"}, "invalid_command"),
        ({"operation": "run_connectivity", "schematic": {"cell": "x"}}, None),
        (
            {"operation": "run_erc", "schematic": {"cell": "x"}, "languages": ["tcl"]},
            "invalid_command",
        ),
    ):
        try:
            checked = adapter.preflight(job)
        except AdapterError as exc:
            assert exc.code == code, (job, exc.code)
        else:
            assert code is None, job
            assert checked["operation"] == job["operation"]


def test_connectivity_round_trip_carries_netlists():
    adapter = _adapter()
    job = {"operation": "run_connectivity", "schematic": _demo()}
    native = adapter.execute(job)
    assert native["exit_code"] == 0
    result = adapter.parse(native)
    assert result["total"] == 0
    assert result["violations"] == []
    assert set(result["measurements"]["netlists"]) == {"spice", "verilog", "vhdl"}
    assert result["measurements"]["nets"] == ["A", "Y", "net1"]
    assert "X1 A net1 inv" in result["measurements"]["netlists"]["spice"]


def test_short_is_an_error_in_both_operations():
    adapter = _adapter()
    schematic = _demo()
    schematic["labels"].append({"name": "Z", "xy": [-10, 10]})
    for operation in ("run_connectivity", "run_erc"):
        result = adapter.parse(
            adapter.execute({"operation": operation, "schematic": schematic})
        )
        shorts = [v for v in result["violations"] if v["rule"] == "connectivity.short"]
        assert len(shorts) == 1
        assert shorts[0]["severity"] == "error"
        assert "A" in shorts[0]["message"] and "Z" in shorts[0]["message"]


def test_erc_escalates_unconnected_pins():
    adapter = _adapter()
    schematic = _demo()
    schematic["pins"].append({"instance": "X1", "pin": "NC", "xy": [400, 400]})
    calm = adapter.parse(
        adapter.execute({"operation": "run_connectivity", "schematic": schematic})
    )
    strict = adapter.parse(
        adapter.execute({"operation": "run_erc", "schematic": schematic})
    )
    calm_nc = [v for v in calm["violations"] if v["rule"] == "connectivity.unconnected_pin"]
    strict_nc = [v for v in strict["violations"] if v["rule"] == "connectivity.unconnected_pin"]
    assert len(calm_nc) == len(strict_nc) == 1
    assert calm_nc[0]["severity"] == "warning"
    assert strict_nc[0]["severity"] == "error"


def test_findings_use_net_name_authority():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    adapter = _adapter()
    schematic = _demo()
    schematic["labels"].append({"name": "Z", "xy": [-10, 10]})
    conn = prepare_netlist_structs(schematic).connectivity
    result = adapter.parse(
        adapter.execute({"operation": "run_connectivity", "schematic": schematic})
    )
    for violation in result["violations"]:
        assert violation["net"] == conn.net_name(violation["net_id"])


def test_malformed_schematic_is_invalid_command():
    from rocket_engine.adapters.errors import AdapterError

    adapter = _adapter()
    try:
        adapter.execute(
            {"operation": "run_connectivity", "schematic": {"cell": "x", "wires": [[["oops"]]]}}
        )
    except AdapterError as exc:
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("malformed schematic must raise invalid_command")
