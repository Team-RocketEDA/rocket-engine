"""DUMP-PROOFS-WAVE1 RED — wave-1 tool parse determinism.

Per kept wave-1 tool (magic, klayout, netgen, slang, connectgraph,
sby): the same recorded native output parses to the identical result
on repeat runs (JSON round-trip included), good outputs parse clean,
mutated outputs parse failing, and verdict-less outputs refuse
loudly instead of guessing. Canned natives are transcribed from the
adapter grammars with provenance in docs/tool-outputs/. Fails
today: no wave-1 determinism pins exist.
"""

import copy
import json

import pytest

MAGIC_GOOD_STDOUT = (
    'Magic version 8.3.685 (canned transcription; real run per '
    'docs/tool-outputs/magic-8.3.685.md).\n'
    'Using technology "scmos", version 8.2.8\n'
    "Total DRC errors found: 0\n"
)

MAGIC_BAD_STDOUT = (
    "Total DRC errors found: 2\n"
    "Error area #1:\n"
    "m1.1: minimum width 0.14um, width 0.10um\n"
    "-5 -5 15 10\n"
    "Error area #2:\n"
    "m1.2: minimum spacing 0.14um\n"
    "0 0 3 4\n"
)

KLAYOUT_GOOD_STDOUT = "TOTAL 0\n"

KLAYOUT_BAD_STDOUT = (
    "VIOL rule=L1_0_width bbox_um=0.0,0.0,0.5,0.1\n"
    "VIOL rule=L1_0_space bbox_um=1.0,0.0,1.2,0.1\n"
    "TOTAL 2\n"
)

KLAYOUT_DECK_GOOD_XML = """<?xml version="1.0"?>
<report-database>
<categories></categories>
<items></items>
</report-database>
"""

KLAYOUT_DECK_BAD_XML = """<?xml version="1.0"?>
<report-database>
<categories><category><name>metal1.width</name>
<description>min width 0.14</description></category></categories>
<items><item><category>metal1.width</category><multiplicity>1</multiplicity>
<values><value>D 0.10/0.14 at (1.0,2.0)</value></values></item></items>
</report-database>
"""

NETGEN_GOOD_REPORT = (
    "Netgen 1.5.316 LVS report (canned transcription; real run per "
    "docs/tool-outputs/netgen-1.5.316.md).\n"
    "Circuits match uniquely.\n"
)

NETGEN_BAD_REPORT = (
    "Netlists do not match.\n"
    "*** MISMATCH ***\n"
    "Net: vdd\n"
    "(no matching net)\n"
    "DEVICE mismatches:\n"
    "Instance: X1\n"
)

SLANG_GOOD_TEXT = "Build succeeded: 0 errors, 0 warnings\n"

SLANG_BAD_TEXT = (
    "counter_broken.v:3:5: error: use of undeclared identifier 'foo' [-Wfoo]\n"
    "Build failed: 1 error, 0 warnings\n"
)

SBY_GOOD_STDOUT = (
    "SBY v0.70 (canned transcription; real run per "
    "docs/tool-outputs/sby-0.70.md).\n"
    "summary: engine_0 (smtbmc boolector) returned pass for assert_p\n"
    "DONE (PASS, rc=0)\n"
)

SBY_BAD_STDOUT = (
    "summary: failed assertion assert_p at counter.v:12.3 step 5\n"
    "summary: counterexample trace [cex_0]: formal/counter/engine_0/trace.vcd\n"
    "DONE (FAIL, rc=2)\n"
)

CONNECTGRAPH_GOOD_NATIVE = {"exit_code": 0, "findings": []}

CONNECTGRAPH_BAD_NATIVE = {
    "exit_code": 0,
    "findings": [
        {
            "rule": "short",
            "severity": "error",
            "message": "nets a and b are shorted",
            "net": "a",
            "net_id": 0,
        }
    ],
}


def _parse(adapter_path, cls, native):
    import importlib

    module = importlib.import_module(adapter_path)
    return getattr(module, cls)().parse(native)


def _deterministic(adapter_path, cls, native):
    first = _parse(adapter_path, cls, copy.deepcopy(native))
    second = _parse(adapter_path, cls, json.loads(json.dumps(native)))
    assert first == second
    return first


def test_magic_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.drc.magic",
        "MagicDrcAdapter",
        {"exit_code": 0, "stdout": MAGIC_GOOD_STDOUT, "stderr": ""},
    )
    assert good == {"total": 0, "violations": []}
    bad = _deterministic(
        "rocket_engine.adapters.drc.magic",
        "MagicDrcAdapter",
        {"exit_code": 0, "stdout": MAGIC_BAD_STDOUT, "stderr": ""},
    )
    assert bad["total"] == 2
    assert [v["area"] for v in bad["violations"]] == [1, 2]


def test_magic_parse_refuses_verdict_less_output():
    from rocket_engine.adapters.drc.magic import MagicDrcAdapter
    from rocket_engine.adapters.errors import AdapterError

    with pytest.raises(AdapterError, match="no DRC total line"):
        MagicDrcAdapter().parse({"exit_code": 0, "stdout": "garbage\n"})


def test_klayout_synthetic_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.drc.klayout",
        "KlayoutDrcAdapter",
        {"exit_code": 0, "stdout": KLAYOUT_GOOD_STDOUT, "stderr": ""},
    )
    assert good == {"total": 0, "violations": []}
    bad = _deterministic(
        "rocket_engine.adapters.drc.klayout",
        "KlayoutDrcAdapter",
        {"exit_code": 0, "stdout": KLAYOUT_BAD_STDOUT, "stderr": ""},
    )
    assert bad["total"] == 2
    assert bad["violations"][0]["bbox_um"] == [0.0, 0.0, 0.5, 0.1]


