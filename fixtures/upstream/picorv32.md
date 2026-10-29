# Vendored fixture: picorv32

- upstream: https://github.com/YosysHQ/picorv32
- pinned rev: `ef203c2b0a3fb793280f5114941416c425c5b461`
- license: ISC
- domain: D

## Documented results (what 'correct' means)

Canonical small RISC-V core; ships Verilog + testbenches. Correct = its testbenches pass under Icarus/Verilator (see the vendored tree's testbench + firmware tests).

Fetched by `scripts/fetch_fixtures.py` (FIXTURE-FETCH). Do not hand-edit the tree under `picorv32/`; re-pin by updating `FIXTURES` and re-running the fetch.
