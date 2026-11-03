# elmer (ambient PPA) — SaveScalars dump (run_thermal)

Version provenance: `ElmerSolver` on PATH, banner
`ELMER SOLVER (v 26.2)` observed on this host; provision pin is
PPA-only/ambient. Adapter `src/adapters/elmer/__init__.py`.

## Report inventory

One phase per job: `ElmerSolver <case.sif>` under the job
timeout. SaveScalars JSON (`savescalars.json`) is the first
channel, CSV next, VTU fields as artifacts, NS/SS stdout lines
last. Native output is `{exit_code, stdout, stderr, dump,
dump_file}`.

## Grammar

Dump mapping: `{scalars: {name: float}, converged: bool}`.
Fallback: `^(NS|SS) \(ITER=` lines. Parsed result: `{total,
violations[], measurements[], source}` with `source` `dump` or
`stdio_fallback`. Non-converged or empty scalars yields one
`fem_converge` error.

## Exit states

- No dump and no NS/SS lines: `runner_unavailable`.
- ElmerSolver absent: `missing_dependency` with
  BLOCKED-needs-host (CSC PPA route).
- Fatal input: exit 1 with `ERROR STOP 1`; success prints
  `ALL DONE`.

## Version sensitivity

Stable: SaveScalars JSON keys, NS/SS heads, exit codes.
Incidental: banner dates, thread notes.

## Out of scope

VTU/VTK/Gmsh payload grammars (artifacts via pyvista/VTK);
restart ASCII (writer-verified, needs a golden fixture).
