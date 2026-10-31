# timing_sta adapter — run_timing via OpenSTA

Standalone top-level timing recheck (M11): mapped netlist + timing
libs + SDC, plus an optional top-level SPEF, flow to `sta` and come
back as setup/hold WNS/TNS, critical paths, slew/load violators,
and unconstrained endpoints.

- Operation `run_timing`, deck.tool `opensta` (only tool).
- Preflight refuses the wrong operation, bad tops/timeouts,
  missing inputs, and unresolvable or unassertable tools with a
  PROV remedy — never a PATH lottery.
- Execute writes `timing.tcl` and runs `sta timing.tcl` under the
  job timeout with stdin closed; the trailing `exit` keeps `sta`
  off its interactive prompt.
- Parse splits the log on `TIMING_STA` markers. Violated paths
  become `setup_violation`/`hold_violation` errors, `VIOLATED`
  constraint lines become `constraint_violation` errors, any
  `Error:` line fails the run however it exited, and warnings —
  including `unconstrained_endpoint` findings — never fail alone.
  Raw `check_setup` text always rides along: missing constraints
  are listed, never silent, never assumed.

Tool resolution: job `tool_dir`, then `$OPENSTA_PREFIX/bin` (the
PROV consumer contract), then PATH; the binary must answer
`-version` (fallback `--version`) with an `OpenSTA` banner.
