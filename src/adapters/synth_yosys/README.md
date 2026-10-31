# adapters/synth_yosys — Yosys synth solver

`run_synth` behind the `ToolAdapter` port: preflight refuses the
wrong operation, bad tops, missing sources, and unresolvable or
unassertable tools; execute synthesizes with `synth -top` (plus
`dfflibmap`/`abc -liberty` mapping when a liberty is given) under a
timeout; parse normalizes `ERROR:`/`Warning:` lines plus the stat
report into `{total, violations[]}` with cell counts, the mapped
area, and the netlist artifact path.

Verified against Yosys 0.70+219 (oss-cad-suite) on counter fixtures
(`tests/adapters/fixtures/synth/`) plus vendored SERV (top
`serv_top`) and picorv32. Warnings (latch inferred, undriven wires)
are findings that never fail alone; broken RTL and a missing top
fail loudly via `hierarchy -check`. ABC's own `ABC: Warning:` lines
are optimizer chatter, never findings.

Tool resolution is PATH plus an explicit job `tool_dir`, and the
binary must answer `yosys -V` with a parseable banner; where the
tools live is B10 scope. Pass `runner=` (a `BwrapRunner`) to confine
synth runs: tool roots bind read-only, the workdir stays read-write,
output is bounded and sanitized. No Engine registration yet
(deploy-time config — see `docs/work/SYNTH-YOSYS/report.md` for the
integrator wiring patch).
