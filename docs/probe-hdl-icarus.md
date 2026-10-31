# HDL sim probe via Icarus (run_hdl_test input, 2026-10-28)

First HDL execution path. Tools from oss-cad-suite at
`~/tools/oss-cad-suite` (NOT on the agent PATH — B10 must put it
there): iverilog 14.0 + vvp, yosys 0.70, verilator, ghdl, slang, sby
present; verible, openroad, sta absent.

## Verified protocol (counter + testbenches)

| Case | Compile exit | Run exit | Signal |
|---|---|---|---|
| clean tb | 0 | 0 | `TB_PASS`, `$finish` note |
| syntax error | 2 | n/a | `file:line: syntax error` on stderr |
| `$fatal` assert | 0 | 1 | `FATAL: file:line: msg` + Time/Scope |
| `$error` assert | 0 | 0 | `ERROR: file:line: msg` + Time/Scope |

Two honesty rules fall out:

- `$error` exits 0. The verdict MUST come from parsing output for
  `^(FATAL|ERROR):` lines, never from the exit code alone.
- Shell pipelines hide tool exits (`$?` after `cmd | head` is head's).
  The adapter captures to files/streams and reads the real status.

VCD waves work via `$dumpfile`/`$dumpvars` (809-byte `wave.vcd` from
the probe counter) — the `wave` artifact path in engine-api §4.

## Adapter sketch (next: HdlSimAdapter RED)

- `preflight`: iverilog + vvp on PATH, sources exist, top/testbench
  named.
- `execute`: `iverilog -o sim.vvp sources...`, then `vvp sim.vvp`
  with a timeout (sims can hang); capture both streams.
- `parse`: compile diagnostics → error findings (`file:line:msg`);
  FATAL/ERROR lines → error findings with sim time; no findings →
  PASS. Compile failure short-circuits (no run attempted).
- Fixtures: `counter.v` + `tb_{pass,fatal,error}.v` + broken variant
  under `tests/adapters/fixtures/hdl/`, mirroring the DRC fixtures.
- Skip guard: tests skip where iverilog is absent, same as the DRC
  adapters. Resolving oss-cad-suite onto PATH is B10 scope.

Follow-up probe: slang (present) for the run_syntax slice.
