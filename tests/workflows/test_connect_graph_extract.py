"""CONNECT-GRAPH extraction RED — one shared connectivity graph.

`prepare_netlist_structs` is the xschem lesson ported over: wires and
instance pins coalesce through a spatial hash, labels propagate net
names, unlabeled nets/instances get stable generated names,
`lvs_ignore` instances stay out of the graph, and results cache only
behind an explicit run key. Valid RED = the import itself fails.
"""

import copy
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "connect_graph_demo.json"


def _demo():
    return json.loads(FIXTURE.read_text())


def test_import_surface_exists():
    from rocket_engine.workflows import connectgraph  # RED: missing module

    assert callable(connectgraph.prepare_netlist_structs)
    assert callable(getattr(connectgraph, "net_name", None)) or hasattr(
        connectgraph, "Connectivity"
    )


def test_pins_sharing_wire_share_one_net():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    structs = prepare_netlist_structs(_demo())
    mid_x1 = structs.connectivity.pin_net("X1", "Y")
    mid_x2 = structs.connectivity.pin_net("X2", "A")
    assert mid_x1 == mid_x2
    assert structs.connectivity.pin_net("X1", "A") != mid_x1


def test_labels_propagate_names():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    conn = prepare_netlist_structs(_demo()).connectivity
    assert conn.net_name(conn.pin_net("X1", "A")) == "A"
    assert conn.net_name(conn.pin_net("X2", "Y")) == "Y"


def test_unlabeled_net_gets_stable_name():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    first = prepare_netlist_structs(_demo()).connectivity
    mid = first.pin_net("X1", "Y")
    assert first.net_name(mid) == "net1"
    # Fresh extraction and shuffled input order must agree byte for byte.
    again = prepare_netlist_structs(_demo()).connectivity
    assert again.net_name(again.pin_net("X1", "Y")) == "net1"
    shuffled = _demo()
    shuffled["wires"] = list(reversed(shuffled["wires"]))
    shuffled["pins"] = list(reversed(shuffled["pins"]))
    third = prepare_netlist_structs(shuffled).connectivity
    assert third.net_name(third.pin_net("X1", "Y")) == "net1"


def test_crossing_wire_interiors_do_not_connect():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    schematic = {
        "cell": "cross",
        "wires": [[[0, -5], [0, 5]], [[-5, 0], [5, 0]]],
        "pins": [
            {"instance": "X1", "pin": "A", "xy": [0, -5]},
            {"instance": "X2", "pin": "A", "xy": [-5, 0]},
        ],
        "labels": [],
        "instances": [
            {"name": "X1", "symbol": "s"},
            {"name": "X2", "symbol": "s"},
        ],
        "symbols": {"s": {"pins": ["A"]}},
    }
    conn = prepare_netlist_structs(schematic).connectivity
    assert conn.pin_net("X1", "A") != conn.pin_net("X2", "A")


def test_t_junction_endpoint_on_segment_connects():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    schematic = {
        "cell": "tee",
        "wires": [[[0, 0], [10, 0]], [[5, 0], [5, 8]]],
        "pins": [
            {"instance": "X1", "pin": "A", "xy": [0, 0]},
            {"instance": "X2", "pin": "A", "xy": [5, 8]},
        ],
        "labels": [{"name": "T", "xy": [10, 0]}],
        "instances": [
            {"name": "X1", "symbol": "s"},
            {"name": "X2", "symbol": "s"},
        ],
        "symbols": {"s": {"pins": ["A"]}},
    }
    conn = prepare_netlist_structs(schematic).connectivity
    assert conn.pin_net("X1", "A") == conn.pin_net("X2", "A")
    assert conn.net_name(conn.pin_net("X1", "A")) == "T"


def test_lvs_ignore_excludes_instance_pins():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    schematic = _demo()
    schematic["instances"].append(
        {"name": "X9", "symbol": "inv", "attrs": {"lvs_ignore": True}}
    )
    schematic["pins"].extend(
        [
            {"instance": "X9", "pin": "A", "xy": [100, 100]},
            {"instance": "X9", "pin": "Y", "xy": [120, 100]},
        ]
    )
    schematic["wires"].append([[100, 100], [120, 100]])
    structs = prepare_netlist_structs(schematic)
    assert structs.connectivity.pin_net("X9", "A") is None
    assert structs.connectivity.pin_net("X9", "Y") is None
    assert "X9" in structs.ignored
    assert all(i.name != "X9" for i in structs.instances)


