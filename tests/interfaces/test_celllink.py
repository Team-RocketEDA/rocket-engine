"""CELL-LINK RED — CellLink schema, resolvePin chokepoint, filters.

Tests assume `rocket_engine.interfaces.celllink` with validate_celllink,
resolve_pin / resolve_cell / resolve_link, match_cell_filters, and
collect_erc. Valid RED = the import itself fails.
"""

import copy

import pytest

CELL = "sky130A:sky130_fd_sc_hd__inv_2"


def _mod():
    from rocket_engine.interfaces import celllink  # RED: missing module

    return celllink


def _code(excinfo):
    return getattr(excinfo.value, "code", None)


def _block(link=None, block_id="u1"):
    block = {"id": block_id}
    if link is not None:
        block["CellLink"] = link
    return block


# -- schema: edit-time validation never checks cell existence ---------


def test_validate_minimal_link_gets_defaults():
    celllink = _mod()
    link = celllink.validate_celllink({"cell": CELL})
    assert link == {
        "cell": CELL,
        "pinMap": [],
        "cellFilters": [],
        "variantOverrides": {},
    }


def test_validate_unknown_cell_passes_edit_time():
    celllink = _mod()
    link = celllink.validate_celllink({"cell": "noplib:nosuchcell"})
    assert link["cell"] == "noplib:nosuchcell"


def test_validate_empty_link_allowed_at_edit():
    celllink = _mod()
    assert celllink.validate_celllink({})["cell"] == ""
    assert celllink.validate_celllink({"cell": ""})["cell"] == ""


@pytest.mark.parametrize(
    "bad",
    [
        "sky130A:inv",
        {"cell": 7},
        {"cell": CELL, "pinMap": [{"symPin": "A"}]},
        {"cell": CELL, "pinMap": [{"symPin": "", "cellPin": "A"}]},
        {"cell": CELL, "pinMap": [{"symPin": "A", "cellPin": ""}]},
        {"cell": CELL, "pinMap": [{"symPin": "A", "cellPin": "x", "extra": 1}]},
        {"cell": CELL, "pinMap": [{"symPin": "A", "cellPin": "x"}] * 2},
        {"cell": CELL, "cellFilters": "sky130*"},
        {"cell": CELL, "cellFilters": [7]},
        {"cell": CELL, "variantOverrides": {"tt": {"cell": ""}}},
        {"cell": CELL, "variantOverrides": {"tt": {"pinEdits": {"A": ""}}}},
        {"cell": CELL, "variantOverrides": {"tt": {"cell": 7}}},
        {"cell": CELL, "variantOverrides": {"tt": {"bogus": 1}}},
        {"cell": CELL, "bogus": 1},
    ],
)
def test_validate_rejects_malformed_links(bad):
    celllink = _mod()
    with pytest.raises(Exception) as excinfo:
        celllink.validate_celllink(bad)
    assert _code(excinfo) == "invalid_celllink"


def test_validate_rejects_reference_override_key():
    celllink = _mod()
    with pytest.raises(Exception) as excinfo:
        celllink.validate_celllink(
            {"cell": CELL, "variantOverrides": {celllink.REFERENCE: {}}}
        )
    assert _code(excinfo) == "invalid_celllink"


# -- resolvePin chokepoint ---------------------------------------------


def test_resolve_pin_explicit_mapping():
    celllink = _mod()
    block = _block(
        {"cell": CELL, "pinMap": [{"symPin": "A", "cellPin": "in"}]}
    )
    assert celllink.resolve_pin(block, "A") == "in"


def test_resolve_pin_identity_default_for_unlisted():
    celllink = _mod()
    block = _block(
        {"cell": CELL, "pinMap": [{"symPin": "A", "cellPin": "in"}]}
    )
    assert celllink.resolve_pin(block, "Y") == "Y"


def test_resolve_pin_identity_without_any_link():
    celllink = _mod()
    assert celllink.resolve_pin(_block(), "CLK") == "CLK"


def test_resolve_pin_variant_override():
    celllink = _mod()
    block = _block(
        {
            "cell": CELL,
            "pinMap": [{"symPin": "A", "cellPin": "in"}],
            "variantOverrides": {
                "fast": {"pinEdits": {"A": "in_fast", "Y": "out_fast"}}
            },
        }
    )
    assert celllink.resolve_pin(block, "A", variant="fast") == "in_fast"
    assert celllink.resolve_pin(block, "Y", variant="fast") == "out_fast"
    assert celllink.resolve_pin(block, "A") == "in"


