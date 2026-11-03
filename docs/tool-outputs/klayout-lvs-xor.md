# klayout LVS path plus layout_xor — addendum to klayout-0.28.16

Context: HDL-PROVIDERS item 4. check.lvs gains a klayout path
(netgen stays the reference); check.layout_xor (assigned to
drc_kl) gains its XOR mode. Code
`src/adapters/drc/klayout.py` (`KlayoutLvsAdapter`,
`run_xor_summary`); the existing DRC synthetic/deck paths are
untouched.

## Report inventory

LVS: layout versus schematic device lists compared in-process;
native output `{exit_code, report_xml, matches, mismatches[]}`.
XOR: `XOR differences: N` summary text parsed to N
`layout_xor` violations.

## Grammar

LVS clean is `matches is True` with no mismatches; anything
else yields `lvs_mismatch` errors. XOR count comes from
`XOR differences:\s*(\d+)` (case-insensitive).

## Exit states

- klayout absent: `missing_dependency` with BLOCKED-needs-host.
- Verdicts from parsed reports, never the exit code (klayout
  exits 0 regardless).
