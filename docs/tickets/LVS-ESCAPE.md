# LVS-ESCAPE: Bulk-rename mutant escapes LVS 3/3 seeds

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-07, MED)*

## Why

The netlist_lvs_mismatch operator escapes on all 3
seeds: mutated netlists still PASS LVS (harness
honestly reports exit 1, so the gate holds — but the
mutant proves a detection hole). Root cause undiagnosed
(netgen setup vs operator, operators.py:437-461 vs
lvs adapter:300-310); possible shared root with
LVS-BANDGAP-TRIAGE, kept separate until proven.

## What

- Diagnose with evidence, fix the losing side
  (setup or operator), pin the escape as a regression
  (escape → FAIL).
- All 3 seeds must fail post-fix.

## Acceptance

- 3/3 escape seeds FAIL LVS; root cause in report.
- Contract + api_spec regen; full suite + gate green.
