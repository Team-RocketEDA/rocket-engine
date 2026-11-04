"""Step-12 RED: drc_kl violations conform to rule/severity/message.

Valid RED = klayout parse violations carry rule plus geometry but
no severity, and synthetic-mode violations carry no message, so
every shape assertion here fails. Per ESCAPE-HARDEN item 5 every
violation needs rule, severity, and message; measurements stay
lists. Deck mode already carries messages; it gains severity.
Synthetic mode gains a rule-plus-geometry message identical to the
results_kl fallback rendering, keeping the normalized bundle
byte-identical.
"""

from rocket_engine.adapters.drc.klayout import KlayoutDrcAdapter

LYRDB = """<?xml version="1.0" encoding="utf-8"?>
<report-database>
<categories><category><name>width</name><description>min width 0.5um</description></category></categories>
<items><item><category>width</category><multiplicity>1</multiplicity>
<values><value>shape 0.1,0.2; 0.3,0.4</value></values>
</item></items>
</report-database>
"""

SYNTHETIC_STDOUT = (
    "VIOL rule=M1_width bbox_um=0.0,0.0,0.05,2.0\n"
    "VIOL rule=M1_space bbox_um=1.0,1.0,1.05,3.0\n"
    "TOTAL 2\n"
)


def test_deck_violations_carry_severity():
    """Deck-mode violations are errors with their deck message."""
    result = KlayoutDrcAdapter().parse(
        {"exit_code": 0, "stdout": "", "stderr": "",
         "report_xml": LYRDB}
    )
    assert result["total"] == 1
    violation = result["violations"][0]
    assert violation["rule"] == "width"
    assert violation["severity"] == "error"
    assert "min width 0.5um" in violation["message"]
    assert violation["bbox_um"] == [0.1, 0.2, 0.3, 0.4]


def test_synthetic_violations_carry_severity_and_message():
    """Synthetic violations are errors naming rule plus geometry."""
    result = KlayoutDrcAdapter().parse(
        {"exit_code": 0, "stdout": SYNTHETIC_STDOUT, "stderr": ""}
    )
    assert result["total"] == 2
    first = result["violations"][0]
    assert first["rule"] == "M1_width"
    assert first["severity"] == "error"
    assert "M1_width" in first["message"]
    assert "0.0,0.0,0.05,2.0" in first["message"]
    assert first["bbox_um"] == [0.0, 0.0, 0.05, 2.0]


def test_every_violation_has_rule_severity_message():
    """Both modes: every violation carries the conformant triple."""
    deck = KlayoutDrcAdapter().parse(
        {"exit_code": 0, "stdout": "", "stderr": "",
         "report_xml": LYRDB}
    )
    synth = KlayoutDrcAdapter().parse(
        {"exit_code": 0, "stdout": SYNTHETIC_STDOUT, "stderr": ""}
    )
    for violation in deck["violations"] + synth["violations"]:
        assert isinstance(violation["rule"], str) and violation["rule"]
        assert violation["severity"] in ("error", "warning")
        assert isinstance(violation["message"], str) and violation["message"]
