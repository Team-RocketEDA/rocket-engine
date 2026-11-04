"""Step 16 part 1 provider decks: dump-first good/bad fixtures.

Covers simulate.hdl verilator/ghdl, ghdl/amaranth synth, and the
xschem schematic-to-netlist-to-sim deck. Live legs skip (never
fake-green) where the binary is absent; parse/emit legs are pure
unit. RED = XschemDeck plus the s16 fixtures do not exist yet.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
HDL = FIX / "hdl"
SYNTH = FIX / "synth"
XS = FIX / "xschem"

verilator_present = shutil.which("verilator") is not None
ghdl_present = shutil.which("ghdl") is not None
xschem_present = shutil.which("xschem") is not None
needs_verilator = pytest.mark.skipif(
    not verilator_present, reason="verilator not installed")
needs_ghdl = pytest.mark.skipif(not ghdl_present, reason="ghdl not installed")
needs_xschem = pytest.mark.skipif(
    not xschem_present, reason="xschem not installed")

try:
    import amaranth  # noqa: F401

    amaranth_present = True
except ImportError:
    amaranth_present = False
needs_amaranth = pytest.mark.skipif(
    not amaranth_present, reason="amaranth not installed")


@needs_verilator
def test_verilator_good_lints_without_errors(tmp_path):
    """A clean counter lints with zero error-severity violations."""
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    native = VerilatorAdapter().execute({
        "operation": "run_hdl_test",
        "sources": [str(HDL / "s16_ve_good.v")],
        "workdir": str(tmp_path),
    })
    result = VerilatorAdapter().parse(native)
    errors = [v for v in result["violations"] if v["severity"] == "error"]
    assert errors == []


@needs_verilator
def test_verilator_bad_reports_error(tmp_path):
    """A syntax-broken source reports at least one error violation."""
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    native = VerilatorAdapter().execute({
        "operation": "run_hdl_test",
        "sources": [str(HDL / "s16_ve_bad.v")],
        "workdir": str(tmp_path),
    })
    result = VerilatorAdapter().parse(native)
    assert result["total"] >= 1
    assert result["violations"][0]["severity"] == "error"


def test_verilator_missing_source_refuses(tmp_path):
    """A missing source refuses invalid_reference before touching tools."""
    from rocket_engine.adapters.hdl_sim.verilator import VerilatorAdapter

    try:
        VerilatorAdapter().preflight({
            "operation": "run_hdl_test",
            "sources": [str(tmp_path / "ghost.v")],
        })
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a ghost source")


@needs_ghdl
def test_ghdl_good_sim_is_clean(tmp_path):
    """A passing VHDL bench simulates with total 0 (notes never fail)."""
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    native = GhdlAdapter().execute({
        "operation": "run_hdl_test",
        "sources": [str(HDL / "s16_counter.vhdl"),
                    str(HDL / "s16_tb_good.vhdl")],
        "top": "tb_good",
        "workdir": str(tmp_path),
    })
    assert native["exit_code"] == 0
    result = GhdlAdapter().parse(native)
    assert result["total"] == 0


@needs_ghdl
def test_ghdl_bad_sim_reports_assert(tmp_path):
    """A failing assert reports an assert_error naming file and line."""
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    native = GhdlAdapter().execute({
        "operation": "run_hdl_test",
        "sources": [str(HDL / "s16_counter.vhdl"),
                    str(HDL / "s16_tb_bad.vhdl")],
        "top": "tb_bad",
        "workdir": str(tmp_path),
    })
    result = GhdlAdapter().parse(native)
    assert result["total"] >= 1
    first = result["violations"][0]
    assert first["rule"] == "assert_error"
    assert first["file"].endswith("s16_tb_bad.vhdl")
    assert first["line"] > 0


@needs_ghdl
def test_ghdl_broken_source_fails_execute(tmp_path):
    """Dump pin: a syntax-broken source fails natively with diags.

    Execute exits nonzero with compile diagnostics on stderr; the
    sim-stdout parse path stays silent on it (solver reports the
    native code, never a parsed-clean verdict from this test).
    """
    from rocket_engine.adapters.hdl_sim.ghdl import GhdlAdapter

    native = GhdlAdapter().execute({
        "operation": "run_hdl_test",
        "sources": [str(HDL / "s16_counter.vhdl"),
                    str(HDL / "s16_broken.vhdl")],
        "top": "broken",
        "workdir": str(tmp_path),
    })
    assert native["exit_code"] != 0
    assert native["stderr"].strip() != ""


@needs_ghdl
def test_ghdl_synth_emits_verilog_stdout(tmp_path):
    """Dump pin: ghdl --synth emits backend Verilog on stdout.

    The working form is `ghdl --synth --out=verilog <files> -e
    <top>`; stdout carries `module <top>`. Recorded against GHDL
    7.0.0-dev (oss-cad-suite).
    """
    proc = subprocess.run(
        ["ghdl", "--synth", "--out=verilog", str(HDL / "s16_counter.vhdl"),
         "-e", "counter"],
        capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr[:500]
    assert "module counter" in proc.stdout


def test_ghdl_synth_parse_clean():
    """A clean synth native parses to total 0 with netlist and top."""
    from rocket_engine.adapters.synth_yosys.ghdl import GhdlSynthAdapter

    native = {"exit_code": 0, "stdout": "module counter",
              "stderr": "", "netlist": "ghdl_synth.v", "top": "counter"}
    result = GhdlSynthAdapter().parse(native)
    assert result["total"] == 0
    assert result["top"] == "counter"


def test_ghdl_synth_parse_failure():
    """A failed synth native parses to one synth_error violation."""
    from rocket_engine.adapters.synth_yosys.ghdl import GhdlSynthAdapter

    native = {"exit_code": 1, "stdout": "",
              "stderr": "s16_broken.vhdl:4:28:error: missing \";\"",
              "netlist": "ghdl_synth.v", "top": "broken"}
    result = GhdlSynthAdapter().parse(native)
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "synth_error"


def test_amaranth_emit_matches_golden():
    """The backend Verilog emission matches the recorded golden bytes."""
    from rocket_engine.adapters.synth_yosys.amaranth import AmaranthAdapter

    golden = (SYNTH / "s16_amaranth_top.v").read_text(encoding="utf-8")
    assert AmaranthAdapter.emit_verilog({"top": "s16demo"}, ".") == golden


@needs_amaranth
def test_amaranth_bad_design_refuses():
    """An empty design refuses invalid_command before emitting."""
    from rocket_engine.adapters.synth_yosys.amaranth import AmaranthAdapter

    try:
        AmaranthAdapter().preflight({"operation": "run_synth", "design": ""})
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_command"
    else:
        raise AssertionError("expected invalid_command for an empty design")


def test_xschem_deck_capabilities():
    """The deck sits behind the ToolAdapter port as an xschem deck."""
    from rocket_engine.adapters import ToolAdapter
    from rocket_engine.adapters.xschem.deck import XschemDeck

    assert issubclass(XschemDeck, ToolAdapter)
    caps = XschemDeck().capabilities({"cell": "good"})
    assert "run_xschem" in caps["operations"]
    assert caps["tool"] == "xschem"
    assert "deck" in caps["modes"]


def test_xschem_deck_missing_schematic_refuses(tmp_path):
    """A missing schematic refuses invalid_reference (no binary needed)."""
    from rocket_engine.adapters.xschem.deck import XschemDeck

    try:
        XschemDeck().deck({
            "operation": "run_xschem",
            "sch_file": str(tmp_path / "ghost.sch"),
            "workdir": str(tmp_path),
        })
    except Exception as exc:
        assert getattr(exc, "code", None) == "invalid_reference"
    else:
        raise AssertionError("expected invalid_reference for a ghost schematic")


@needs_xschem
def test_xschem_deck_netlists_good_schematic(tmp_path):
    """A good schematic decks to one device line with zero violations."""
    from rocket_engine.adapters.xschem.deck import XschemDeck

    verdict = XschemDeck().deck({
        "operation": "run_xschem",
        "sch_file": str(XS / "good.sch"),
        "rcfile": str(XS / "xschemrc"),
        "workdir": str(tmp_path),
    })
    assert verdict["violations"] == []
    assert len(verdict["elements"]) == 1
    assert verdict["elements"][0].startswith("V1 ")
    assert "/tmp" not in verdict["normalized_text"]
    assert Path(verdict["netlist_file"]).is_file()


@needs_xschem
def test_xschem_deck_empty_schematic_fails_loud(tmp_path):
    """An empty schematic decks to an empty_netlist error, never clean."""
    from rocket_engine.adapters.xschem.deck import XschemDeck

    verdict = XschemDeck().deck({
        "operation": "run_xschem",
        "sch_file": str(XS / "empty.sch"),
        "workdir": str(tmp_path),
    })
    assert verdict["total"] >= 1
    assert verdict["violations"][0]["rule"] == "empty_netlist"
    assert verdict["violations"][0]["severity"] == "error"


def test_xschem_deck_sim_phase_combines():
    """A failing sim phase appends xschem_sim_fail under a clean netlist."""
    from rocket_engine.adapters.xschem.deck import XschemDeck

    binary = shutil.which("xschem")
    if binary is None:
        pytest.skip("xschem not installed")

    class _FakeRunner:
        """Canned xschem: V3 banner, one-device netlist, sim error log."""

        def preflight(self):
            """No runner admission gates for the canned double."""
            return None

        def run(self, argv, workdir, timeout):
            """Answer -v plus netlist runs; the sim run logs a failure."""
            from subprocess import CompletedProcess

            if argv[:2] == [binary, "-v"]:
                return CompletedProcess(
                    argv, 0, stdout="XSCHEM V3.4.8", stderr="")
            outdir = Path(workdir) / "xschem_out"
            outdir.mkdir(exist_ok=True)
            name = argv[argv.index("-N") + 1]
            netlist = ("** sch_path: good.sch\n**.subckt good\n"
                       "V1 net1 net2 1.65\n**.ends\n.end\n")
            (outdir / name).write_text(netlist)
            stderr = ""
            if "-S" in argv:
                stderr = "ngspice error: no simulation data\n"
            return CompletedProcess(argv, 0, stdout="", stderr=stderr)

    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        verdict = XschemDeck(
            runner=_FakeRunner(), xschem_bin=binary).deck({
                "operation": "run_xschem",
                "sch_file": str(XS / "good.sch"),
                "workdir": scratch,
                "sim": True,
            })
    assert verdict["violations"] == []
    assert verdict["sim"] is not None
    assert verdict["sim"]["total"] >= 1
    assert verdict["sim"]["violations"][0]["rule"] == "xschem_sim_fail"
