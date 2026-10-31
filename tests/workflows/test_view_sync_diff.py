"""VIEW-SYNC diff RED — intended-vs-extracted over CONNECT-GRAPH + CellLink.

`compare_views` reduces two schematics through
`prepare_netlist_structs`, correlates pins through CellLink identity
(never a second naming scheme), and reports missing/wrong/extra
ports, missing/unexpected connections, and unmapped objects with
per-finding identity references. Valid RED = the import itself fails.
"""

import copy

RULES = (
    "view_sync.missing_port",
    "view_sync.extra_port",
    "view_sync.wrong_port",
    "view_sync.missing_connection",
    "view_sync.unexpected_connection",
    "view_sync.unmapped",
)


def _single():
    """One SIG net between X1.A and X2.A, port SIG input."""
    return {
        "cell": "tiny",
        "wires": [[[0, 0], [10, 0]]],
        "pins": [
            {"instance": "X1", "pin": "A", "xy": [0, 0]},
            {"instance": "X2", "pin": "A", "xy": [10, 0]},
        ],
        "labels": [{"name": "SIG", "xy": [0, 0]}],
        "instances": [
            {"name": "X1", "symbol": "s"},
            {"name": "X2", "symbol": "s"},
        ],
        "symbols": {"s": {"pins": ["A"]}},
        "ports": [{"name": "SIG", "direction": "input"}],
    }


def _two_net():
    """Two nets N1/N2 between X1/X2 pin pairs, no ports."""
    return {
        "cell": "tiny",
        "wires": [[[0, 0], [10, 0]], [[0, 10], [10, 10]]],
        "pins": [
            {"instance": "X1", "pin": "A", "xy": [0, 0]},
            {"instance": "X2", "pin": "A", "xy": [10, 0]},
            {"instance": "X1", "pin": "B", "xy": [0, 10]},
            {"instance": "X2", "pin": "B", "xy": [10, 10]},
        ],
        "labels": [{"name": "N1", "xy": [0, 0]}, {"name": "N2", "xy": [0, 10]}],
        "instances": [
            {"name": "X1", "symbol": "s"},
            {"name": "X2", "symbol": "s"},
        ],
        "symbols": {"s": {"pins": ["A", "B"]}},
        "ports": [],
    }


def test_import_surface_exists():
    from rocket_engine.workflows import viewsync  # RED: missing module

    assert callable(viewsync.compare_views)
    assert issubclass(viewsync.ViewSyncError, ValueError)
    assert viewsync.RULE_MISSING_PORT == "view_sync.missing_port"
    assert viewsync.RULE_EXTRA_PORT == "view_sync.extra_port"
    assert viewsync.RULE_WRONG_PORT == "view_sync.wrong_port"
    assert viewsync.RULE_MISSING_CONNECTION == "view_sync.missing_connection"
    assert viewsync.RULE_UNEXPECTED_CONNECTION == "view_sync.unexpected_connection"
    assert viewsync.RULE_UNMAPPED == "view_sync.unmapped"


def test_clean_comparison_passes_with_coverage_statement():
    from rocket_engine.workflows.viewsync import compare_views

    result = compare_views(_single(), _single())
    assert result["findings"] == []
    coverage = result["coverage"]
    assert coverage["compared_views"] == ["intended", "extracted"]
    assert coverage["intended_nets"] == coverage["extracted_nets"] == 1
    assert coverage["mapped_pins"] == 2
    assert "0 findings" in coverage["statement"]
    assert "in sync" in coverage["statement"]
    assert coverage["statement"] in result["report"]


def test_missing_port_detected():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _single()
    extracted["ports"] = []
    result = compare_views(_single(), extracted)
    assert [(f["rule"], f["port"]) for f in result["findings"]] == [
        ("view_sync.missing_port", "SIG")
    ]
    finding = result["findings"][0]
    assert finding["severity"] == "error"
    assert finding["view"] == "intended"
    assert "SIG" in finding["message"]


