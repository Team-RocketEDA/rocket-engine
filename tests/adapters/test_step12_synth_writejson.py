"""Step-12 RED: synth_yosys parses the write_json netlist first.

Valid RED = parse() ignores `netlist_json`, so a native carrying
only JSON stats raises `runner_unavailable` and a native carrying
conflicting stat text parses the text counts. Per ESCAPE-HARDEN
item 1 the blessed escape is yosys `write_json` (pyosys rejected);
the scraped `synth_stat.txt` survives only as fallback (it still
carries the mapped area, which write_json has no key for).
Byte-identity rule (live-verified on yosys 0.70+219): per-module
netnames count as wires; per-module cells count except cells whose
type names another module (submodule instances, never leaf cells).
"""

import shutil
from pathlib import Path

import pytest

from rocket_engine.adapters.synth_yosys import YosysSynthAdapter

OSS = Path("/home/alrida-ismail/tools/oss-cad-suite/bin")
needs_yosys = pytest.mark.skipif(
    shutil.which("yosys") is None and not (OSS / "yosys").is_file(),
    reason="yosys not installed",
)

HIER_JSON = {
    "modules": {
        "sub": {
            "netnames": {"a": {}, "y": {}},
            "cells": {"c0": {"type": "$_NOT_"}},
        },
        "top": {
            "netnames": {"a": {}, "b": {}, "y": {}, "w": {}},
            "cells": {"c0": {"type": "$_AND_"}, "c1": {"type": "sub"}},
        },
    }
}

HIER_STAT = """4. Printing statistics.

=== top ===

        +----------Local Count, excluding submodules.
        |
        4 wires
        4 wire bits
        3 ports
        3 port bits
        1 cells
        1   $_AND_
        1 submodules

=== sub ===

        +----------Local Count, excluding submodules.
        |
        2 wires
        2 wire bits
        2 ports
        2 port bits
        1 cells
        1   $_NOT_

===
"""


def _native(*, stat=HIER_STAT, netlist_json=None):
    native = {
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
        "log": "",
        "stat": stat,
        "netlist": "synth_netlist.v",
        "top": "top",
        "mapped": False,
        "yosys_version": "Yosys 0.70+219",
    }
    if netlist_json is not None:
        native["netlist_json"] = netlist_json
    return native


def test_parse_reads_cells_from_netlist_json_not_stat_text(tmp_path):
    """Conflicting stat text must not move the JSON verdict."""
    netlist = tmp_path / "synth_netlist.v"
    netlist.write_text("module top(); endmodule\n")
    wrong_stat = HIER_STAT.replace("1   $_AND_", "7   $_AND_")
    native = _native(stat=wrong_stat, netlist_json=HIER_JSON)
    native["netlist"] = str(netlist)
    result = YosysSynthAdapter().parse(native)
    assert result["cells"] == {"$_AND_": 1, "$_NOT_": 1}
    assert result["cell_count"] == 2
    assert result["wire_count"] == 6


def test_netlist_json_alone_parses_without_stat_text(tmp_path):
    """JSON stats suffice; no stat verdict text is required."""
    netlist = tmp_path / "synth_netlist.v"
    netlist.write_text("module top(); endmodule\n")
    native = _native(stat="", netlist_json=HIER_JSON)
    native["netlist"] = str(netlist)
    result = YosysSynthAdapter().parse(native)
    assert result["cells"] == {"$_AND_": 1, "$_NOT_": 1}
    assert result["cell_count"] == 2
    assert result["wire_count"] == 6


def test_netlist_json_byte_identical_to_stat_text(tmp_path):
    """JSON-derived stats equal text-derived stats on the golden."""
    netlist = tmp_path / "synth_netlist.v"
    netlist.write_text("module top(); endmodule\n")
    only_json = _native(stat="", netlist_json=HIER_JSON)
    only_json["netlist"] = str(netlist)
    from_json = YosysSynthAdapter().parse(only_json)
    native = _native(stat=HIER_STAT)
    native["netlist"] = str(netlist)
    from_text = YosysSynthAdapter().parse(native)
    for key in ("cells", "cell_count", "wire_count"):
        assert from_json[key] == from_text[key]


@needs_yosys
def test_execute_emits_netlist_json(tmp_path):
    """Execute writes synth_netlist.json and threads it through."""
    (tmp_path / "top.v").write_text(
        "module top(input a, b, output y);\nassign y = a & b;\nendmodule\n"
    )
    adapter = YosysSynthAdapter()
    native = adapter.execute(
        {
            "operation": "run_synth",
            "sources": [str(tmp_path / "top.v")],
            "top": "top",
            "workdir": str(tmp_path),
        }
    )
    assert (tmp_path / "synth_netlist.json").is_file()
    assert isinstance(native.get("netlist_json"), dict)
    assert set(native["netlist_json"].get("modules", {})) >= {"top"}


@needs_yosys
def test_live_json_matches_live_stat_text(tmp_path):
    """Live yosys: JSON stats equal the scraped stat text."""
    (tmp_path / "top.v").write_text(
        "module top(input a, b, output y);\nassign y = a & b;\nendmodule\n"
    )
    adapter = YosysSynthAdapter()
    native = adapter.execute(
        {
            "operation": "run_synth",
            "sources": [str(tmp_path / "top.v")],
            "top": "top",
            "workdir": str(tmp_path),
        }
    )
    parsed = adapter.parse(native)
    text_only = dict(native)
    text_only.pop("netlist_json", None)
    reparsed = adapter.parse(text_only)
    for key in ("cells", "cell_count", "wire_count"):
        assert parsed[key] == reparsed[key]
