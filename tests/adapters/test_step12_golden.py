"""Step-12 golden pins: file channels byte-identical to stdio.

These tests pin the MIGRATE-STDIO-FILE verdict: every file parse
agrees with the stdio parse on the same bytes, and the file wins
on conflict. They pass on the landed behavior and guard the
escape work against regressions. A companion shape-conformance
pass asserts every violation carries rule/severity/message and
every measurement list carries name/value/unit.
"""

from rocket_engine.adapters.cosim import CosimAdapter
from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter
from rocket_engine.adapters.hdl_sim import HdlSimAdapter
from rocket_engine.adapters.synth_yosys import YosysSynthAdapter
from rocket_engine.adapters.syntax import SyntaxAdapter

ERROR_LOG = "ERROR: top.v:10: syntax error\n"
OTHER_LOG = "ERROR: other.v:99: something else\n"

HDL_LOG = "FATAL: bench.v:44: mismatch on dout\nTime: 120\n"
HDL_OTHER = "FATAL: other.v:1: unrelated\nTime: 5\n"

DIAG_JSON = [
    {
        "severity": "error",
        "message": "use of undeclared identifier 'foo'",
        "code": "UndeclaredIdentifier",
        "location": "top.sv:7:11",
        "ranges": [{"start": {"file": "top.sv", "line": 7, "column": 11}}],
        "symbolPath": "top",
    }
]
STDIO_OTHER = "other.sv:1:1: error: something else\nBuild failed: 1 errors, 0 warnings\n"


def _synth_native(*, log, stdout="", stderr="", stat=""):
    return {
        "exit_code": 1,
        "stdout": stdout,
        "stderr": stderr,
        "log": log,
        "stat": stat,
        "netlist": "synth_netlist.v",
        "top": "top",
        "mapped": False,
        "yosys_version": "Yosys 0.70+219",
    }


def test_synth_log_matches_stdio_on_same_bytes():
    """Same bytes via log or stdio parse to the same violations."""
    via_log = YosysSynthAdapter().parse(_synth_native(log=ERROR_LOG))
    via_stdio = YosysSynthAdapter().parse(
        _synth_native(log="", stdout=ERROR_LOG)
    )
    assert via_log["violations"] == via_stdio["violations"]
    assert via_log["source"] == "log"
    assert via_stdio["source"] == "stdio_fallback"


def test_synth_log_wins_on_conflict():
    """Conflicting stdio error lines never move the log verdict."""
    result = YosysSynthAdapter().parse(
        _synth_native(log=ERROR_LOG, stdout=OTHER_LOG)
    )
    assert result["source"] == "log"
    assert [v["message"] for v in result["violations"]] == [
        "top.v:10: syntax error"
    ]


def _compile_block():
    return {"exit_code": 0, "stdout": "", "stderr": ""}


def test_hdl_run_log_matches_stdio_on_same_bytes():
    """Same sim bytes via run log or stdio parse identically."""
    via_log = HdlSimAdapter().parse(
        {"compile": _compile_block(),
         "run": {"exit_code": 0, "stdout": "", "stderr": "", "log": HDL_LOG}}
    )
    via_stdio = HdlSimAdapter().parse(
        {"compile": _compile_block(),
         "run": {"exit_code": 0, "stdout": HDL_LOG, "stderr": ""}}
    )
    assert via_log["violations"] == via_stdio["violations"]
    assert via_log["source"] == "log"
    assert via_stdio["source"] == "stdio_fallback"


def test_hdl_run_log_wins_on_conflict():
    """Conflicting stdio FATAL lines never move the log verdict."""
    result = HdlSimAdapter().parse(
        {"compile": _compile_block(),
         "run": {"exit_code": 0, "stdout": HDL_OTHER, "stderr": "",
                 "log": HDL_LOG}}
    )
    assert result["source"] == "log"
    assert [v["file"] for v in result["violations"]] == ["bench.v"]


def test_syntax_diag_json_matches_stdio_counts():
    """JSON diagnostics derive the same error count as stdio."""
    native_json = {
        "exit_code": 1,
        "stdout": "",
        "stderr": "",
        "sources": ["top.sv"],
        "diag_json": DIAG_JSON,
    }
    native_stdio = {
        "exit_code": 1,
        "stdout": "top.sv:7:11: error: use of undeclared identifier 'foo'\n"
                  "Build failed: 1 errors, 0 warnings\n",
        "stderr": "",
        "sources": ["top.sv"],
        "diag_json": None,
    }
    from_json = SyntaxAdapter().parse(native_json)
    from_stdio = SyntaxAdapter().parse(native_stdio)
    assert from_json["source"] == "diag_json"
    assert from_stdio["source"] == "stdio_fallback"
    assert len(from_json["violations"]) == len(from_stdio["violations"]) == 1
    assert from_json["violations"][0]["line"] == 7
    assert from_json["violations"][0]["severity"] == "error"


