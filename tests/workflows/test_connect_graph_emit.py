"""CONNECT-GRAPH emitter RED — raw IR plus one post-pass per language.

Emitters never walk the graph: `to_raw_ir` resolves pins to canonical
net names through the shared `net_name()` authority plus the 4-level
format chain, and each language printer only arranges raw lines and
runs its small textual post-pass. Goldens pin byte-stable output;
the identity test proves all three languages name the same nets.
Valid RED = the import itself fails.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
DEMO = json.loads((FIXTURES / "connect_graph_demo.json").read_text())


def _structs(schematic=None):
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs

    return prepare_netlist_structs(schematic if schematic is not None else DEMO)


def test_raw_ir_resolves_pins_through_net_name():
    from rocket_engine.workflows.connectgraph_emit import to_raw_ir

    raw = to_raw_ir(_structs())
    assert raw["raw_ir_version"] == 1
    assert raw["cell"] == "top"
    assert [n["name"] for n in raw["nets"]] == ["A", "Y", "net1"]
    by_name = {i["name"]: i for i in raw["instances"]}
    assert by_name["X1"]["pins"] == [
        {"pin": "A", "net": "A"},
        {"pin": "Y", "net": "net1"},
    ]
    assert by_name["X2"]["pins"] == [
        {"pin": "A", "net": "net1"},
        {"pin": "Y", "net": "Y"},
    ]
    # Raw IR is plain data: it must survive a JSON round trip.
    assert json.loads(json.dumps(raw)) == raw


def test_format_chain_prefers_first_available_level():
    from rocket_engine.workflows.connectgraph_emit import resolve_format

    levels = ("instance_custom", "symbol_custom", "instance_format", "symbol_format")
    for winner in range(4):
        instance, symbol = {"custom": {}, "format": {}}, {"custom": {}, "format": {}}
        if winner == 0:
            instance["custom"]["spice"] = "I-CUSTOM"
        if winner <= 1:
            symbol["custom"]["spice"] = "S-CUSTOM"
        if winner <= 2:
            instance["format"]["spice"] = "I-FORMAT"
        symbol["format"]["spice"] = "S-FORMAT"
        level, template = resolve_format(instance, symbol, "spice")
        if winner == 0:
            assert (level, template) == ("instance_custom", "I-CUSTOM")
        elif winner == 1:
            assert (level, template) == ("symbol_custom", "S-CUSTOM")
        elif winner == 2:
            assert (level, template) == ("instance_format", "I-FORMAT")
        else:
            assert (level, template) == ("symbol_format", "S-FORMAT")
    assert resolve_format({}, {}, "spice") == (None, None)


def test_missing_name_and_format_skips_silently():
    from rocket_engine.workflows.connectgraph_emit import emit_netlists, to_raw_ir

    schematic = dict(DEMO)
    schematic["instances"] = list(DEMO["instances"]) + [{"symbol": "nograph"}]
    schematic["symbols"] = dict(DEMO["symbols"])
    schematic["symbols"]["nograph"] = {}
    raw = to_raw_ir(_structs(schematic))
    assert "X3" in raw["skipped"]
    texts = emit_netlists(raw)
    assert "X3" not in texts["spice"]
    assert "X3" not in texts["verilog"]
    assert "X3" not in texts["vhdl"]


def test_broken_template_fails_loudly_not_silently():
    from rocket_engine.workflows.connectgraph import ConnectGraphError
    from rocket_engine.workflows.connectgraph_emit import to_raw_ir

    schematic = dict(DEMO)
    schematic["instances"] = [
        {"name": "X1", "symbol": "inv", "format": {"spice": "X{name} {pins[NOPE]}"}}
    ]
    schematic["pins"] = [p for p in DEMO["pins"] if p["instance"] == "X1"]
    schematic["symbols"] = dict(DEMO["symbols"])
    try:
        to_raw_ir(_structs(schematic))
    except ConnectGraphError as exc:
        assert "X1" in str(exc)
    else:
        raise AssertionError("dangling template key must raise ConnectGraphError")


def test_spice_golden_byte_stable():
    from rocket_engine.workflows.connectgraph_emit import emit_spice, to_raw_ir

    golden = (FIXTURES / "connect_graph_demo.spice.golden").read_bytes()
    assert emit_spice(to_raw_ir(_structs())).encode() == golden


def test_verilog_golden_byte_stable():
    from rocket_engine.workflows.connectgraph_emit import emit_verilog, to_raw_ir

    golden = (FIXTURES / "connect_graph_demo.verilog.golden").read_bytes()
    assert emit_verilog(to_raw_ir(_structs())).encode() == golden


def test_vhdl_golden_byte_stable():
    from rocket_engine.workflows.connectgraph_emit import emit_vhdl, to_raw_ir

    golden = (FIXTURES / "connect_graph_demo.vhdl.golden").read_bytes()
    assert emit_vhdl(to_raw_ir(_structs())).encode() == golden


def test_emits_byte_stable_across_runs_and_input_order():
    from rocket_engine.workflows.connectgraph_emit import emit_netlists, to_raw_ir

    import copy

    first = emit_netlists(to_raw_ir(_structs()))
    second = emit_netlists(to_raw_ir(_structs()))
    assert first == second
    shuffled = copy.deepcopy(DEMO)
    shuffled["wires"] = list(reversed(shuffled["wires"]))
    shuffled["pins"] = list(reversed(shuffled["pins"]))
    shuffled["instances"] = list(reversed(shuffled["instances"]))
    assert emit_netlists(to_raw_ir(_structs(shuffled))) == first


def test_cross_language_net_identity():
    import re

    from rocket_engine.workflows.connectgraph_emit import emit_netlists, to_raw_ir

    texts = emit_netlists(to_raw_ir(_structs()))
    spice_nets = set(re.findall(r"^X\d+ (\S+(?: \S+)*) \w+$", texts["spice"], re.M))
    spice_pin_nets = {n for line in spice_nets for n in line.split()}
    verilog_nets = set(re.findall(r"\.([A-Z]+)\(([^)]+)\)", texts["verilog"]))
    verilog_pin_nets = {net for _, net in verilog_nets}
    vhdl_nets = set(re.findall(r"(\w+) => (\w+)", texts["vhdl"]))
    vhdl_pin_nets = {net for _, net in vhdl_nets}
    assert spice_pin_nets == verilog_pin_nets == vhdl_pin_nets == {"A", "Y", "net1"}
    # Pin-to-net maps agree too, not just the net set.
    verilog_map = {}
    for match in re.finditer(r"(\w+) (\w+) \((.*)\);", texts["verilog"]):
        ports = dict(re.findall(r"\.(\w+)\((\w+)\)", match.group(3)))
        if ports:
            verilog_map[match.group(2)] = ports
    vhdl_map = {}
    for match in re.finditer(r"(\w+) : entity work\.\w+ port map \((.*)\);", texts["vhdl"]):
        vhdl_map[match.group(1)] = dict(re.findall(r"(\w+) => (\w+)", match.group(2)))
    assert verilog_map == vhdl_map == {
        "X1": {"A": "A", "Y": "net1"},
        "X2": {"A": "net1", "Y": "Y"},
    }


def test_bus_bits_share_one_vector_declaration():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs
    from rocket_engine.workflows.connectgraph_emit import emit_netlists, to_raw_ir

    schematic = {
        "cell": "busdemo",
        "wires": [[[0, 0], [10, 0]], [[0, 10], [10, 10]]],
        "pins": [
            {"instance": "X1", "pin": "A", "xy": [0, 0]},
            {"instance": "X1", "pin": "Y", "xy": [0, 10]},
        ],
        "labels": [{"name": "d[0]", "xy": [10, 0]}, {"name": "d[1]", "xy": [10, 10]}],
        "instances": [{"name": "X1", "symbol": "buf"}],
        "symbols": {
            "buf": {
                "pins": ["A", "Y"],
                "format": {
                    "spice": "{name} {pin_nets} {symbol}",
                    "verilog": "{symbol} {name} (.A({pins[A]}), .Y({pins[Y]}));",
                    "vhdl": "{name} : entity work.{symbol} port map (A => {pins[A]}, Y => {pins[Y]});",
                },
            }
        },
    }
    texts = emit_netlists(to_raw_ir(prepare_netlist_structs(schematic)))
    assert "wire [1:0] d;" in texts["verilog"]
    assert "signal d : std_logic_vector(1 downto 0);" in texts["vhdl"]
    assert texts["verilog"].count("wire ") == 1
    # SPICE keeps bus bits flat: same names, no vector syntax.
    assert "d[0]" in texts["spice"] and "d[1]" in texts["spice"]


def test_emitters_reject_unknown_languages():
    from rocket_engine.workflows.connectgraph import ConnectGraphError
    from rocket_engine.workflows.connectgraph_emit import emit_netlists, to_raw_ir

    try:
        emit_netlists(to_raw_ir(_structs()), languages=["spice", "eldorado"])
    except ConnectGraphError as exc:
        assert "eldorado" in str(exc)
    else:
        raise AssertionError("unknown language must raise ConnectGraphError")
