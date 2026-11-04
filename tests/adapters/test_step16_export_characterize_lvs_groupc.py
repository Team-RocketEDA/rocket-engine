"""Step-16 part-2 dump-first pin: export + characterize + LVS/XOR + group C.

Valid RED = ``tests/adapters/fixtures/step16/*.json`` do not exist
yet, so every fixture-loading test fails with FileNotFoundError.
GREEN = the committed good/bad natives parse deterministically
through the committed adapters (xschem export, vlsirtools export,
cace characterize re-verified at the 2.13.0 pin, klayout LVS plus
layout_xor, group-C meow/devsim/meep/elmer dumps) and the catalog
carries no standalone kfactory provider (RULING-07: kfactory is an
internal gdsfactory component).

Dump-first: live runs need xschem/cace/klayout/meep on PATH and
skip loudly without them; every parse probe runs hermetically off
the committed fixtures.
"""

import json
import re
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "step16"
SRC = Path(__file__).resolve().parent.parent.parent / "src"


def load(name):
    """Read one committed Step-16 native fixture.

    Args:
        name: Fixture filename under fixtures/step16.

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


def test_step16_xschem_export_normalizes_deterministically():
    """Raw xschem netlist normalizes to basenames, twice identically."""
    from rocket_engine.adapters.xschem import normalize_netlist

    raw = (FIX / "xschem_netlist.txt").read_text()
    first = normalize_netlist(raw)
    second = normalize_netlist((FIX / "xschem_netlist.txt").read_text())
    assert first == second
    assert "** sch_path: mini.sch" in first
    assert str(FIX) not in first


def test_step16_xschem_capabilities_serve_export():
    """The xschem adapter serves run_xschem with tool xschem."""
    from rocket_engine.adapters.xschem import XschemAdapter

    caps = XschemAdapter().capabilities({})
    assert "run_xschem" in caps["operations"]
    assert caps["tool"] == "xschem"


def test_step16_vlsir_export_is_deterministic():
    """Committed package emits byte-identical netlists twice."""
    from rocket_engine.adapters.vlsir import VlsirAdapter

    pkg = load("vlsir_package.json")
    first = VlsirAdapter.emit_netlist(pkg, fmt="spice")
    second = VlsirAdapter.emit_netlist(load("vlsir_package.json"), fmt="spice")
    assert first == second
    assert ".SUBCKT dup_top" in first


def test_step16_vlsir_capabilities_serve_generate_views():
    """The vlsir adapter serves generate_views with tool vlsir."""
    from rocket_engine.adapters.vlsir import VlsirAdapter

    caps = VlsirAdapter().capabilities({})
    assert "generate_views" in caps["operations"]
    assert caps["tool"] == "vlsir"


def test_step16_cace_good_summary_is_clean_and_deterministic():
    """All-Pass summary.md parses clean, twice identically."""
    from rocket_engine.adapters.cace import CaceAdapter

    first = CaceAdapter().parse(load("cace_pass.json"))
    second = CaceAdapter().parse(load("cace_pass.json"))
    assert first["total"] == 0
    assert first["source"] == "summary_md"
    assert first == second
    assert json.loads(json.dumps(first)) == first


def test_step16_cace_bad_summary_reports_violations():
    """Fail-row summary parses to violations, never clean."""
    from rocket_engine.adapters.cace import CaceAdapter

    result = CaceAdapter().parse(load("cace_fail.json"))
    assert result["total"] >= 1
    assert result["source"] == "summary_md"


def test_step16_cace_preflight_refuses_bad_operation():
    """A wrong operation refuses loudly with no binary needed."""
    from rocket_engine.adapters.cace import CaceAdapter

    assert code_of(CaceAdapter().preflight, {"operation": "run_spice"}) == (
        "unsupported_operation"
    )


def test_step16_klayout_lvs_clean_parses_clean():
    """Matching layout/schematic parses clean, twice identically."""
    from rocket_engine.adapters.drc.klayout import KlayoutLvsAdapter

    first = KlayoutLvsAdapter().parse(load("lvs_clean.json"))
    second = KlayoutLvsAdapter().parse(load("lvs_clean.json"))
    assert first["total"] == 0
    assert first == second


def test_step16_klayout_lvs_mismatch_reports_violation():
    """Mismatched devices parse to violations, never clean."""
    from rocket_engine.adapters.drc.klayout import KlayoutLvsAdapter

    result = KlayoutLvsAdapter().parse(load("lvs_mismatch.json"))
    assert result["total"] >= 1


def test_step16_layout_xor_clean_is_zero():
    """Zero XOR differences parse to zero violations."""
    from rocket_engine.adapters.drc.klayout import run_xor_summary

    result = run_xor_summary(load("xor_clean.json"))
    assert result["total"] == 0


def test_step16_layout_xor_dirty_reports_differences():
    """N XOR differences parse to exactly N violations."""
    from rocket_engine.adapters.drc.klayout import run_xor_summary

    result = run_xor_summary(load("xor_dirty.json"))
    assert result["total"] == 2
    assert len(result["violations"]) == 2


def test_step16_devsim_good_dump_is_clean_with_measurements():
    """Converged devsim dump parses clean with current measurements."""
    from rocket_engine.adapters.devsim import DevsimAdapter

    first = DevsimAdapter().parse(load("devsim_good.json"))
    second = DevsimAdapter().parse(load("devsim_good.json"))
    assert first["total"] == 0
    assert first["source"] == "dump"
    assert any(m["name"].startswith("current.") for m in first["measurements"])
    assert first == second


def test_step16_devsim_bad_dump_reports_convergence():
    """Non-converged devsim dump parses to a tcad violation."""
    from rocket_engine.adapters.devsim import DevsimAdapter

    result = DevsimAdapter().parse(load("devsim_bad.json"))
    assert result["total"] >= 1


def test_step16_meep_dump_is_clean_with_flux():
    """In-API meep dump parses clean with flux measurements."""
    from rocket_engine.adapters.meep import MeepAdapter

    first = MeepAdapter().parse(load("meep_good.json"))
    second = MeepAdapter().parse(load("meep_good.json"))
    assert first["total"] == 0
    assert first["source"] == "dump"
    assert any(m["name"] == "flux" for m in first["measurements"])
    assert first == second


def test_step16_elmer_good_dump_is_clean():
    """Converged SaveScalars dump parses clean with measurements."""
    from rocket_engine.adapters.elmer import ElmerAdapter

    first = ElmerAdapter().parse(load("elmer_good.json"))
    second = ElmerAdapter().parse(load("elmer_good.json"))
    assert first["total"] == 0
    assert first["source"] == "dump"
    assert first == second


def test_step16_elmer_bad_dump_reports_convergence():
    """Non-converged Elmer dump parses to an fem violation."""
    from rocket_engine.adapters.elmer import ElmerAdapter

    result = ElmerAdapter().parse(load("elmer_bad.json"))
    assert result["total"] >= 1


def test_step16_meow_capabilities_and_preflight_refusal():
    """The meow adapter serves run_em and refuses bad input loudly."""
    from rocket_engine.adapters.meow.adapter import MeowAdapter

    caps = MeowAdapter().capabilities({})
    assert "run_em" in caps["operations"]
    assert caps["tool"] == "meow"
    assert code_of(MeowAdapter().preflight, {"operation": "run_spice"}) == (
        "unsupported_operation"
    )


def test_step16_kfactory_has_no_standalone_provider():
    """kfactory stays internal: no direct import, no solver entry."""
    hits = []
    for path in sorted((SRC / "adapters").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(errors="replace")
        if re.search(r"(?m)^\s*(import kfactory|from kfactory)\b", text):
            hits.append(str(path))
    assert hits == []
    composition = (SRC / "composition.py").read_text()
    assert "kfactory" not in composition