def test_syntax_diag_json_wins_on_conflict():
    """Conflicting stdio diagnostics never move the JSON verdict."""
    result = SyntaxAdapter().parse(
        {"exit_code": 1, "stdout": STDIO_OTHER, "stderr": "",
         "sources": ["top.sv"], "diag_json": DIAG_JSON}
    )
    assert result["source"] == "diag_json"
    assert [v["file"] for v in result["violations"]] == ["top.sv"]


def _cosim_native(*, report_text, stdio_text):
    run = {"exit_code": 0, "stdout": stdio_text, "stderr": "",
           "log": report_text}
    digital = {
        "exit_code": 0,
        "compile": _compile_block(),
        "run": run,
    }
    return {
        "exit_code": 0,
        "analog": {"sources": ["tb.spice"]},
        "digital": digital,
        "bits": [1, 0, 1, 0],
        "ones_density": 0.5,
        "sndr_db": 30.0,
        "nbits": 4,
        "osr_fast": 2,
        "osr_prec": 2,
        "gates": {"gate_db": 20.0, "ones_min": 0.4, "ones_max": 0.6},
    }


COSIM_REPORT = (
    "COSIM_BITS 4 2\n"
    "COSIM_COUNT_FAST 2\n"
    "COSIM_COUNT_PREC 2\n"
    "COSIM_DATA_FAST 0\n"
    "COSIM_DATA_PREC 0\n"
)


def test_cosim_report_log_matches_stdio_on_same_bytes():
    """Same COSIM-adjacent bytes via log or stdio agree on source."""
    via_log = CosimAdapter().parse(
        _cosim_native(report_text=COSIM_REPORT, stdio_text=""))
    via_stdio = CosimAdapter().parse(
        _cosim_native(report_text="", stdio_text=COSIM_REPORT))
    assert via_log["source"] == "log"
    assert via_stdio["source"] == "stdio_fallback"
    assert via_log["violations"] == via_stdio["violations"]


def _shape_natives():
    stat = ("4. Printing statistics.\n\n=== top ===\n\n  3 wires\n"
            "  1 cells\n  1   $_AND_\n\n===\n")
    synth = dict(_synth_native(log=ERROR_LOG, stat=stat))
    syntax = {"exit_code": 1, "stdout": "", "stderr": "",
              "sources": ["top.sv"], "diag_json": DIAG_JSON}
    hdl = {"compile": _compile_block(),
           "run": {"exit_code": 0, "stdout": "", "stderr": "",
                   "log": HDL_LOG}}
    cosim = _cosim_native(report_text=COSIM_REPORT, stdio_text="")
    drc = {"exit_code": 0,
           "stdout": "VIOL rule=M1_width bbox_um=0,0,1,1\nTOTAL 1\n",
           "stderr": ""}
    return {
        "synth": YosysSynthAdapter().parse(synth),
        "syntax": SyntaxAdapter().parse(syntax),
        "hdl_sim": HdlSimAdapter().parse(hdl),
        "cosim": CosimAdapter().parse(cosim),
        "drc_kl": KlayoutDrcAdapter().parse(drc),
    }


def test_violation_shapes_conform():
    """Every violation carries rule, severity, and message."""
    for name, parsed in _shape_natives().items():
        assert parsed["violations"], name
        for violation in parsed["violations"]:
            assert isinstance(violation.get("rule"), str), name
            assert violation["rule"], name
            assert violation.get("severity") in ("error", "warning"), name
            assert isinstance(violation.get("message"), str), name
            assert violation["message"], name


def test_measurement_shapes_conform():
    """Every measurement list carries name, value, and unit."""
    for name, parsed in _shape_natives().items():
        measurements = parsed.get("measurements", [])
        assert isinstance(measurements, list), name
        for measurement in measurements:
            assert isinstance(measurement.get("name"), str), name
            assert "value" in measurement, name
            assert isinstance(measurement.get("unit"), str), name
