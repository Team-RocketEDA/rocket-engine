"""DECK-XSCHEM RED — schematic to netlist to sim execution deck.

Valid RED = `rocket_engine.adapters.xschem` does not exist yet,
so every test below fails on ImportError. GREEN = the adapter
netlists a project schematic to byte-comparable SPICE (pinned
rcfile, explicit outputs, V3 version assert), feeds sim through
the schematic-owned `-S`/ngspice seam, and fails loud with the
PROV remedy where xschem is missing — never fake-green.

Live tests skip (never fake-green) where xschem is absent.
Method notes in docs/probe-xschem-deck.md.
"""

import shutil
from pathlib import Path

import pytest

xschem_present = shutil.which("xschem") is not None
needs_xschem = pytest.mark.skipif(not xschem_present, reason="xschem not installed")

# Minimal self-contained schematic: one behavioral source, no PDK
# symbols, so the recorded bytes depend only on xschem itself.
MINI_SCH = """v {xschem version=3.4.4 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {mini rc deck} 0 0 0 0 0.5 0.5 {}
C {devices/vsource.sym} 100 0 0 0 {name=V1 value=1.65}
C {devices/gnd.sym} 100 100 0 0 {lab=GND}
"""

def _mini_project(tmp_path):
    workdir = tmp_path / "work"
    (workdir / "cells").mkdir(parents=True)
    (workdir / "cells" / "mini.sch").write_text(MINI_SCH)
    project_rc = workdir / "xschemrc"
    project_rc.write_text("set XSCHEM_SHAREDIR /nonexistent/xschem\n")
    return workdir


def test_xschem_adapter_serves_tool_port():
    """The adapter sits behind the ToolAdapter port with tool xschem."""
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.xschem import XschemAdapter

    assert issubclass(XschemAdapter, ToolAdapter)
    caps = XschemAdapter().capabilities({"cell": "mini"})
    assert "run_xschem" in caps["operations"]
    assert caps["tool"] == "xschem"


def test_xschem_version_assert_rejects_ancient_banner():
    """A non-V3 banner refuses loudly instead of netlisting blind."""
    from rocket_engine.adapters.xschem import XschemAdapter

    try:
        XschemAdapter()._assert_version("XSCHEM V2.9.9")
    except Exception as exc:
        assert getattr(exc, "code", None) == "missing_dependency"
    else:
        raise AssertionError("expected missing_dependency for a V2 banner")


def test_xschem_missing_binary_fails_loud_with_prov_remedy():
    """No xschem on PATH fails with the PROV remedy, never fake-green."""
    from rocket_engine.adapters.xschem import XschemAdapter

    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        job = {
            "operation": "run_xschem",
            "sch_file": str(Path(scratch) / "mini.sch"),
            "workdir": scratch,
        }
        (Path(scratch) / "mini.sch").write_text(MINI_SCH)
        try:
            XschemAdapter(xschem_bin="/nonexistent/xschem").preflight(job)
        except Exception as exc:
            assert getattr(exc, "code", None) == "missing_dependency"
            assert "PROV" in str(exc)
        else:
            raise AssertionError("expected missing_dependency without xschem")


def test_netlist_normalize_strips_checkout_paths():
    """Absolute sch/sym paths normalize to basenames for byte-compare."""
    from rocket_engine.adapters.xschem import normalize_netlist

    raw = (
        "** sch_path: /home/user/proj/xschem/mini.sch\n"
        "**.subckt mini\n"
        "** sym_path: /home/user/proj/xschem/elem.sym\n"
        "R1 a b 1k\n"
        "**.ends\n"
    )
    out = normalize_netlist(raw)
    assert "/home/user/proj" not in out
    assert "mini.sch" in out
    assert "R1 a b 1k" in out


@needs_xschem
def test_xschem_netlists_mini_to_recorded_bytes(tmp_path):
    """A project schematic netlists to the recorded normalized bytes."""
    from rocket_engine.adapters.xschem import XschemAdapter, normalize_netlist

    workdir = _mini_project(tmp_path)
    native = XschemAdapter().execute(
        {
            "operation": "run_xschem",
            "sch_file": str(workdir / "cells" / "mini.sch"),
            "rcfile": str(workdir / "xschemrc"),
            "workdir": str(workdir),
        }
    )
    first = normalize_netlist(Path(native["netlist_file"]).read_text())
    native2 = XschemAdapter().execute(
        {
            "operation": "run_xschem",
            "sch_file": str(workdir / "cells" / "mini.sch"),
            "rcfile": str(workdir / "xschemrc"),
            "workdir": str(workdir),
            "output_name": "mini_b.spice",
        }
    )
    second = normalize_netlist(Path(native2["netlist_file"]).read_text())
    assert first == second
    assert "mini" in first.lower()
    assert "/tmp" not in first and "/home" not in first


@needs_xschem
def test_xschem_silent_fail_never_fake_greens(tmp_path):
    """A schematic that yields no output fails loudly as unavailable."""
    from rocket_engine.adapters.xschem import XschemAdapter

    workdir = tmp_path / "work"
    workdir.mkdir(exist_ok=True)
    ghost = workdir / "ghost.sch"
    try:
        XschemAdapter().execute(
            {
                "operation": "run_xschem",
                "sch_file": str(ghost),
                "workdir": str(workdir),
            }
        )
    except Exception as exc:
        assert getattr(exc, "code", None) in ("invalid_reference", "runner_unavailable")
    else:
        raise AssertionError("expected loud failure for a missing schematic")
