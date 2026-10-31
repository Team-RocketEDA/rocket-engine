"""VIEW-SYNC adapter RED — run_view_sync ToolAdapter over connectgraph.

Pure-Python adapter: preflight validates the job, execute diffs via
`compare_views`, parse normalizes findings and carries
coverage/report as measurements. Valid RED = the import itself fails.
"""


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


def _adapter():
    from rocket_engine.adapters.view_sync import ViewSyncAdapter

    return ViewSyncAdapter()


def test_capabilities_name_operation_and_tool():
    from rocket_engine.adapters.view_sync import (  # RED: missing module
        OPERATION,
        TOOL,
    )

    assert OPERATION == "run_view_sync"
    assert TOOL == "connectgraph"
    caps = _adapter().capabilities(target=None)
    assert caps == {"operations": ["run_view_sync"], "tool": "connectgraph"}


def test_preflight_rejects_bad_jobs():
    from rocket_engine.adapters.errors import AdapterError

    adapter = _adapter()
    good = {"operation": "run_view_sync", "intended": _single(), "extracted": _single()}
    checked = adapter.preflight(dict(good))
    assert checked["operation"] == "run_view_sync"
    assert checked["links"] == []
    assert checked["variant"] is None
    bad = [
        {"operation": "run_drc", "intended": {}, "extracted": {}},
        {"operation": "run_view_sync", "extracted": _single()},
        {"operation": "run_view_sync", "intended": _single()},
        {"operation": "run_view_sync", "intended": [], "extracted": _single()},
        {"operation": "run_view_sync", "intended": _single(), "extracted": []},
        {"operation": "run_view_sync", "intended": _single(), "extracted": _single(), "links": {}},
        {"operation": "run_view_sync", "intended": _single(), "extracted": _single(), "variant": 7},
    ]
    for job in bad:
        try:
            adapter.preflight(job)
        except AdapterError as exc:
            assert exc.code in ("unsupported_operation", "invalid_command"), job
        else:
            raise AssertionError(f"bad job accepted: {job!r}")
    hinted = dict(good, deck={"tool": "netgen"})
    try:
        adapter.preflight(hinted)
    except AdapterError as exc:
        assert exc.code == "unsupported_operation"
    else:
        raise AssertionError("foreign deck tool accepted")


def test_clean_round_trip_carries_coverage():
    adapter = _adapter()
    job = {"operation": "run_view_sync", "intended": _single(), "extracted": _single()}
    native = adapter.execute(job)
    assert native["exit_code"] == 0
    result = adapter.parse(native)
    assert result["total"] == 0
    assert result["violations"] == []
    assert "in sync" in result["measurements"]["coverage"]["statement"]
    assert result["measurements"]["report"]


def test_missing_port_round_trip():
    adapter = _adapter()
    extracted = _single()
    extracted["ports"] = []
    job = {"operation": "run_view_sync", "intended": _single(), "extracted": extracted}
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 1
    violation = result["violations"][0]
    assert violation["rule"] == "view_sync.missing_port"
    assert violation["severity"] == "error"
    assert "SIG" in violation["message"]
    assert violation["port"] == "SIG"


def test_malformed_schematic_is_invalid_command():
    from rocket_engine.adapters.errors import AdapterError

    adapter = _adapter()
    job = {
        "operation": "run_view_sync",
        "intended": {"cell": "bad", "wires": [[["oops"]]]},
        "extracted": _single(),
    }
    try:
        adapter.execute(job)
    except AdapterError as exc:
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("malformed schematic must raise invalid_command")


def test_unknown_variant_is_invalid_command():
    from rocket_engine.adapters.errors import AdapterError

    adapter = _adapter()
    job = {
        "operation": "run_view_sync",
        "intended": _single(),
        "extracted": _single(),
        "links": [{"id": "X1"}],
        "variant": "nope",
    }
    try:
        adapter.execute(job)
    except AdapterError as exc:
        assert exc.code == "invalid_command"
    else:
        raise AssertionError("unknown variant must raise invalid_command")


def test_parse_without_findings_is_runner_unavailable():
    from rocket_engine.adapters.errors import AdapterError

    try:
        _adapter().parse({"exit_code": 0})
    except AdapterError as exc:
        assert exc.code == "runner_unavailable"
    else:
        raise AssertionError("findings-less output must raise runner_unavailable")


def test_job_inputs_drive_the_diff():
    adapter = _adapter()
    ported, bare = _single(), _single()
    bare["ports"] = []
    missing = adapter.parse(
        adapter.execute({"operation": "run_view_sync", "intended": ported, "extracted": bare})
    )
    extra = adapter.parse(
        adapter.execute({"operation": "run_view_sync", "intended": bare, "extracted": ported})
    )
    assert [v["rule"] for v in missing["violations"]] == ["view_sync.missing_port"]
    assert [v["rule"] for v in extra["violations"]] == ["view_sync.extra_port"]
