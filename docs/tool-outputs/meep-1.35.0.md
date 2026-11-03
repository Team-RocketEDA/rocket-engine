# meep 1.35.0 — in-API dump plus S1 telemetry (run_optical)

Version provenance: pymeep==1.35.0 pin per
`scripts/provision_toolchain.sh`; absent in this venv
(`import meep` fails) so live legs skip BLOCKED-needs-host.
Adapter `src/adapters/meep/__init__.py`.

## Report inventory

One phase per job: run the driver under subprocess python
(pymeep env); results via `get_fluxes` / `get_dft_array` /
`get_array` / `Harminv.modes` dumped to `meep_dump.json`; HDF5
field/DFT/far-field files stay as artifacts. Native output is
`{exit_code, stdout, stderr, dump, dump_file}`.

## Grammar

Dump mapping: `{fluxes: [floats], modes: [...], transmission:
float}`. Fallback: S1 telemetry
`^(flux|force|((electric|magnetic|total)-energy)|ldos|harminv)\d*:,`.
Parsed result: `{total, violations[], measurements[], source}`
with `source` `dump` or `stdio_fallback`.

## Exit states

- Dump present: clean (measurements flux + transmission).
- No dump, no telemetry, nonzero exit: one `optical_fail` error.
- No dump, no telemetry, exit 0: `runner_unavailable` (a clean
  exit with nothing parsed never goes clean).
- meep not importable: `missing_dependency` with
  BLOCKED-needs-host.

## Version sensitivity

Stable: S1 line heads, HDF5 `{comp}{-stamp}.h5` naming.
Incidental: progress/diagnostic chatter (verbosity-gated).

## Out of scope

HDF5 dataset parsing (artifacts via h5py downstream); PNG
(h5topng) and timing CSV (informational).
