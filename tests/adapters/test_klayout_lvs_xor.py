"""KLayout LVS/XOR RED — klayout LVS path plus layout_xor mode.

Valid RED = `KlayoutLvsAdapter` / xor support do not exist yet in
`rocket_engine.adapters.drc.klayout`. check.lvs needs a klayout
path (netgen stays the reference); check.layout_xor is assigned to
drc_kl but no XOR mode exists. Both parse from report/database
output, never exit code.
"""

import pytest


def test_klayout_lvs_adapter_exists():
    from rocket_engine.adapters.drc.klayout import KlayoutLvsAdapter

    caps = KlayoutLvsAdapter().capabilities({})
    assert "run_lvs" in caps["operations"]
    assert caps["tool"] == "klayout"


def test_klayout_lvs_parse_clean():
    from rocket_engine.adapters.drc.klayout import KlayoutLvsAdapter

    native = {"exit_code": 0, "report_xml": "<report></report>",
              "matches": True, "mismatches": []}
    result = KlayoutLvsAdapter().parse(native)
    assert result["total"] == 0


def test_klayout_lvs_parse_mismatch_reports_violation():
    from rocket_engine.adapters.drc.klayout import KlayoutLvsAdapter

    native = {"exit_code": 0, "report_xml": "<report></report>",
              "matches": False,
              "mismatches": [{"devices": "M1"}]}
    result = KlayoutLvsAdapter().parse(native)
    assert result["total"] >= 1


def test_klayout_xor_mode_parses():
    from rocket_engine.adapters.drc.klayout import run_xor_summary

    native = {"exit_code": 0, "stdout": "XOR differences: 0\n"}
    result = run_xor_summary(native)
    assert result["total"] == 0


def test_klayout_xor_differences_report_violation():
    from rocket_engine.adapters.drc.klayout import run_xor_summary

    native = {"exit_code": 0, "stdout": "XOR differences: 3\n"}
    result = run_xor_summary(native)
    assert result["total"] == 3
