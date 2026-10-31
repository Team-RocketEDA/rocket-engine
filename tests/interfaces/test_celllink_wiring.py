"""CELL-LINK wiring integration — integrator runs AFTER the patch.

Pre-patch these skip (the composition/validation/contract wiring from
docs/work/CELL-LINK/report.md is not applied yet); post-patch they
must pass. They pin the wired surface, not module behavior (see
test_celllink.py and test_celllink_run.py for that).
"""

import pytest

CELL = "sky130A:sky130_fd_sc_hd__inv_2"


def test_top_level_interfaces_export():
    try:
        from rocket_engine.interfaces import (  # noqa: F401
            CellLinkError,
            collect_erc,
            match_cell_filters,
            resolve_cell,
            resolve_link,
            resolve_pin,
            resolve_run,
            validate_celllink,
        )
    except ImportError:
        pytest.skip("needs CELL-LINK wiring patch (interfaces export)")


def test_engine_run_resolves_celllinks():
    composition = pytest.importorskip(
        "rocket_engine.composition",
        reason="needs CELL-LINK wiring patch (full engine env)",
    )
    if not hasattr(composition.Engine, "resolve_celllinks"):
        pytest.skip("needs CELL-LINK wiring patch (Engine.resolve_celllinks)")
    engine = composition.Engine("celllink-probe", actor="tester")
    (record,) = engine.resolve_celllinks(
        [{"id": "u1", "CellLink": {"cell": CELL}}], {CELL}
    )
    assert record == {
        "block": "u1",
        "cell": CELL,
        "pinMap": [],
        "variant": None,
    }
    with pytest.raises(Exception) as excinfo:
        engine.resolve_celllinks(
            [{"id": "u2", "CellLink": {"cell": "noplib:nosuchcell"}}], {CELL}
        )
    assert getattr(excinfo.value, "code", None) == "unknown_cell"
