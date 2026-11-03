# verilator 5.053 — SARIF plus lint text (run_hdl_test provider)

Version provenance: `verilator --version` prints
`Verilator 5.053 devel` on this host (bundle era 5.053/5.054;
xml-only dead since 5.046 — SARIF/JSON only). Provider
`src/adapters/hdl_sim/verilator.py`.

## Report inventory

Lint runs `--lint-only --diagnostics-sarif`; the SARIF file is
the first channel, `%Error`/`%Warning` stderr the fallback.

## Grammar

SARIF results: ruleId plus file/line plus level. Fallback:
`^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):`.
Verdict from parsed errors, never exit code (warnings-only
exits 1).

## Exit states

- Exit nonzero with nothing parseable: synthesized
  `lint_error`.
- verilator absent: `missing_dependency` with
  BLOCKED-needs-host.
