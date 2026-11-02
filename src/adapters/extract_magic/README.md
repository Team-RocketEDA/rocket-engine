# adapters/extract_magic — Magic extraction solver

Batch extraction behind the `ToolAdapter` port: preflight refuses
missing binaries, unloadable techs, and missing cells; execute runs
magic headless (`-dnull -noconsole`) over `extract all` + `ext2spice
lvs`; parse reads back the `<cell>.ext`/`<cell>.spice` pair into
`{device_count, devices[]}` with class + w/l per FET.

Verified against magic 8.3.685 + sky130A tech 1.0.588 on
`sky130_fd_sc_hd__inv_2` from the registered PDK (4 FETs, exact
w/l). Magic exits 0 even on failure, so the verdict comes from
parsed output, never the exit code.

Status: EXTRACT-SKY130 GREEN. See `docs/probe-extract-lvs.md`.
Status: EXTRACT-GDS GREEN. See `docs/probe-extract-gds.md`.
