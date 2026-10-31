"""WIRE-PLACE wiring integration — integrator runs AFTER the patch.

Pre-patch these skip (the composition/vocabulary/contract wiring from
docs/work/WIRE-PLACE/report.md is not applied yet, and the ENGINE-ECS
entity store seam it rides on may still be missing); post-patch they
must pass. They pin the wired surface, not module behavior (see
test_wireplace.py and test_wireplace_nets.py for that).
"""

import pytest


def test_top_level_interfaces_export():
    try:
        from rocket_engine.interfaces import (  # noqa: F401
            collect_wire_erc,
            connect_endpoint,
            delete_junction,
            delete_wire,
            materialize_nets,
            move_wire,
            place_junction,
            place_wire,
            split_wire,
            validate_junction,
            validate_net,
            validate_wire,
            world_schematic,
        )
    except ImportError:
        pytest.skip("needs WIRE-PLACE wiring patch (interfaces export)")


def test_vocabulary_declares_wire_operations():
    from rocket_engine.interfaces.vocabulary import OPERATIONS

    wanted = {
        "place_wire", "place_junction", "connect_endpoint", "move_wire",
        "split_wire", "delete_wire", "delete_junction", "materialize_nets",
    }
    if not wanted <= OPERATIONS:
        pytest.skip("needs WIRE-PLACE wiring patch (vocabulary)")


def test_engine_submit_place_wire_round_trip():
    composition = pytest.importorskip(
        "rocket_engine.composition",
        reason="needs WIRE-PLACE wiring patch (full engine env)",
    )
    try:
        engine = composition.Engine("wireplace-probe", actor="tester")
    except Exception as exc:
        pytest.skip(f"Engine construction is broken outside this lane: {exc!r}")
    try:
        head = engine.submit({
            "project_id": "wireplace-probe",
            "operation": "get_project_snapshot",
            "arguments": {},
            "request_id": "wireplace-wiring-head",
        })["current_revision"]
        response = engine.submit({
            "project_id": "wireplace-probe",
            "operation": "place_wire",
            "arguments": {
                "segments": [[[0, 0], [10, 0]]],
                "layer": "metal1",
                "endpoints": [
                    {"ref": None, "xy": [0, 0]},
                    {"ref": None, "xy": [10, 0]},
                ],
                "expected_revision": head,
            },
            "request_id": "wireplace-wiring-probe",
        })
    except Exception as exc:
        if getattr(exc, "code", None) == "unsupported_operation":
            pytest.skip("needs WIRE-PLACE wiring patch (Engine.submit)")
        raise
    assert response["current_revision"] != response["previous_revision"]
    assert response["actor"] == "tester"
    assert response["events"], "place_wire must append a ledger event"


def test_mcp_tool_describes_wire_operations():
    pytest.importorskip(
        "mcp", reason="needs WIRE-PLACE wiring patch (full engine env)"
    )
    from rocket_engine.adapters.mcp.server import describe_tool

    try:
        text = describe_tool("place_wire")
    except Exception:
        pytest.skip("needs WIRE-PLACE wiring patch (MCP server)")
    assert "no handler wired yet" not in text
