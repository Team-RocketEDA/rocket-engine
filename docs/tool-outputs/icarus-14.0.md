# icarus 14.0 — compile diagnostics + sim assertions (run_hdl_test)

Version provenance: `Icarus Verilog version 14.0 (devel)` and
`Icarus Verilog runtime version 14.0 (devel)` observed on this
host via `iverilog -V` / `vvp -V` (oss-cad-suite `20261025` pin
per `scripts/provision_toolchain.sh:73`); adapter
`src/adapters/hdl_sim/__init__.py:1-13`.

## Report inventory

Two phases per job (`hdl_sim:173-224`): compile the sources with
`iverilog -o sim.vvp` (exit 2 + diagnostics on failure), then run
`vvp sim.vvp` under the job timeout. Native output is `{exit_code,
compile, run}` with `{exit_code, stdout, stderr}` blocks; `run` is
None when the build failed.

## Grammar

Compile diagnostics (`hdl_sim:27`):

```ebnf
FILE ":" LINE ": " MESSAGE
```

Messages starting with `warning` (case-insensitive) are warnings,
else errors (`hdl_sim:39`). Sim assertions (`hdl_sim:28`):

```ebnf
("FATAL"|"ERROR") ": " FILE ":" LINE ": " MESSAGE
```

`FATAL` → rule `assert_fatal`, `ERROR` → `assert_error`
(`hdl_sim:61`); a `Time: INT` match on the next line attaches
`sim_time` (`hdl_sim:29,68-70`). Parsed result:
`{total, violations[]}` with file/line and sim_time where
reported (`hdl_sim:226-275`).

## Exit states

- `$error` exits 0: the verdict always comes from parsed output,
  never the exit code alone (`hdl_sim:5-7`).
- Failed compile with no parseable diagnostics synthesizes one
  `compile` error rather than going clean; crashed sims with
  nothing parseable synthesize `sim_fail`.
- Compiled run with no run block: `runner_unavailable`.
- Hangs raise `runner_unavailable` instead of hanging the engine.
- Unresolvable tools: `missing_dependency`.

## Version sensitivity

Stable: `file:line:` diagnostic shape, `FATAL:`/`ERROR:` sim
lines, exit-2 compile failure. Incidental: diagnostic message
wording across iverilog releases, `$error` text.

## Out of scope

`$dumpfile`/VCD waveform output (ESCAPE-HARDEN item 3: no VCD
or pywellen refs — recorded gap, not implemented here);
coverage (`cover` scope belongs to formal/cosim lanes).

## Fixtures

- `tests/adapters/fixtures/hdl/counter.v` (clean).
- `tests/adapters/fixtures/hdl/counter_broken.v` (compile error).
- `tests/adapters/fixtures/hdl/serv_harness.v` + `serv_sources.txt`
  (SERV corpus).