def test_klayout_deck_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.drc.klayout",
        "KlayoutDrcAdapter",
        {"exit_code": 0, "stdout": "", "report_xml": KLAYOUT_DECK_GOOD_XML},
    )
    assert good == {"total": 0, "violations": []}
    bad = _deterministic(
        "rocket_engine.adapters.drc.klayout",
        "KlayoutDrcAdapter",
        {"exit_code": 0, "stdout": "", "report_xml": KLAYOUT_DECK_BAD_XML},
    )
    assert bad["total"] == 1
    assert bad["violations"][0]["rule"] == "metal1.width"


def test_klayout_parse_refuses_verdict_less_output():
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter
    from rocket_engine.adapters.errors import AdapterError

    with pytest.raises(AdapterError, match="no TOTAL line"):
        KlayoutDrcAdapter().parse({"exit_code": 0, "stdout": "nothing\n"})


def test_netgen_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.lvs_netgen",
        "NetgenLvsAdapter",
        {"exit_code": 0, "stdout": "", "report_text": NETGEN_GOOD_REPORT},
    )
    assert good == {"match": True, "total": 0, "violations": []}
    bad = _deterministic(
        "rocket_engine.adapters.lvs_netgen",
        "NetgenLvsAdapter",
        {"exit_code": 0, "stdout": "", "report_text": NETGEN_BAD_REPORT},
    )
    assert bad["match"] is False
    assert bad["total"] == 3
    assert {v["rule"] for v in bad["violations"]} == {
        "lvs_net_mismatch",
        "lvs_device_mismatch",
    }


def test_netgen_parse_refuses_verdict_less_output():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.lvs_netgen import NetgenLvsAdapter

    with pytest.raises(AdapterError, match="no LVS verdict"):
        NetgenLvsAdapter().parse({"exit_code": 0, "report_text": "noise\n"})


def test_slang_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.syntax",
        "SyntaxAdapter",
        {"exit_code": 0, "stdout": SLANG_GOOD_TEXT, "stderr": ""},
    )
    assert good == {"total": 0, "violations": []}
    bad = _deterministic(
        "rocket_engine.adapters.syntax",
        "SyntaxAdapter",
        {"exit_code": 0, "stdout": SLANG_BAD_TEXT, "stderr": ""},
    )
    assert bad["total"] == 1
    assert bad["violations"][0]["rule"] == "-Wfoo"
    assert bad["violations"][0]["severity"] == "error"


def test_slang_parse_refuses_verdict_less_output():
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.syntax import SyntaxAdapter

    with pytest.raises(AdapterError, match="no Build summary line"):
        SyntaxAdapter().parse({"exit_code": 1, "stdout": "oops\n"})


def test_connectgraph_parse_is_deterministic_and_two_sided():
    good = _deterministic(
        "rocket_engine.adapters.connectivity",
        "ConnectivityAdapter",
        CONNECTGRAPH_GOOD_NATIVE,
    )
    assert good["total"] == 0
    assert good["violations"] == []
    bad = _deterministic(
        "rocket_engine.adapters.connectivity",
        "ConnectivityAdapter",
        CONNECTGRAPH_BAD_NATIVE,
    )
    assert bad["total"] == 1
    assert bad["violations"][0]["rule"] == "short"


def test_connectgraph_parse_refuses_findings_less_output():
    from rocket_engine.adapters.connectivity import ConnectivityAdapter
    from rocket_engine.adapters.errors import AdapterError

    with pytest.raises(AdapterError, match="no findings list"):
        ConnectivityAdapter().parse({"exit_code": 0})


def test_sby_parse_is_deterministic_and_two_sided(tmp_path):
    from pathlib import Path

    fixture = (
        Path(__file__).parent
        / "adapters"
        / "fixtures"
        / "formal"
        / "counter.v"
    )
    assert fixture.is_file()
    good_native = {
        "exit_code": 0,
        "stdout": SBY_GOOD_STDOUT,
        "stderr": "",
        "timed_out": False,
        "workdir": str(tmp_path),
        "sources": [str(fixture)],
        "top": "counter",
        "mode": "bmc",
        "depth": 20,
    }
    good = _deterministic(
        "rocket_engine.adapters.formal_sby", "FormalSbyAdapter", good_native
    )
    assert good["total"] == 0
    assert good["measurements"]["scope"] == "bounded"
    bad_native = dict(
        good_native, stdout=SBY_BAD_STDOUT, stderr="", timed_out=False
    )
    bad = _deterministic(
        "rocket_engine.adapters.formal_sby", "FormalSbyAdapter", bad_native
    )
    assert bad["total"] == 1
    assert bad["violations"][0]["rule"] == "assert_fail"
    assert bad["measurements"]["scope"] == "bounded"


def test_sby_parse_refuses_verdict_less_output(tmp_path):
    from rocket_engine.adapters.errors import AdapterError
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter

    with pytest.raises(AdapterError, match="no status file"):
        FormalSbyAdapter().parse(
            {
                "exit_code": 0,
                "stdout": "noise\n",
                "stderr": "",
                "timed_out": False,
                "workdir": str(tmp_path),
                "sources": [],
            }
        )
