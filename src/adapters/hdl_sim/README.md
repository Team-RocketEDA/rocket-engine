# adapters/hdl_sim — Icarus HDL sim solver

`run_hdl_test` behind the `ToolAdapter` port: preflight refuses the
wrong operation, bad timeouts, missing sources, and unresolvable
tools; execute compiles with iverilog then runs with vvp under a
timeout; parse normalizes compile diagnostics plus `FATAL:`/`ERROR:`
lines into `{total, violations[]}` with file/line locations.

Verified against iverilog 14.0 + vvp on counter fixtures
(`tests/adapters/fixtures/hdl/`). `$error` exits 0, so the verdict
comes from parsed output, never the exit code alone.

Tool resolution is PATH plus an explicit job `tool_dir`; where the
tools live is B10 scope. Pass `runner=` (a `BwrapRunner`) to confine
compile and sim runs: tool roots bind read-only, the workdir stays
read-write, output is bounded and sanitized. No Engine registration
yet (deploy-time config).
