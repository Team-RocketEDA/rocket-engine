# yosys 0.70 — synth stat + diagnostics (run_synth)

Version provenance: `Yosys 0.70+219` observed on this host via
`yosys -V` (oss-cad-suite `20261025` pin per
`scripts/provision_toolchain.sh:73`); adapter
`src/adapters/synth_yosys/__init__.py:1-21`. Canned natives in
`tests/adapters/test_synth_yosys.py` are transcribed, plus live
runs where yosys exists.

## Report inventory

One mode per job: the adapter writes `synth.ys` (`synth_yosys:459-489`)
— `read_verilog` the sources, `hierarchy -check -top`, `synth -top`,
then `stat` plus `write_verilog`. With a `liberty` input it maps to
standard cells (`dfflibmap` + `abc -liberty`, `stat -liberty`).
Native output is `{exit_code, stdout, stderr, log, stat, netlist,
top, mapped, yosys_version}` (`synth_yosys:317-366`).

## Grammar

Version banner (`synth_yosys:47`):

```ebnf
"Yosys " MAJOR "." MINOR
```

Errors (`synth_yosys:48`):

```ebnf
[FILE ":" LINE ": "] "ERROR: " MESSAGE
```

Warnings (`synth_yosys:49`), classified (`synth_yosys:82-95`):
`Latch inferred` → `latch`, `has no driver` → `undriven`, else
`synth_warning`. Skipped (never findings): `ABC: Warning:`
optimizer chatter, the `Warnings: N unique` summary line.

Stat report (`synth_yosys:131-182`): per `=== module ===` section,
local counts excluding submodules (summed for the design total);
`Chip area for top module '…': FLOAT` wins when present, else
per-module areas sum. Wire/cell line shapes:

```ebnf
INT "wires" | INT "cells" | INT FLOAT? CELLTYPE
```

Parsed result: `{total, violations[], measurements[]}` plus
`cells`, `cell_count`, `wire_count`, `area`, `mapped`, `netlist`,
`top`, `yosys_version` (`synth_yosys:368-456`).

## Exit states

- `hierarchy -check` fails loudly (nonzero exit + `ERROR:`) on a
  missing top; broken RTL fails the same way — a failed run never
  parses as clean (synthesized `synth_error` when the log carries
  none).
- Warnings never fail the verdict alone.
- Clean run with no stat cells block or no netlist artifact:
  `runner_unavailable` — unparseable never parses as clean.
- Timeout: `runner_unavailable`.
- Unresolvable/unassertable yosys: `missing_dependency`.

## Version sensitivity

Stable: `ERROR:`/`Warning:` prefixes, stat section shape,
`Yosys major.minor` banner. Incidental: cell-type names, area
float formatting, ABC chatter wording.

## Out of scope

`write_json` structured stat (ESCAPE-HARDEN item 1: audit
mandates it, rejects pyosys — recorded gap, not implemented
here); `read_slang` logging (SHAPE-HARDEN yosys_slang item);
post-map timing (TIMING-STA scope).

## Fixtures

- `tests/adapters/fixtures/synth/` (clean / broken / latch /
  undriven corpus; see `tests/adapters/test_synth_yosys.py`).
