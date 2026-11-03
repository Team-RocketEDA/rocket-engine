# ghdl 7.0.0-dev — assert lines plus synth stats (providers)

Version provenance: `ghdl --version` prints `GHDL 7.0.0-dev` on
this host (bundle member, no separate pin). Providers
`src/adapters/hdl_sim/ghdl.py` (run_hdl_test) and
`src/adapters/synth_yosys/ghdl.py` (run_synth frontend).

## Report inventory

Sim: `-a` then `-e` then `-r`; assert/report lines arrive on
stdout (runtime diags go to STDOUT, compile diags to STDERR —
never merge blindly). Synth: `ghdl --synth --out=verilog -o`
plus `--stats` text.

## Grammar

Assert line:
`FILE:LINE:COL:@TIME:(assertion|report|... SEV): MSG` with
SEV note/warning/error/failure (notes never fail). `simulation
failed` plus exit 1 on stop-level trips. Synth stats:
`Statistics for netlists:` shape (stable-ish debug grammar).

## Exit states

- Clean run with no asserts: total 0.
- ghdl absent: `missing_dependency` with BLOCKED-needs-host.

## Out of scope

GHW (unstable — read via libghw/pywellen); pyGHDL sim-runner
bindings (none exist — AST/diagnostics only).
