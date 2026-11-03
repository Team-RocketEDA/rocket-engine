# cace 2.13.0 — summary.md verdicts (run_characterize)

Version provenance: `import cace` reports 2.13.0 in the engine
venv (matches CACE_PIN); the `cace` CLI binary is absent on
this host so live runs refuse BLOCKED-needs-host. Adapter
`src/adapters/cace/__init__.py`. Grammars below are verified at
the 2.13.0 import; summary.md columns must be re-verified on a
live gate host before staffing a full normalizer.

## Report inventory

`cace <datasheet> --no-progress-bar` as a subprocess; gate on
the exit code (0 pass, 2 spec miss, 1/3/4 error/unknown/
canceled). Values come from `RUN_*/summary.md` rows plus
`parameters/*/simulation_summary.csv`, never flow.log.

## Grammar

summary.md 10-col rows with Status in `Pass ✅ Fail ❌ Error ❗
Unknown ❓ Skip/Cancel 🟧`. Parsed result: `{total,
violations[], source}` with `source` `summary_md`.

## Exit states

- No summary.md: `runner_unavailable`.
- cace binary or package absent: `missing_dependency` with
  BLOCKED-needs-host (need cace==2.13.0).
