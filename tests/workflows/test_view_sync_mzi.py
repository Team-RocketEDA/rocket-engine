"""VIEW-SYNC MZI RED — intended circuit vs perturbed extraction.

The MZI (two couplers, two arms) is the photonic P14 shape: intended
uses symbol-pin names, extraction uses cell-pin names through
CellLink links, and the perturbed extraction plants exactly five
diffs — wrong/missing/extra ports, one shorted arm pair, one dropped
pin. Valid RED = the workflow import itself fails.
"""

import copy
import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "view_sync_mzi.json"


def _mzi():
    return json.loads(FIXTURE.read_text())


def test_mzi_yields_exactly_the_planted_diffs():
    from rocket_engine.workflows.viewsync import compare_views

    mzi = _mzi()
    result = compare_views(mzi["intended"], mzi["extracted"], links=mzi["links"])
    findings = result["findings"]
    assert len(findings) == 5, [f["rule"] for f in findings]
    keys = set()
    for finding in findings:
        assert finding["severity"] == "error"
        if finding["rule"] in (
            "view_sync.missing_port",
            "view_sync.extra_port",
            "view_sync.wrong_port",
        ):
            keys.add((finding["rule"], finding["port"]))
        elif finding["rule"] == "view_sync.unexpected_connection":
            keys.add((finding["rule"], finding["net"]))
        else:
            keys.add((finding["rule"], finding["instance"], finding.get("pin")))
    assert keys == {
        ("view_sync.wrong_port", "IN"),
        ("view_sync.missing_port", "OUT"),
        ("view_sync.extra_port", "ARM_A"),
        ("view_sync.unexpected_connection", "ARM_A"),
        ("view_sync.unmapped", "S2", "out2"),
    }


def test_mzi_clean_cell_copy_passes():
    from rocket_engine.workflows.viewsync import compare_views

    mzi = _mzi()
    clean = copy.deepcopy(mzi["intended"])
    renames = {("S1", "out1"): "o1", ("S2", "in1"): "i1"}
    for pin in clean["pins"]:
        key = (pin["instance"], pin["pin"])
        if key in renames:
            pin["pin"] = renames[key]
    result = compare_views(mzi["intended"], clean, links=mzi["links"])
    assert result["findings"] == []
    assert "in sync" in result["coverage"]["statement"]
    assert result["coverage"]["mapped_pins"] == 8


def test_mzi_links_are_load_bearing():
    from rocket_engine.workflows.viewsync import compare_views

    mzi = _mzi()
    result = compare_views(mzi["intended"], mzi["extracted"])
    findings = result["findings"]
    assert len(findings) == 8, [(f["rule"], f.get("port")) for f in findings]
    unmapped = [f for f in findings if f["rule"] == "view_sync.unmapped"]
    assert len(unmapped) == 5
    assert {(f["instance"], f["pin"], f["side"]) for f in unmapped} == {
        ("S1", "out1", "intended"),
        ("S2", "in1", "intended"),
        ("S2", "out2", "intended"),
        ("S1", "o1", "extracted"),
        ("S2", "i1", "extracted"),
    }


def test_mzi_short_details_cite_celllink_identity():
    from rocket_engine.workflows.viewsync import compare_views

    mzi = _mzi()
    result = compare_views(mzi["intended"], mzi["extracted"], links=mzi["links"])
    short = next(f for f in result["findings"] if f["rule"] == "view_sync.unexpected_connection")
    assert sorted(n["net"] for n in short["merged_from"]) == ["ARM_A", "ARM_B"]
    members = {(m["instance"], m["pin"]) for m in short["members"]}
    assert members == {("S1", "o1"), ("S2", "i1"), ("S1", "out2"), ("S2", "in2")}
    syms = {(m["instance"], m["pin"]): m.get("sym_pin") for m in short["members"]}
    assert syms[("S1", "o1")] == "out1"
    assert syms[("S2", "i1")] == "in1"
    assert "o1" in short["message"] and "ARM_A" in short["message"]


def test_mzi_adapter_reports_planted_diffs():
    from rocket_engine.adapters.view_sync import ViewSyncAdapter

    mzi = _mzi()
    adapter = ViewSyncAdapter()
    job = {
        "operation": "run_view_sync",
        "intended": mzi["intended"],
        "extracted": mzi["extracted"],
        "links": mzi["links"],
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 5
    coverage = result["measurements"]["coverage"]
    assert coverage["mapped_pins"] == 7
    assert coverage["intended_nets"] == 6
    assert coverage["extracted_nets"] == 4
    assert "5 findings" in coverage["statement"]
    assert "5 findings" in result["measurements"]["report"]
