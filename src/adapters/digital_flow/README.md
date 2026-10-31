# adapters/digital_flow — LibreLane digital-flow solver

`run_digital_flow` behind the `ToolAdapter` port: preflight refuses the
wrong operation, foreign deck tools, bad flow inputs, missing sources,
and unresolvable or unpinned tools; execute stages the project RTL
into a LibreLane design dir and runs the Classic flow as a subprocess
under the job timeout; parse judges the D11–D27 stage gates from the
run's step dirs into `{total, violations[]}` with per-stage evidence
plus GDS, netlist, SPEF, DRC-total, and LVS-match measurements.

Verified hermetically with a stub `librelane` (version probe plus
fake `design/runs/<tag>/` trees: clean, partial, synth-fail, DRC/LVS/
STA failures, timeout tree-kill). Live proof needs the pinned
LibreLane 3.0.17 supported distribution plus a LibreLane PDK root:
the SERV/counter/broken live tests skip loudly (never fake-green)
where either is absent.

Tool resolution is PATH plus an explicit job `tool_dir`, and the
binary must answer `librelane --version` with the pinned 3.0.17
banner; where the tools live is B10/PROV scope. Pass `runner=` (a
`BwrapRunner`) to confine flow runs: tool roots plus the PDK root
bind read-only, the workdir stays read-write. No Engine registration
yet (deploy-time config — see `docs/work/DIGITAL-FLOW/report.md` for
the integrator wiring patch).
