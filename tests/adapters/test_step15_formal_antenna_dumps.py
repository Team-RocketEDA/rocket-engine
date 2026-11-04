"""Step-15 dump-first pin: eqy, mcy, and KLayout-DB antenna fixtures.

Valid RED = ``tests/adapters/fixtures/step15/*.json`` do not exist
yet, so every fixture-loading test fails with FileNotFoundError.
GREEN = the six committed good/bad natives parse deterministically
through the three committed adapters (equivalence, mutation,
KLayout-DB antenna) with clean-good / violating-bad verdicts, and
no openroad-standalone path exists anywhere in ``src/adapters``.

Dump-first: eqy gates on the V1 verdict filename plus the DONE
line; mcy reads the sqlite DB rows plus output.txt streaming rows;
antenna counts island violations from the layout DB. Live runs need
eqy/mcy/klayout on PATH and skip loudly without them; the antenna
execute probe needs only importable pya and runs hermetically.
"""

import json
from pathlib import Path

import pytest

try:
    import pya as _pya
except ImportError:
    _pya = None

needs_pya = pytest.mark.skipif(
    _pya is None, reason="BLOCKED-needs-host: pya absent"
)

FIX = Path(__file__).resolve().parent / "fixtures" / "step15"


def load(name):
    """Read one committed Step-15 native fixture.

    Args:
        name: Fixture filename under fixtures/step15.

    Returns:
        Parsed JSON native output mapping.
    """
    return json.loads((FIX / name).read_text())


def code_of(func, job):
    """Run a preflight func and return the AdapterError code it raises.

    Args:
        func: Preflight callable expected to raise AdapterError.
        job: Solver job mapping passed to func.

    Returns:
        The raised error's code string.

    Raises:
        AssertionError: func returned without raising.
    """
    try:
        func(job)
    except Exception as exc:
        return getattr(exc, "code", None)
    raise AssertionError("expected AdapterError")


def test_step15_eqy_good_dump_is_clean_and_deterministic():
    """PASS verdict file plus DONE line parses clean, twice identically."""
    from rocket_engine.adapters.equivalence import EqyAdapter

    native = load("eqy_pass.json")
    first = EqyAdapter().parse(native)
    second = EqyAdapter().parse(load("eqy_pass.json"))
    assert first["total"] == 0
    assert first["verdict"] == "PASS"
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_step15_eqy_bad_dump_reports_violation():
    """FAIL verdict plus a failed partition yields violations."""
    from rocket_engine.adapters.equivalence import EqyAdapter

    result = EqyAdapter().parse(load("eqy_fail.json"))
    assert result["total"] >= 1
    assert result["verdict"] == "FAIL"


def test_step15_eqy_capabilities_advertise_formal_eqy():
    """The equivalence adapter serves run_formal with tool eqy."""
    from rocket_engine.adapters.equivalence import EqyAdapter

    caps = EqyAdapter().capabilities({})
    assert "run_formal" in caps["operations"]
    assert caps["tool"] == "eqy"


def test_step15_eqy_preflight_refuses_bad_inputs():
    """Bad operation and missing config refuse loudly, no binary needed."""
    from rocket_engine.adapters.equivalence import EqyAdapter

    assert code_of(EqyAdapter().preflight, {"operation": "run_spice"}) == (
        "unsupported_operation"
    )
    assert code_of(
        EqyAdapter().preflight,
        {"operation": "run_formal", "config": "no-such.eqy"},
    ) == "invalid_reference"


def test_step15_mcy_good_dump_has_full_coverage():
    """All-covered DB rows parse clean with coverage 1.0, deterministically."""
    from rocket_engine.adapters.mutation import McyAdapter

    native = load("mcy_covered.json")
    first = McyAdapter().parse(native)
    second = McyAdapter().parse(load("mcy_covered.json"))
    assert first["total"] == 0
    assert first["coverage"] == 1.0
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_step15_mcy_bad_dump_reports_uncovered():
    """An uncovered mutation row yields a violation and partial coverage."""
    from rocket_engine.adapters.mutation import McyAdapter

    result = McyAdapter().parse(load("mcy_uncovered.json"))
    assert result["total"] >= 1
    assert result["coverage"] < 1.0


def test_step15_mcy_capabilities_advertise_run_mutation():
    """The mutation adapter serves run_mutation with tool mcy."""
    from rocket_engine.adapters.mutation import McyAdapter

    caps = McyAdapter().capabilities({})
    assert "run_mutation" in caps["operations"]
    assert caps["tool"] == "mcy"


def test_step15_mcy_preflight_refuses_bad_inputs():
    """Bad operation and missing project refuse loudly, no binary needed."""
    from rocket_engine.adapters.mutation import McyAdapter

    assert code_of(McyAdapter().preflight, {"operation": "run_spice"}) == (
        "unsupported_operation"
    )
    assert code_of(
        McyAdapter().preflight,
        {"operation": "run_mutation", "project": "no-such-project"},
    ) == "invalid_reference"


def test_step15_mcy_output_txt_streaming_rows():
    """output.txt `<idx> <RESULT>` lines stream per-task verdicts."""
    from rocket_engine.adapters.mutation import McyAdapter

    rows = McyAdapter.parse_output_txt("1 PASS\n2 FAIL\n")
    assert rows == [
        {"mutation_id": 1, "result": "PASS"},
        {"mutation_id": 2, "result": "FAIL"},
    ]


