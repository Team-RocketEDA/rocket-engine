"""PDK-UBC RED — lane proof: PDK DRC deck run with golden expectations.

Valid RED = the lane profile + fixture do not exist yet, so the
proof fails on FileNotFoundError before touching KLayout. GREEN
runs the PDK's own SiEPIC_EBeam_DRC deck (checks verbatim; only
the 2-line batch header — source($input)/report-to-file, the
same shape the sky130 deck carries inline — is added, because
the deck as-shipped is GUI-oriented and errors in batch) through
KlayoutDrcAdapter deck mode: the lane fixture (upstream
reference MZI GDS, MIT) reports exactly the 6 documented
Boundary items (bare cell, no layer-99 floorplan) with zero
physical violations, and a synthesized bad layout reports the
golden Si_width + Si_space hits. Skips LOUDLY where klayout or
the ubc source tree is absent.

Fixture provenance: fixtures/mzi_ref.gds is a byte copy of
tests/gds_ref_si220/mzi.gds in gdsfactory/ubc @598a773 (MIT);
sha256 pinned below.
"""

import hashlib
import shutil
from collections import Counter

import pytest

from ._profile import FIXTURES, find_ubc_root, load_profile

FIXTURE_SHA256 = (
    "722b1aea10ea00c6046c97e08188ee6a604a31a72baeedea0f89b1f57fbc1bb1"
)

BATCH_ANCHOR = 'report("SiEPIC-EBeam-PDK DRC")'
BATCH_HEADER = """if $input
  source($input)
end

if $report
  report("SiEPIC-EBeam-PDK DRC", $report)
else
  report("SiEPIC-EBeam-PDK DRC")
end"""

klayout_present = shutil.which("klayout") is not None
ubc_present = find_ubc_root() is not None
needs_lane = pytest.mark.skipif(
    not (klayout_present and ubc_present),
    reason="ubc lane DRC live: klayout not on PATH or no ubc source "
    "tree (fixtures/upstream/ubc, scripts/fetch_fixtures.py --only ubc)",
)


def _fixture():
    gds = FIXTURES / "mzi_ref.gds"
    if not gds.is_file():
        raise FileNotFoundError(f"ubc lane fixture not found: {gds}.")
    digest = hashlib.sha256(gds.read_bytes()).hexdigest()
    assert digest == FIXTURE_SHA256
    return gds


def _deck_harness(tmp_path):
    """PDK deck text + 2-line batch header (checks otherwise verbatim)."""
    profile = load_profile()  # RED: missing profile.yaml
    root = find_ubc_root()
    assert root is not None
    deck_text = (root / profile["variants"]["ebeam"]["drc"]["deck"]).read_text()
    assert deck_text.count(BATCH_ANCHOR) == 1
    harness = deck_text.replace(BATCH_ANCHOR, BATCH_HEADER)
    # Verbatim check: harness differs from the deck only at the header.
    assert harness.replace(BATCH_HEADER, BATCH_ANCHOR) == deck_text
    deck_file = tmp_path / "ubc_deck_batch.lydrc"
    deck_file.write_text(harness)
    return deck_file


def _run_deck(gds_file, deck_file, workdir):
    from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

    adapter = KlayoutDrcAdapter()
    return adapter.parse(
        adapter.execute(
            {
                "operation": "run_drc",
                "gds_file": str(gds_file),
                "deck_file": str(deck_file),
                "workdir": str(workdir),
            }
        )
    )


@needs_lane
def test_lane_drc_reference_mzi_reports_boundary_only(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    staged = work / "mzi_ref.gds"
    shutil.copy(_fixture(), staged)
    result = _run_deck(staged, _deck_harness(tmp_path), work)
    profile = load_profile()  # RED: missing profile.yaml
    want = profile["proofs"]["drc"]
    assert result["total"] == want["reference_total"] == 6
    by_rule = Counter(v["rule"] for v in result["violations"])
    assert dict(by_rule) == want["reference_rules"] == {"Boundary": 6}
    # Zero physical violations on the reference cell.
    assert not any(
        v["rule"].startswith(("Si_", "Sip6nm", "M1_", "M2_"))
        for v in result["violations"]
    )


@needs_lane
def test_lane_drc_bad_layout_reports_si_goldens(tmp_path):
    import klayout.db as kdb

    work = tmp_path / "work"
    work.mkdir()
    layout = kdb.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("BAD")
    layer = layout.layer(1, 0)
    top.shapes(layer).insert(kdb.Box(0, 0, 40, 10000))  # 40 nm sliver
    top.shapes(layer).insert(kdb.Box(20000, 0, 30000, 10000))
    top.shapes(layer).insert(kdb.Box(30040, 0, 40040, 10000))  # 40 nm gap
    bad = work / "bad.gds"
    layout.write(str(bad))
    result = _run_deck(bad, _deck_harness(tmp_path), work)
    assert result["total"] == 5
    by_rule = Counter(v["rule"] for v in result["violations"])
    assert dict(by_rule) == {"Boundary": 3, "Si_space": 1, "Si_width": 1}
