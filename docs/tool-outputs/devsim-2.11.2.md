# devsim 2.11.2 — driver JSON dump (run_tcad)

Version provenance: `import devsim` loads in the engine venv
(BLAS/LAPACK lines on import); provision pin devsim==2.11.2 per
`scripts/provision_toolchain.sh`. Adapter
`src/adapters/devsim/__init__.py`.

## Report inventory

One phase per job: run the driver script under the job timeout;
the driver calls `get_contact_current` / `get_*_model_values` /
`solve(info=True)` plus `write_devices` files and dumps JSON to
`devsim_dump.json`. Native output is `{exit_code, stdout, stderr,
dump, dump_file}`.

## Grammar

Dump mapping: `{currents: {contact: amps}, potentials: [floats],
solve: {converged: bool, iteration: int}}`. Parsed result:
`{total, violations[], measurements[], source}` with `source`
`dump`. A non-converged solve or empty currents yields one
`tcad_converge` error; currents map to `current.<contact>` (A).

## Exit states

- No dump file: `runner_unavailable` (never clean).
- devsim not importable: `missing_dependency` with
  BLOCKED-needs-host (needs devsim==2.11.2 in the engine venv).
- Hangs raise `runner_unavailable`.

## Version sensitivity

Stable: A1/A2/A6 API shapes, solve(info=True) maps. Incidental:
BLAS loader chatter on import.

## Out of scope

VTK/tecplot/restart file parsing (artifacts, not verdicts);
stdout print_*/iteration-log scraping (every numeric line has an
API twin).