def test_conflicting_labels_form_a_named_short():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    schematic = _demo()
    schematic["labels"].append({"name": "Z", "xy": [-10, 10]})
    conn = prepare_netlist_structs(schematic).connectivity
    assert len(conn.shorts) == 1
    short = conn.shorts[0]
    assert sorted(short["labels"]) == ["A", "Z"]
    # Deterministic pick: sorted-first wins, every run agrees.
    assert conn.net_name(short["net"]) == "A"


def test_net_name_rejects_unknown_id():
    from rocket_engine.workflows.connectgraph import (
        ConnectGraphError,
        prepare_netlist_structs,
    )

    conn = prepare_netlist_structs(_demo()).connectivity
    try:
        conn.net_name(9999)
    except ConnectGraphError:
        pass
    else:
        raise AssertionError("net_name(9999) must raise ConnectGraphError")


def test_cache_needs_an_explicit_run_key():
    from rocket_engine.workflows.connectgraph import (
        invalidate_run,
        prepare_netlist_structs,
    )

    schematic = _demo()
    # No key, no cache: every call rebuilds.
    assert prepare_netlist_structs(schematic) is not prepare_netlist_structs(schematic)
    # Same key reuses the identical object ...
    first = prepare_netlist_structs(schematic, run_key="run-1")
    assert prepare_netlist_structs(schematic, run_key="run-1") is first
    # ... but a changed schematic under the same key rebuilds loudly,
    # never serving stale nets.
    changed = copy.deepcopy(schematic)
    changed["labels"].append({"name": "EXTRA", "xy": [20, 10]})
    rebuilt = prepare_netlist_structs(changed, run_key="run-1")
    assert rebuilt is not first
    assert rebuilt.connectivity.net_name(rebuilt.connectivity.pin_net("X1", "Y")) == "EXTRA"
    assert invalidate_run("run-1") == 1
    assert invalidate_run("run-1") == 0


def test_unnamed_instance_gets_stable_name():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    schematic = _demo()
    schematic["instances"].append({"symbol": "inv"})
    schematic["pins"].extend(
        [
            {"instance": "", "pin": "A", "xy": [200, 200]},
            {"instance": "", "pin": "Y", "xy": [210, 200]},
        ]
    )
    # Pins keyed by position: the unnamed instance claims pins whose
    # instance field is empty once names are assigned.
    first = prepare_netlist_structs(schematic)
    names = sorted(i.name for i in first.instances)
    assert names == ["X1", "X2", "X3"]


def test_malformed_schematic_raises_typed_error():
    from rocket_engine.workflows.connectgraph import (
        ConnectGraphError,
        prepare_netlist_structs,
    )

    for bad in (
        {"cell": "bad", "wires": [[["oops"]]]},
        {"cell": "bad", "pins": [{"instance": "X1"}]},
        {"cell": "bad", "ports": [{"name": "GHOST", "direction": "input"}]},
        {"cell": "bad", "ports": [{"name": "A", "direction": "sideways"}]},
        {"cell": "bad", "instances": [{"name": "X1", "symbol": "ghost"}]},
    ):
        try:
            prepare_netlist_structs(bad)
        except ConnectGraphError:
            continue
        raise AssertionError(f"malformed schematic accepted: {bad!r}")


def test_erc_findings_share_the_net_name_authority():
    from rocket_engine.workflows.connectgraph import (
        erc_findings,
        prepare_netlist_structs,
    )

    schematic = _demo()
    schematic["labels"].append({"name": "Z", "xy": [-10, 10]})
    schematic["pins"].append({"instance": "X1", "pin": "NC", "xy": [400, 400]})
    conn = prepare_netlist_structs(schematic).connectivity
    findings = erc_findings(conn)
    kinds = {f["rule"] for f in findings}
    assert "connectivity.short" in kinds
    assert "connectivity.unconnected_pin" in kinds
    by_net = {n.id: n.name for n in conn.nets}
    for finding in findings:
        assert finding["net"] == by_net[finding["net_id"]]
        assert finding["net"] == conn.net_name(finding["net_id"])
