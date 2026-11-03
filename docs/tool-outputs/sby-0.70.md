# sby v0.70 — formal status and summary (run_formal)

Version provenance: verified against sby v0.70 (pinned
oss-cad-suite, bundled boolector engine) per
`src/adapters/formal_sby/__init__.py:1-16`. Grammar transcribed
from the adapter's summary regexes plus the status file reader;
canned outputs in `tests/test_coverage_wave1.py` are
transcribed, not live runs.

## Report inventory

Per job the adapter generates `formal.sby` from the sources
(`formal_sby:619-638`), runs `sby -f` bounded and cancellable in
its own process group (`formal_sby:699-741`), and parses two
machine-readable sources (`formal_sby:444-468`): the `formal/`
status file (`<PASS|FAIL|UNKNOWN|ERROR> <rc>`,
`formal_sby:97-108`) wins; the `DONE` summary line is the
fallback. Native output carries `{exit_code, stdout, stderr,
log, timed_out, workdir, sby_file, sources, top, mode, depth,
engines, sby_version, timeout_s}`.

## Grammar

```ebnf
"DONE (" ("PASS"|"FAIL"|"UNKNOWN"|"ERROR") ", rc=" INT ")"
"summary: " "engine_" INT " (" CONFIG ") returned " STATUS ["for " STEP]
"summary: " ("counterexample trace" ["[" LABEL "]"] | "cover trace") ": " PATH
"summary: failed assertion " NAME " at " FILE ":" LINE "." COL ["step " INT]
"summary: reached cover statement " NAME " at " FILE ":" LINE ["." COL] ["step " INT]
"unreached cover statements:" {"summary: " NAME " at " FILE ":" LINE}*
```

(`formal_sby:47-70` plus `_failure_reports`/`_cover_hits`,
`formal_sby:141-195`.) Verdicts always carry scope
(`formal_sby:534-616`): prove PASS is `proven`, bmc/cover PASS
is `bounded`, FAIL carries counterexamples, inconclusive runs
are `unknown`, wall-clock exhaustion is `timeout`, and
zero-property PASS is `bounded-vacuous` FAIL — never a bare
PASS. The vacuous guard lives in
`src/adapters/formal_sby/formal_edge.py:131-152`; property
sites are ifdef-aware (`formal_edge.py:31-128`).

## Exit states

- Exit zero is not PASS: rc 0/2/4/16 map to
  PASS/FAIL/UNKNOWN/ERROR, and the scope lives in the
  measurements (`formal_sby:7-9`).
- Timeout natives report scope `timeout` with a
  `formal_timeout` error (`formal_sby:481-500`); expiry
  SIGKILLs the whole process tree (`formal_sby:719-731`).
- No status file and no DONE line: `runner_unavailable`
  (`formal_sby:503-510`) — unparseable never parses as clean.
- An sby FAIL with no failed assertion still yields one
  `assert_fail` error rather than going clean
  (`formal_sby:570-579`).
- Impostor/unprobed sby binary: `missing_dependency` via the
  `SBY ` banner version probe (`formal_sby:676-697`).

## Version sensitivity

Stable: status file shape, DONE line, `summary:` prefixes.
Incidental: engine config strings, trace relpaths, yosys
error text inside ERROR verdicts.

## Out of scope

`.sby` task-file authoring beyond the generated shape;
solver-engine internals (boolector stays a bundled detail);
VCD trace contents (waveform scope, later wave).

## Fixtures

- `tests/adapters/fixtures/formal/counter.v` (passing).
- `tests/adapters/fixtures/formal/counter_bad.v` (fails).
- `tests/adapters/fixtures/formal/counter_broken.v`,
  `counter_cover*.v`, `serv_alu_*.v` (edge corpus).
