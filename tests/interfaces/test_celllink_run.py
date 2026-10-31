"""CELL-LINK RED — run/export resolution round-trip.

Tests assume `rocket_engine.interfaces.celllink.resolve_run`: per-block
(cell, pinMap, variant) emission, only when non-empty, with unknown
cells failing the run under a named reason. Valid RED = import fails.
"""

import pytest

CELL = "sky130A:sky130_fd_sc_hd__inv_2"


def _mod():
    from rocket_engine.interfaces import celllink  # RED: missing module

    return celllink


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def test_round_trip_explicit_identity_and_variant_pins():
    celllink = _mod()
    block = {
        "id": "u1",
        "CellLink": {
            "cell": CELL,
            "pinMap": [{"symPin": "A", "cellPin": "A"}],
            "variantOverrides": {"fast": {"pinEdits": {"Y": "Y_fast"}}},
        },
    }
    (record,) = celllink.resolve_run([block], {CELL})
    assert record == {
        "block": "u1",
        "cell": CELL,
        "pinMap": [{"symPin": "A", "cellPin": "A"}],
        "variant": None,
    }
    assert celllink.resolve_pin(block, "A") == "A"  # explicit
    assert celllink.resolve_pin(block, "Y") == "Y"  # identity default
    assert celllink.resolve_pin(block, "Y", variant="fast") == "Y_fast"
    (fast,) = celllink.resolve_run([block], {CELL}, variant="fast")
    assert fast["pinMap"] == [
        {"symPin": "A", "cellPin": "A"},
        {"symPin": "Y", "cellPin": "Y_fast"},
    ]
    assert fast["variant"] == "fast"


def test_run_emits_only_non_empty_links():
    celllink = _mod()
    blocks = [
        {"id": "u1", "CellLink": {"cell": CELL}},
        {"id": "u2"},  # no link at all
        {"id": "u3", "CellLink": {"cell": ""}},  # unlinked
    ]
    records = celllink.resolve_run(blocks, {CELL})
    assert [r["block"] for r in records] == ["u1"]


def test_run_variant_cell_override_emitted():
    celllink = _mod()
    hv = "sky130A:sky130_fd_sc_hvl__inv_2"
    block = {
        "id": "u9",
        "CellLink": {"cell": CELL, "variantOverrides": {"hv": {"cell": hv}}},
    }
    (record,) = celllink.resolve_run([block], {CELL, hv}, variant="hv")
    assert record["cell"] == hv


def test_run_unknown_cell_fails_with_named_reason_edit_stays_free():
    celllink = _mod()
    link = {"cell": "noplib:nosuchcell"}
    assert celllink.validate_celllink(link)["cell"] == "noplib:nosuchcell"
    with pytest.raises(Exception) as excinfo:
        celllink.resolve_run([{"id": "u4", "CellLink": link}], {CELL})
    assert _code(excinfo) == "unknown_cell"
    assert "u4" in str(excinfo.value)
    assert "noplib:nosuchcell" in str(excinfo.value)


def test_run_rejects_block_without_id():
    celllink = _mod()
    with pytest.raises(Exception) as excinfo:
        celllink.resolve_run([{"CellLink": {"cell": CELL}}], {CELL})
    assert _code(excinfo) == "invalid_block"
