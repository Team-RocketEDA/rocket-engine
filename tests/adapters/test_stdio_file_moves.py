"""Stdio-to-file moves RED — adapters read files, not stdio scrapes.

Valid RED = none of the file channels exist yet, so every test
fails: parse results carry no source marker, vvp runs without
`-l`, slang runs without `--diag-json`, and formal ignores
`formal/logfile.txt`. Per MIGRATE-STDIO-FILE: ngspice/postlayout
tier 1 (log only), formal logfile, hdl_sim/cosim `vvp -l`,
synth_yosys log-only, syntax `--diag-json`. Existing golden
fixtures still pass via a loud stdio fallback, never silently.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

OSS = Path("/home/alrida-ismail/tools/oss-cad-suite/bin")
needs_slang = pytest.mark.skipif(
    shutil.which("slang") is None and not (OSS / "slang").is_file(),
    reason="slang not installed",
)


def _measurements():
    return [
        {"name": "vref", "expr": "v(vref)", "unit": "V",
         "min": 1.15, "max": 1.25},
    ]


def test_ngspice_parse_prefers_log_and_marks_source():
    """Conflicting stdio meas lines no longer satisfy the parse."""
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": "meas_vref = 9.900000e+00\n",
        "stderr": "",
        "log": "meas_vref = 1.200000e+00\n",
        "deck": "ngspice_deck.spice",
        "sources": ["tb.spice"],
        "measurements": _measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["source"] == "log"
    assert result["measurements"][0]["value"] == pytest.approx(1.2)


def test_ngspice_parse_stdio_fallback_is_loud():
    """Empty logs fall back to stdio with a loud marker, never silent."""
    from rocket_engine.adapters.ngspice import NgspiceAdapter

    native = {
        "exit_code": 0,
        "stdout": "meas_vref = 1.200000e+00\n",
        "stderr": "",
        "log": "",
        "deck": "ngspice_deck.spice",
        "sources": ["tb.spice"],
        "measurements": _measurements(),
    }
    result = NgspiceAdapter().parse(native)
    assert result["source"] == "stdio_fallback"
    assert result["measurements"][0]["value"] == pytest.approx(1.2)


def test_postlayout_parse_prefers_log_and_marks_source(tmp_path):
    """Postlayout meas lines come from the -o log, not stdio."""
    from rocket_engine.adapters.postlayout.adapter import PostLayoutAdapter

    netlist = tmp_path / "extracted.spice"
    netlist.write_text("* extracted\n")
    from rocket_engine.adapters.postlayout.adapter import build_provenance

    record = build_provenance(str(netlist), "run-extract-1")
    native = {
        "exit_code": 0,
        "stdout": "meas_vref = 9.900000e+00\n",
        "stderr": "",
        "log": "meas_vref = 1.190000e+00\n",
        "measurements": _measurements(),
        "waveforms_spec": [],
        "waveforms_file": "",
        "extracted_netlist": str(netlist),
        "extraction_provenance": record,
        "schematic": {
            "run_id": "run-schem-1",
            "values": {"vref": {"value": 1.2, "unit": "V"}},
        },
    }
    result = PostLayoutAdapter().parse(native)
    assert result["source"] == "log"
    assert result["measurements"][0]["value"] == pytest.approx(1.19)


def test_formal_parse_reads_logfile_when_stdout_is_empty(tmp_path):
    """formal/logfile.txt feeds the summary regexes when stdio is bare."""
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter

    workdir = tmp_path / "work"
    formal_dir = workdir / "formal"
    formal_dir.mkdir(parents=True)
    (formal_dir / "logfile.txt").write_text(
        "SBY 0.70\nsummary: engine_0 (smtbmc boolector) returned FAIL for p_x\n"
        "summary: failed assertion p_x at prop_top.sv:10. step 3\n"
        "summary: counterexample trace: formal/cex.vcd\n"
        "DONE (FAIL, rc=2)\n"
    )
    sources = [str(tmp_path / "prop_top.sv")]
    Path(sources[0]).write_text(
        "module prop_top(input logic clk);\n"
        "assert property (@(posedge clk) 1'b1);\nendmodule\n"
    )
    native = {
        "exit_code": 2,
        "stdout": "",
        "stderr": "",
        "log": "",
        "timed_out": False,
        "workdir": str(workdir),
        "sources": sources,
        "top": "prop_top",
        "mode": "bmc",
        "depth": 20,
        "engines": ["smtbmc boolector"],
        "sby_version": "SBY 0.70",
        "timeout_s": 300,
    }
    result = FormalSbyAdapter().parse(native)
    assert result["source"] == "logfile"
    assert result["measurements"]["sby_status"] == "FAIL"
    assert any(
        v.get("file") == str(sources[0]) for v in result["violations"]
    )


def test_hdl_execute_passes_logfile_to_vvp(tmp_path):
    """vvp runs with -l so sim text lands in a file first."""
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    seen = {}

    class FakeRunner:
        def preflight(self):
            return {"ready": True}

        def run(self, command, workdir, timeout_s, extra_binds=()):
            seen["command"] = command
            if command[0].endswith("vvp"):
                (Path(workdir) / "sim.log").write_text(
                    "FATAL: bench.v:42: oops\nTime: 120\n"
                )
            return subprocess.CompletedProcess(command, 0, "", "")

    bench = tmp_path / "bench.v"
    bench.write_text(
        "module bench; initial begin $display(\"hi\"); $finish; end endmodule\n"
    )
    native = HdlSimAdapter(runner=FakeRunner()).execute(
        {
            "operation": "run_hdl_test",
            "sources": [str(bench)],
            "workdir": str(tmp_path),
            "tool_dir": str(OSS),
        }
    )
    assert "-l" in seen["command"]
    assert native["run"]["log"] != ""


def test_hdl_parse_prefers_run_log_over_stdio():
    """Sim assertion lines come from the vvp log, not stdio."""
    from rocket_engine.adapters.hdl_sim import HdlSimAdapter

    native = {
        "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
        "run": {
            "exit_code": 0,
            "stdout": "FATAL: bench.v:1: stdio decoy\nTime: 10\n",
            "stderr": "",
            "log": "FATAL: bench.v:42: log truth\nTime: 120\n",
        },
    }
    result = HdlSimAdapter().parse(native)
    assert result["source"] == "log"
    assert result["violations"][0]["file"] == "bench.v"
    assert result["violations"][0]["line"] == 42
    assert result["violations"][0]["sim_time"] == 120


def test_cosim_parse_prefers_run_log_for_reports():
    """COSIM_* bench reports come from the vvp log, not stdio."""
    from rocket_engine.adapters.cosim import CosimAdapter, _sinc3_model

    bits = [1] * 256 + [0] * 256
    reports = (
        "SDM_RX_ID 53444D31\n"
        f"COSIM_BITS {len(bits)} {sum(bits)}\n"
        "COSIM_COUNT_FAST 20\n"
        "COSIM_COUNT_PREC 2\n"
        f"COSIM_DATA_FAST {_sinc3_model(bits, 25)[-1]}\n"
        f"COSIM_DATA_PREC {_sinc3_model(bits, 250)[-1]}\n"
        "COSIM_PASS\n"
    )
    native = {
        "exit_code": 0,
        "analog": {"exit_code": 0, "stdout": "", "stderr": "",
                   "log": "", "deck": "* deck", "sources": ["half.spice"],
                   "csv_rows": 1000, "error": None},
        "digital": {
            "exit_code": 0,
            "compile": {"exit_code": 0, "stdout": "", "stderr": ""},
            "run": {"exit_code": 0, "stdout": "", "stderr": "",
                    "log": reports},
        },
        "bits": bits,
        "ones_density": 0.5,
        "sndr_db": 42.5,
        "nbits": len(bits),
        "sig_bin": 5,
        "osr_fast": 25,
        "osr_prec": 250,
        "gates": {"gate_db": 36.0, "ones_min": 0.2, "ones_max": 0.8},
    }
    result = CosimAdapter().parse(native)
    assert result["source"] == "log"
    assert result["total"] == 0


def test_synth_parse_ignores_stdio_error_lines(tmp_path):
    """Synth verdicts come from synth.log, not stdio copies."""
    from rocket_engine.adapters.synth_yosys import YosysSynthAdapter

    netlist = tmp_path / "net.v"
    netlist.write_text("module top(); endmodule\n")
    stat = "\n=== top ===\n\n  2 wires\n  3 cells\n  2   $_DLATCH_P_\n  1   $_NOT_\n"
    result = YosysSynthAdapter().parse(
        {
            "exit_code": 0,
            "log": "",
            "stdout": "ERROR: stdio ghost: Module `ghost` not found\n",
            "stderr": "",
            "stat": stat,
            "netlist": str(netlist),
        }
    )
    assert result["source"] == "stdio_fallback"
    assert result["total"] >= 1
    logged = YosysSynthAdapter().parse(
        {
            "exit_code": 0,
            "log": "Warnings: 0 unique messages, 0 total\n",
            "stdout": "ERROR: stdio ghost: Module `ghost` not found\n",
            "stderr": "",
            "stat": stat,
            "netlist": str(netlist),
        }
    )
    assert logged["source"] == "log"
    assert logged["total"] == 0


@needs_slang
def test_syntax_execute_writes_diag_json_and_parse_prefers_it(tmp_path):
    """slang runs with --diag-json; counts derive from pinned JSON."""
    from rocket_engine.adapters.syntax import SyntaxAdapter

    seen = {}

    class FakeRunner:
        def run(self, argv, workdir, timeout_s):
            seen["argv"] = argv
            return subprocess.CompletedProcess(argv, 1, "", "")

    bad = tmp_path / "bad.sv"
    bad.write_text(
        "module top(input logic a, output logic y);\n"
        "  assign y = missing_mod(a);\nendmodule\n"
    )
    adapter = SyntaxAdapter(runner=FakeRunner())
    tool = str(OSS) if (OSS / "slang").is_file() else None
    job = {"operation": "run_syntax", "sources": [str(bad)],
           "workdir": str(tmp_path)}
    if tool is not None:
        job["tool_dir"] = str(OSS)
    try:
        adapter.execute(job)
    except Exception:
        pass
    assert "--diag-json" in seen["argv"]

    diag = [
        {
            "severity": "error",
            "message": "use of undeclared identifier 'missing_mod'",
            "code": "UndeclaredIdentifier",
            "location": "bad.sv:2:14",
            "ranges": [
                {"start": {"file": "bad.sv", "line": 2, "column": 14},
                 "end": {"file": "bad.sv", "line": 2, "column": 25}}
            ],
            "symbolPath": "$unit",
        },
    ]
    (tmp_path / "diag.json").write_text(json.dumps(diag))
    result = SyntaxAdapter().parse(
        {
            "exit_code": 1,
            "stdout": "",
            "stderr": "",
            "sources": [str(bad)],
            "diag_json": diag,
        }
    )
    assert result["source"] == "diag_json"
    assert result["total"] == 1
    assert result["violations"][0]["severity"] == "error"
    assert result["violations"][0]["line"] == 2
    assert result["violations"][0]["col"] == 14
