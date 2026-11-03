"""ANTENNA-KLAYOUT RED — KLayout-DB antenna path + fixtures.

Valid RED = no antenna surface exists in
`rocket_engine.adapters.drc.klayout`, so the imports below fail.
GREEN = a DB-backed antenna check (no foundry deck, no binary
gate beyond importable pya): per-island metal-to-gate area ratio
over the cell, violating islands reported with rule, ratio, and
metric bbox. Openroad-standalone stays out of scope by ticket
demotion (see docs/tickets/ANTENNA-KLAYOUT.md).

Method notes in docs/probe-antenna-klayout.md.
"""

import pytest

pytest.importorskip("pya")


def _cells(tmp_path, islands):
    """Build a one-cell GDS: metal islands on layer 10/0, gate on 1/0.

    Args:
        tmp_path: Pytest scratch dir.
        islands: Sequence of (metal_box, gate_box_or_None) in dbu.

    Returns:
        Path to the written GDS file.
    """
    import pya

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    layout = pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    metal = layout.layer(10, 0)
    gate = layout.layer(1, 0)
    for metal_box, gate_box in islands:
        top.shapes(metal).insert(pya.Box(*metal_box))
        if gate_box is not None:
            top.shapes(gate).insert(pya.Box(*gate_box))
    gds = workdir / "antenna.gds"
    layout.write(str(gds))
    return gds


def test_antenna_honors_capabilities(tmp_path):
    """The antenna adapter serves run_antenna via the klayout tool."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    caps = AntennaKlayoutAdapter().capabilities({"cell": "TOP"})
    assert "run_antenna" in caps["operations"]
    assert caps["tool"] == "klayout"


def test_antenna_clean_cell_reports_zero(tmp_path):
    """Small metal over generous gate stays under the ratio cap."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    gds = _cells(tmp_path, [((0, 0, 2000, 2000), (0, 0, 2000, 2000))])
    adapter = AntennaKlayoutAdapter()
    job = {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(tmp_path / "work"),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": 100.0},
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 0
    assert result["violations"] == []


def test_antenna_oversize_island_violates_with_ratio_and_bbox(tmp_path):
    """A huge island on a sliver gate fails with a named antenna rule."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    gds = _cells(tmp_path, [((0, 0, 100000, 100000), (0, 0, 100, 100))])
    adapter = AntennaKlayoutAdapter()
    job = {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(tmp_path / "work"),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": 100.0},
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 1
    (violation,) = result["violations"]
    assert violation["rule"] == "antenna_ratio"
    assert violation["ratio"] > 100.0
    assert len(violation["bbox_um"]) == 4


def test_antenna_floating_island_without_gate_is_flagged(tmp_path):
    """Metal with no gate overlap cannot discharge: flagged, not divided."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    gds = _cells(tmp_path, [((0, 0, 50000, 50000), None)])
    adapter = AntennaKlayoutAdapter()
    job = {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(tmp_path / "work"),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": 100.0},
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "antenna_floating"


def test_antenna_mixed_islands_report_only_violators(tmp_path):
    """Clean and violating islands in one cell: only violators listed."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    gds = _cells(
        tmp_path,
        [
            ((0, 0, 2000, 2000), (0, 0, 2000, 2000)),
            ((100000, 100000, 200000, 200000), (100000, 100000, 100100, 100100)),
        ],
    )
    adapter = AntennaKlayoutAdapter()
    job = {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(tmp_path / "work"),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": 100.0},
    }
    result = adapter.parse(adapter.execute(job))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "antenna_ratio"


def test_antenna_preflight_refuses_bad_rules(tmp_path):
    """Non-positive ratio or malformed layers refuse loudly."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    gds = _cells(tmp_path, [((0, 0, 2000, 2000), (0, 0, 2000, 2000))])
    adapter = AntennaKlayoutAdapter()
    bad = {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(tmp_path / "work"),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": -5.0},
    }
    try:
        adapter.preflight(bad)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for a bad ratio")


def test_antenna_preflight_refuses_missing_gds(tmp_path):
    """A missing GDS refuses loudly instead of checking nothing."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    job = {
        "operation": "run_antenna",
        "gds_file": str(tmp_path / "ghost.gds"),
        "workdir": str(tmp_path),
        "rules": {"metal_layer": [10, 0], "gate_layer": [1, 0], "max_ratio": 100.0},
    }
    try:
        AntennaKlayoutAdapter().preflight(job)
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a missing GDS")