def test_extra_port_detected():
    from rocket_engine.workflows.viewsync import compare_views

    intended = _single()
    intended["ports"] = []
    result = compare_views(intended, _single())
    assert [(f["rule"], f["port"]) for f in result["findings"]] == [
        ("view_sync.extra_port", "SIG")
    ]
    assert result["findings"][0]["view"] == "extracted"


def test_wrong_port_direction_detected():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _single()
    extracted["ports"] = [{"name": "SIG", "direction": "output"}]
    result = compare_views(_single(), extracted)
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "view_sync.wrong_port"
    assert finding["port"] == "SIG"
    assert finding["expected_direction"] == "input"
    assert finding["actual_direction"] == "output"


def test_missing_connection_detected():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _two_net()
    extracted["wires"] = [[[0, 0], [10, 0]]]
    result = compare_views(_two_net(), extracted)
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "view_sync.missing_connection"
    assert finding["net"] == "N2"
    assert finding["view"] == "intended"
    assert len(finding["split_across"]) == 2
    assert "N2" in finding["message"]


def test_unexpected_connection_detected():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _two_net()
    extracted["wires"].append([[5, 0], [5, 10]])
    result = compare_views(_two_net(), extracted)
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "view_sync.unexpected_connection"
    assert finding["net"] == "N1"
    assert finding["view"] == "extracted"
    assert sorted(n["net"] for n in finding["merged_from"]) == ["N1", "N2"]


def test_unmapped_pin_detected():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _two_net()
    dropped = {"instance": "X2", "pin": "B", "xy": [10, 10]}
    extracted["pins"] = [p for p in extracted["pins"] if p != dropped]
    result = compare_views(_two_net(), extracted)
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "view_sync.unmapped"
    assert finding["kind"] == "pin"
    assert finding["instance"] == "X2"
    assert finding["pin"] == "B"
    assert finding["side"] == "intended"


def test_extra_instance_detected_once_not_per_pin():
    from rocket_engine.workflows.viewsync import compare_views

    extracted = _two_net()
    extracted["instances"].append({"name": "X3", "symbol": "s"})
    extracted["pins"].append({"instance": "X3", "pin": "C", "xy": [5, 0]})
    result = compare_views(_two_net(), extracted)
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule"] == "view_sync.unmapped"
    assert finding["kind"] == "instance"
    assert finding["instance"] == "X3"
    assert finding["side"] == "extracted"


def test_celllink_rename_honored():
    from rocket_engine.workflows.viewsync import compare_views

    intended = _single()
    extracted = _single()
    extracted["pins"][0] = {"instance": "X1", "pin": "a1", "xy": [0, 0]}
    links = [
        {"id": "X1", "CellLink": {"cell": "t:s", "pinMap": [{"symPin": "A", "cellPin": "a1"}]}}
    ]
    assert compare_views(intended, extracted, links=links)["findings"] == []
    bare = compare_views(intended, extracted)["findings"]
    assert len(bare) == 2
    assert {f["rule"] for f in bare} == {"view_sync.unmapped"}


def test_variant_override_honored():
    from rocket_engine.workflows.viewsync import compare_views

    intended = _single()
    extracted = _single()
    extracted["pins"][0] = {"instance": "X1", "pin": "a1", "xy": [0, 0]}
    links = [
        {
            "id": "X1",
            "CellLink": {"cell": "t:s", "variantOverrides": {"fast": {"pinEdits": {"A": "a1"}}}},
        }
    ]
    assert compare_views(intended, extracted, links=links, variant="fast")["findings"] == []
    assert len(compare_views(intended, extracted, links=links)["findings"]) == 2


def test_bad_identity_raises_typed_error():
    from rocket_engine.workflows.viewsync import ViewSyncError, compare_views

    intended, extracted = _single(), _single()
    cases = [
        {"links": [{"id": "X1"}, {"id": "X1"}], "variant": None},
        {
            "links": [{
                "id": "X1", "CellLink": {"pinMap": [
                    {"symPin": "A", "cellPin": "x"},
                    {"symPin": "A", "cellPin": "y"},
                ]},
            }],
            "variant": None,
        },
        {"links": [{"id": "X1"}], "variant": "nope"},
        {"links": "not-a-list", "variant": None},
    ]
    for case in cases:
        try:
            compare_views(intended, extracted, **case)
        except ViewSyncError:
            continue
        raise AssertionError(f"bad identity accepted: {case!r}")