def test_step15_antenna_clean_parse_is_zero():
    """An empty island-violation list parses to zero total."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    result = AntennaKlayoutAdapter().parse(load("antenna_clean.json"))
    assert result == {"total": 0, "violations": []}


def test_step15_antenna_violation_parse_names_rules():
    """Ratio and floating islands parse with rule plus metric bbox."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    first = AntennaKlayoutAdapter().parse(load("antenna_violation.json"))
    second = AntennaKlayoutAdapter().parse(load("antenna_violation.json"))
    assert first["total"] >= 1
    assert first == second
    assert json.loads(json.dumps(first)) == first
    rules = {v["rule"] for v in first["violations"]}
    assert rules <= {"antenna_ratio", "antenna_floating"}
    assert rules
    for violation in first["violations"]:
        assert len(violation["bbox_um"]) == 4


def test_step15_antenna_capabilities_advertise_klayout():
    """The antenna adapter serves run_antenna with tool klayout."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    caps = AntennaKlayoutAdapter().capabilities({"cell": "TOP"})
    assert "run_antenna" in caps["operations"]
    assert caps["tool"] == "klayout"


def test_step15_antenna_preflight_refuses_bad_inputs():
    """Bad operation and missing GDS refuse loudly, never fake-green."""
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    assert code_of(
        AntennaKlayoutAdapter().preflight, {"operation": "run_drc"}
    ) == "unsupported_operation"
    assert code_of(
        AntennaKlayoutAdapter().preflight,
        {
            "operation": "run_antenna",
            "gds_file": "no-such.gds",
            "rules": {
                "metal_layer": [10, 0],
                "gate_layer": [1, 0],
                "max_ratio": 100.0,
            },
        },
    ) == "invalid_reference"


def _write_gds(workdir, islands):
    """Build a one-cell GDS with metal islands over gate shapes.

    Args:
        workdir: Directory receiving antenna.gds.
        islands: Sequence of (metal_box, gate_box_or_None) in dbu.

    Returns:
        Path to the written GDS file.
    """
    layout = _pya.Layout()
    layout.dbu = 0.001
    top = layout.create_cell("TOP")
    metal = layout.layer(10, 0)
    gate = layout.layer(1, 0)
    for metal_box, gate_box in islands:
        top.shapes(metal).insert(_pya.Box(*metal_box))
        if gate_box is not None:
            top.shapes(gate).insert(_pya.Box(*gate_box))
    gds = Path(workdir) / "antenna.gds"
    layout.write(str(gds))
    return gds


def _antenna_job(gds, workdir):
    """Antenna check job over one GDS with a ratio cap of 100.

    Args:
        gds: GDS layout under check.
        workdir: Run directory for the job.

    Returns:
        Solver job mapping for run_antenna.
    """
    return {
        "operation": "run_antenna",
        "gds_file": str(gds),
        "workdir": str(workdir),
        "rules": {
            "metal_layer": [10, 0],
            "gate_layer": [1, 0],
            "max_ratio": 100.0,
        },
    }


@needs_pya
def test_step15_antenna_execute_clean_and_violating(tmp_path):
    """Hermetic execute: balanced island clean, huge island violates.

    Args:
        tmp_path: Pytest scratch dir for the runtime GDS files.
    """
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    adapter = AntennaKlayoutAdapter()
    clean = _write_gds(
        workdir, [((0, 0, 2000, 2000), (0, 0, 2000, 2000))]
    )
    assert adapter.parse(adapter.execute(_antenna_job(clean, workdir)))[
        "total"
    ] == 0
    big = _write_gds(
        workdir, [((0, 0, 100000, 100000), (0, 0, 100, 100))]
    )
    result = adapter.parse(adapter.execute(_antenna_job(big, workdir)))
    assert result["total"] == 1
    (violation,) = result["violations"]
    assert violation["rule"] == "antenna_ratio"
    assert violation["ratio"] > 100.0
    assert len(violation["bbox_um"]) == 4


@needs_pya
def test_step15_antenna_execute_floating_island_flagged(tmp_path):
    """Metal with no gate overlap flags antenna_floating, never divides.

    Args:
        tmp_path: Pytest scratch dir for the runtime GDS files.
    """
    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    gds = _write_gds(workdir, [((0, 0, 50000, 50000), None)])
    adapter = AntennaKlayoutAdapter()
    result = adapter.parse(adapter.execute(_antenna_job(gds, workdir)))
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "antenna_floating"


def test_step15_no_openroad_standalone_in_adapters():
    """No openroad-standalone path is staffed; antenna rides KLayout-DB.

    The only allowed mentions are demotion notes documenting that the
    standalone path is ruled out (ticket demotion); any adapter
    module, class, or binary call for it fails this test.
    """
    import re

    from rocket_engine.adapters.drc.klayout import AntennaKlayoutAdapter

    root = Path(__file__).resolve().parents[2] / "src" / "adapters"
    modules = [
        path
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]
    assert not [p for p in modules if "openroad" in p.name.lower()]
    assert [
        str(p)
        for p in modules
        if re.search(r"class\s+\w*[Oo]penroad\w*", p.read_text())
    ] == []
    staffed = []
    for path in modules:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            lowered = line.lower()
            if "openroad-standalone" in lowered or (
                "openroad_standalone" in lowered
            ):
                markers = (
                    "demot",
                    "not staffed",
                    "never",
                    "ruled out",
                    "without",
                    "instead",
                )
                if not any(mark in lowered for mark in markers):
                    staffed.append(f"{path}:{lineno}: {line.strip()}")
    assert staffed == []
    assert AntennaKlayoutAdapter().capabilities({})["tool"] == "klayout"


def test_step15_tasks_catalog_lists_all_three_tasks():
    """The v1 catalog binds check.equivalence/mutation/antenna tools."""
    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "v1"
            / "catalog"
            / "tasks.json"
        ).read_text()
    )
    assert "eqy" in catalog["check.equivalence"]["tools"]
    assert "mcy" in catalog["check.mutation"]["tools"]
    assert "klayout" in catalog["check.antenna"]["tools"]
