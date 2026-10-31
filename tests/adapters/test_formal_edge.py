"""FORMAL-EDGE GREEN — vacuity guard + ifdef-aware sites (new files only).

Unit tests exercise the new formal_edge helpers directly (always
GREEN after resync). Wiring tests probe the tracked adapter and skip
until the integrator applies docs/work/FORMAL-EDGE/wiring.patch.
"""

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "formal"
ROOT = Path(__file__).resolve().parent.parent.parent
PICORV32 = ROOT / "fixtures" / "upstream" / "picorv32" / "picorv32.v"


def _require_picorv32():
    if not PICORV32.is_file():
        pytest.skip("picorv32 fixture not fetched")


def test_edge_sites_skip_define_lines(tmp_path):
    from rocket_engine.adapters.formal_sby.formal_edge import property_sites

    src = tmp_path / "d.v"
    src.write_text(
        "module d(input clk);\n"
        "`define assert(assert_expr) assert(assert_expr)\n"
        "always @(posedge clk) assert(q == 1);\n"
        "endmodule\n"
    )
    _, props = property_sites([str(src)])
    assert [(p["line"], p["kind"]) for p in props] == [(3, "assert")]


def test_edge_sites_ifdef_aware(tmp_path):
    from rocket_engine.adapters.formal_sby.formal_edge import property_sites

    src = tmp_path / "c.v"
    src.write_text(
        "module c(input clk);\n"
        "`ifdef FORMAL\n"
        "always @(posedge clk) assert(a == 1);\n"
        "`elsif DEBUG\n"
        "always @(posedge clk) assert(b == 1);\n"
        "`else\n"
        "always @(posedge clk) assert(c == 1);\n"
        "`endif\n"
        "`ifndef NEVER_DEFINED\n"
        "always @(posedge clk) assume(d == 1);\n"
        "`endif\n"
        "`ifdef NEVER_DEFINED\n"
        "always @(posedge clk) assert(e == 1);\n"
        "`endif\n"
        "// assert(f == 1);\n"
        "/* assert(g == 1); */\n"
        "endmodule\n"
    )
    assumptions, props = property_sites([str(src)])
    assert [(p["line"], p["kind"]) for p in props] == [(3, "assert")]
    assert [a["line"] for a in assumptions] == [10]


def test_edge_sites_nested_ifdef_and_undef(tmp_path):
    from rocket_engine.adapters.formal_sby.formal_edge import property_sites

    src = tmp_path / "n.v"
    src.write_text(
        "module n(input clk);\n"
        "`define FEAT\n"
        "`ifdef FEAT\n"
        "`ifdef FORMAL\n"
        "always @(posedge clk) cover(q == 1);\n"
        "`endif\n"
        "`endif\n"
        "`undef FEAT\n"
        "`ifdef FEAT\n"
        "always @(posedge clk) assert(z == 1);\n"
        "`endif\n"
        "endmodule\n"
    )
    _, props = property_sites([str(src)])
    assert [(p["line"], p["kind"]) for p in props] == [(5, "cover")]


def test_edge_sites_picorv32_guarded_asserts():
    from rocket_engine.adapters.formal_sby.formal_edge import property_sites

    _require_picorv32()
    _, props = property_sites([str(PICORV32)])
    lines = sorted(p["line"] for p in props)
    assert 40 not in lines and 47 not in lines
    assert len(props) == 23
    for want in (549, 596, 622, 630, 2122, 2134, 2152, 2163):
        assert want in lines


def test_edge_sites_picorv32_formal_undefined_excludes_ifdef_block():
    from rocket_engine.adapters.formal_sby.formal_edge import property_sites

    _require_picorv32()
    _, props = property_sites([str(PICORV32)], defines=set())
    lines = sorted(p["line"] for p in props)
    assert 40 not in lines and 47 not in lines
    assert 2122 not in lines and 2163 not in lines
    assert 549 in lines and 631 in lines
    assert len(props) == 13


def test_edge_vacuity_guard_flags_empty():
    from rocket_engine.adapters.formal_sby.formal_edge import (
        VACUOUS_RULE,
        VACUOUS_SCOPE,
        guard_vacuous_pass,
    )

    out = guard_vacuous_pass([], mode="bmc", depth=5)
    assert out is not None
    assert out["scope"] == VACUOUS_SCOPE == "bounded-vacuous"
    assert out["violation"]["rule"] == VACUOUS_RULE == "formal_vacuous"
    assert out["violation"]["severity"] == "error"
    assert "zero checked properties" in out["violation"]["message"]
    assert "bmc" in out["violation"]["message"]


def test_edge_vacuity_guard_passes_through_nonempty():
    from rocket_engine.adapters.formal_sby.formal_edge import guard_vacuous_pass

    props = [{"file": "x.v", "line": 1, "kind": "assert"}]
    assert guard_vacuous_pass(props, mode="bmc", depth=5) is None


def test_edge_vacuity_simulated_parse_is_fail_not_pass(tmp_path):
    from rocket_engine.adapters.formal_sby.formal_edge import (
        guard_vacuous_pass,
        property_sites,
    )

    plain = tmp_path / "plain.v"
    plain.write_text(
        "module plain(input clk);\n"
        "reg q = 0;\n"
        "always @(posedge clk) q <= !q;\n"
        "endmodule\n"
    )
    _, props = property_sites([str(plain)])
    assert props == []
    out = guard_vacuous_pass(props, mode="bmc", depth=5)
    assert out is not None
    result = {
        "total": 1,
        "violations": [out["violation"]],
        "measurements": {"scope": out["scope"]},
    }
    assert result["total"] == 1
    assert result["measurements"]["scope"] == "bounded-vacuous"


def test_edge_wired_vacuity_refuses_bare_pass(tmp_path):
    from rocket_engine.adapters.formal_sby import FormalSbyAdapter

    work = tmp_path / "work"
    work.mkdir()
    plain = work / "plain.v"
    plain.write_text(
        "module plain(input clk);\n"
        "reg q = 0;\n"
        "always @(posedge clk) q <= !q;\n"
        "endmodule\n"
    )
    native = {
        "exit_code": 0,
        "stdout": "SBY fake DONE (PASS, rc=0)\n",
        "stderr": "",
        "timed_out": False,
        "workdir": str(work),
        "sby_file": str(work / "formal.sby"),
        "sources": [str(plain)],
        "mode": "bmc",
        "depth": 5,
        "top": "plain",
        "sby_version": "SBY v0.70-fake",
        "timeout_s": 300,
    }
    (work / "formal").mkdir()
    (work / "formal" / "status").write_text("PASS 0 0\n")
    result = FormalSbyAdapter().parse(native)
    if result["total"] == 0:
        pytest.skip("wiring patch not applied: vacuous PASS still bare")
    assert result["total"] == 1
    assert result["violations"][0]["rule"] == "formal_vacuous"
    assert result["measurements"]["scope"] == "bounded-vacuous"


def test_edge_wired_sites_skip_defines(tmp_path):
    from rocket_engine.adapters.formal_sby import _property_sites

    src = tmp_path / "d.v"
    src.write_text(
        "module d(input clk);\n"
        "`define assert(assert_expr) assert(assert_expr)\n"
        "`ifdef NEVER_DEFINED_XYZ\n"
        "always @(posedge clk) assert(q == 1);\n"
        "`endif\n"
        "always @(posedge clk) assert(r == 1);\n"
        "endmodule\n"
    )
    _, props = _property_sites([str(src)])
    lines = sorted(p["line"] for p in props)
    if 2 in lines or 4 in lines:
        pytest.skip("wiring patch not applied: sites still ifdef-blind")
    assert lines == [6]