def test_identity_collision_raises_typed_error():
    from rocket_engine.workflows.viewsync import ViewSyncError, compare_views

    links = [
        {"id": "X1", "CellLink": {"cell": "t:s", "pinMap": [
            {"symPin": "A", "cellPin": "a"},
            {"symPin": "B", "cellPin": "a"},
        ]}}
    ]
    try:
        compare_views(_two_net(), _two_net(), links=links)
    except ViewSyncError as exc:
        assert "collision" in str(exc)
    else:
        raise AssertionError("identity collision must raise ViewSyncError")


def test_malformed_schematic_raises_with_side():
    from rocket_engine.workflows.viewsync import ViewSyncError, compare_views

    bad = {"cell": "bad", "wires": [[["oops"]]]}
    for intended, extracted, side in ((bad, _single(), "intended"), (_single(), bad, "extracted")):
        try:
            compare_views(intended, extracted)
        except ViewSyncError as exc:
            assert side in str(exc), str(exc)
        else:
            raise AssertionError(f"malformed {side} accepted")


def test_findings_reuse_net_name_authority():
    from rocket_engine.workflows.connectgraph import prepare_netlist_structs
    from rocket_engine.workflows.viewsync import compare_views

    intended, extracted = _two_net(), _two_net()
    extracted["wires"].append([[5, 0], [5, 10]])
    intended["ports"] = [{"name": "N1", "direction": "input"}]
    extracted["ports"] = [{"name": "N1", "direction": "output"}]
    result = compare_views(intended, extracted)
    assert {f["rule"] for f in result["findings"]} == {
        "view_sync.wrong_port",
        "view_sync.unexpected_connection",
    }
    conns = {
        "intended": prepare_netlist_structs(intended).connectivity,
        "extracted": prepare_netlist_structs(extracted).connectivity,
    }
    for finding in result["findings"]:
        conn = conns[finding["view"]]
        assert finding["net"] == conn.net_name(finding["net_id"])
    wrong = next(f for f in result["findings"] if f["rule"] == "view_sync.wrong_port")
    assert wrong["net"] == conns["extracted"].net_name(wrong["extracted_net_id"])


def test_pinless_nets_skipped_with_coverage():
    from rocket_engine.workflows.viewsync import compare_views

    intended = _single()
    intended["labels"].append({"name": "LONELY", "xy": [999, 999]})
    result = compare_views(intended, _single())
    assert result["findings"] == []
    assert result["coverage"]["pinless_nets_skipped"] == 1
    flipped = compare_views(_single(), intended)
    assert flipped["findings"] == []
    assert flipped["coverage"]["pinless_nets_skipped"] == 1


def test_findings_sorted_and_deterministic():
    from rocket_engine.workflows.viewsync import compare_views

    intended = _two_net()
    intended["ports"] = [{"name": "N1", "direction": "input"}]
    extracted = _two_net()
    extracted["wires"].append([[5, 0], [5, 10]])
    extracted["ports"] = []
    first = compare_views(copy.deepcopy(intended), copy.deepcopy(extracted))["findings"]
    second = compare_views(copy.deepcopy(intended), copy.deepcopy(extracted))["findings"]
    assert first == second
    assert [f["rule"] for f in first] == sorted(f["rule"] for f in first)
    assert {f["rule"] for f in first} == {
        "view_sync.missing_port", "view_sync.unexpected_connection",
    }


def test_p14_photonic_stage_needs_view_sync():
    from rocket_engine.workflows import applicable_stages

    backends = {"run_drc", "run_view_sync"}
    ready = [s for s in applicable_stages("photonic", backends)
             if s["id"] == "P14"]
    assert ready and ready[0]["readiness"] == "ready"
    blocked = [s for s in applicable_stages("photonic", {"run_drc"}) if s["id"] == "P14"]
    assert blocked and blocked[0]["readiness"] == "blocked"
