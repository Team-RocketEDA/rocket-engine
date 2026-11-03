"""ASAP7-DRC-DECK: inventory + deck-coverage static checks (no klayout needed).

The lane directory carries the full DRM rule inventory, the .drc deck,
the fixture spec/generator, and the generated tech files. These tests
pin the inventory counts (201 DRM table rows, 333 instantiated checks),
the implemented-vs-deferred split, and that every implemented rule
category is actually emitted by the deck. RED signal: the lane files
are missing, so every test fails on FileNotFoundError until they land.
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LANE = REPO_ROOT / "docs" / "work" / "ASAP7-DRC-DECK"
INVENTORY = LANE / "inventory.md"
DECK = LANE / "asap7.drc"
SPEC = LANE / "fixtures" / "spec.json"
MAKE_FIXTURES = LANE / "fixtures" / "make_fixtures.py"
GEN_TECH = LANE / "tech" / "gen_tech.py"
LYT = LANE / "tech" / "asap7.lyt"
LYP = LANE / "tech" / "asap7.lyp"

EXPECTED_TABLE_ROWS = 201
EXPECTED_INSTANTIATED = 331
EXPECTED_NOTE_RULES = 1


def _read_inventory():
    if not INVENTORY.is_file():
        raise FileNotFoundError(f"lane inventory not found: {INVENTORY}.")
    return INVENTORY.read_text()


def _read_deck():
    if not DECK.is_file():
        raise FileNotFoundError(f"lane deck not found: {DECK}.")
    return DECK.read_text()


def _read_spec():
    if not SPEC.is_file():
        raise FileNotFoundError(f"fixture spec not found: {SPEC}.")
    return json.loads(SPEC.read_text())


def test_lane_files_present():
    missing = [str(p) for p in (
        INVENTORY, DECK, SPEC, MAKE_FIXTURES, GEN_TECH, LYT, LYP,
    ) if not p.is_file()]
    assert not missing, f"lane files missing: {missing}"


def test_inventory_counts_match_drm():
    text = _read_inventory()
    rows = re.search(r"^table-rows:\s*(\d+)\s*$", text, re.M)
    inst = re.search(r"^instantiated:\s*(\d+)\s*$", text, re.M)
    note = re.search(r"^note-rules:\s*(\d+)\s*$", text, re.M)
    assert rows, "inventory.md must carry a 'table-rows: N' count line"
    assert inst, "inventory.md must carry an 'instantiated: N' count line"
    assert note, "inventory.md must carry a 'note-rules: N' count line"
    assert int(rows.group(1)) == EXPECTED_TABLE_ROWS
    assert int(inst.group(1)) == EXPECTED_INSTANTIATED
    assert int(note.group(1)) == EXPECTED_NOTE_RULES


def test_inventory_marks_implemented_and_deferred():
    text = _read_inventory()
    assert "## Implemented" in text
    assert "## Deferred" in text
    n_impl = len(re.findall(r"^- IMPL ", text, re.M))
    n_def = len(re.findall(r"^- DEFER ", text, re.M))
    n_note = len(re.findall(r"^- IMPL-NOTE ", text, re.M))
    assert n_impl > 0 and n_def > 0
    assert n_impl + n_def == EXPECTED_TABLE_ROWS, (
        f"implemented ({n_impl}) + deferred ({n_def}) must equal "
        f"{EXPECTED_TABLE_ROWS} DRM table rows"
    )
    assert n_note == EXPECTED_NOTE_RULES


def test_every_implemented_category_emitted_by_deck():
    deck = _read_deck()
    spec = _read_spec()
    categories = set()
    for entry in spec["breakers"]:
        categories.add(entry["rule"])
        categories.update(entry.get("also", []))
    missing = sorted(c for c in categories if f'output("{c}"' not in deck)
    assert not missing, f"deck never outputs categories: {missing}"


def test_every_breaker_has_shapes_and_exactness_contract():
    spec = _read_spec()
    ids = set()
    for entry in spec["breakers"]:
        assert entry["id"] not in ids, f"duplicate breaker id: {entry['id']}"
        ids.add(entry["id"])
        shapes = entry.get("shapes", {})
        polys = entry.get("polygons", {})
        assert shapes or polys, f"breaker {entry['id']} has no geometry"
        assert entry["rule"] not in entry.get("also", [])


def test_clean_refs_present_in_spec():
    spec = _read_spec()
    ids = {entry["id"] for entry in spec["cleans"]}
    assert "clean_all" in ids, "spec must define the clean_all synthetic ref"
    assert "empty" in ids, "spec must define the empty-layout control"