def test_resolve_pin_unknown_variant_named():
    celllink = _mod()
    block = _block({"cell": CELL, "variantOverrides": {"tt": {}}})
    with pytest.raises(Exception) as excinfo:
        celllink.resolve_pin(block, "A", variant="ss")
    assert _code(excinfo) == "unknown_variant"
    assert "ss" in str(excinfo.value)


def test_resolve_cell_variant_override():
    celllink = _mod()
    block = _block(
        {
            "cell": CELL,
            "variantOverrides": {"hv": {"cell": "sky130A:sky130_fd_sc_hvl__inv_2"}},
        }
    )
    assert celllink.resolve_cell(block) == CELL
    assert (
        celllink.resolve_cell(block, variant="hv")
        == "sky130A:sky130_fd_sc_hvl__inv_2"
    )


def test_reference_variant_always_resolves_stored_base():
    celllink = _mod()
    block = _block(
        {
            "cell": CELL,
            "pinMap": [{"symPin": "A", "cellPin": "in"}],
            "variantOverrides": {
                "fast": {"cell": "other:cell", "pinEdits": {"A": "x"}}
            },
        }
    )
    ref = celllink.resolve_link(block, variant=celllink.REFERENCE)
    base = celllink.resolve_link(block)
    assert (ref["cell"], ref["pinMap"]) == (base["cell"], base["pinMap"])


def test_resolution_never_mutates_storage():
    celllink = _mod()
    block = _block(
        {
            "cell": CELL,
            "pinMap": [{"symPin": "A", "cellPin": "in"}],
            "variantOverrides": {"fast": {"pinEdits": {"A": "x"}}},
        }
    )
    frozen = copy.deepcopy(block)
    celllink.resolve_link(block, variant="fast")
    celllink.resolve_pin(block, "A", variant="fast")
    assert block == frozen


def test_resolve_link_keeps_order_edits_in_place_appends_sorted():
    celllink = _mod()
    block = _block(
        {
            "cell": CELL,
            "pinMap": [
                {"symPin": "B", "cellPin": "b"},
                {"symPin": "A", "cellPin": "a"},
            ],
            "variantOverrides": {"v": {"pinEdits": {"A": "a2", "Z": "z", "M": "m"}}},
        }
    )
    resolved = celllink.resolve_link(block, variant="v")
    assert resolved["variant"] == "v"
    assert resolved["pinMap"] == [
        {"symPin": "B", "cellPin": "b"},
        {"symPin": "A", "cellPin": "a2"},
        {"symPin": "M", "cellPin": "m"},
        {"symPin": "Z", "cellPin": "z"},
    ]
    assert resolved["cell"] == CELL


# -- KiCad chooser filter semantics ------------------------------------


def test_filters_empty_matches_all():
    celllink = _mod()
    assert celllink.match_cell_filters(CELL, []) is True


@pytest.mark.parametrize(
    "pattern, cell, expected",
    [
        ("sky130*", CELL, True),  # wildcard over lib:cell text
        ("SKY130*", CELL, True),  # case-insensitive
        ("gf180*", CELL, False),
        ("sky130A:sky130_fd_sc_hd__*", CELL, True),  # lib:cell split
        ("gf180mcu:sky130_fd_sc_hd__*", CELL, False),  # lib must match too
        ("sky130A:*inv_?", CELL, True),  # ? is one char
        ("sky130A:*inv_??", CELL, False),
        ("*inv_2", CELL, True),  # unanchored only via explicit *
        ("inv_2", CELL, False),  # anchored: bare text is not a substring
        ("sky130A:sky130 fd sc hd__inv_2", CELL, True),  # space -> _
    ],
)
def test_filters_kicad_semantics(pattern, cell, expected):
    celllink = _mod()
    assert celllink.match_cell_filters(cell, [pattern]) is expected


def test_filters_or_across_entries():
    celllink = _mod()
    assert (
        celllink.match_cell_filters(CELL, ["gf180*", "sky130A:sky130*"]) is True
    )
    assert celllink.match_cell_filters(CELL, ["gf180*", "ihp*"]) is False


# -- ERC collection: checks only, never enforcement --------------------


def test_collect_erc_reports_cell_and_filters_without_enforcing():
    celllink = _mod()
    assert celllink.collect_erc(
        {"cell": "noplib:nosuchcell", "cellFilters": ["sky130*"]}
    ) == {"cell": "noplib:nosuchcell", "filters": ["sky130*"]}
