# Per-tool output dissection — index

Synthesis of 21 dissector reports. Dissectors wrote nothing; this directory is the write surface.
Branch: GREEN-the-tests. One commit; never push.

Reports written: 21 / 21. Missing tools: 0.

## Missing tools

None — all 42 handoff parts (21 text + 21 summary) read successfully.

## Per-tool one-line verdicts

| Tool | Dissector ref | Clone | Verdict |
|---|---|---|---|
| [xyce](./xyce.md) | 9 | a592a42ae747 / 2025-06-10 | 1. `.PRINT FORMAT=CSV` + `.MEASURE` (`.mtN` `NAME = value`) — primary; |
| [openroad](./openroad.md) | 8 | f3d27840b65a / 2026-11-02 | 1. BINDINGS (primary): `-metrics out.json` for all scalars (timing/power/area/drv/antenna/congestion counts); |
| [eqy](./eqy.md) | 3 | 33015166c473 / 2026-10-27 | 1st — STRUCTURED FILES (no bindings exist): V1 filename for top verdict; |
| [mcy](./mcy.md) | 1 | 5a2cad0cbefc / 2026-08-04 | 1st: query `database/db.sqlite3` with stdlib sqlite3 (queryable-DB tier — no text parsing). |
| [openrcx](./openrcx.md) | 7 | a0c988ddc591 / 2020-12-16 | 1st: SPEF file (ch.1) — IEEE-grammar-stable, hardcoded units/date, golden-covered; |
| [cace](./cace.md) | 2 | d71c8da5f8d8 / 2025-02-07 | (1) Run `cace <ds.yaml> [--run-path DIR] [--no-progress-bar] [-s src] [-p/--skip-parameter …]` as subprocess; |
| [meep](./meep.md) | 4 | b08d226ba311 / 2026-10-09 | 1) In-API numpy (rank 1): run user script under subprocess `python` (pymeep env), results via `get_fluxes/get_dft_array/get_array/Harminv.modes` — zero parsing. |
| [openems](./openems.md) | 6 | 305df56aa7df / 2026-10-09 | (1) BINDINGS-READ: h5py via `HDF5Dump`/`nf2ff_results`/`readSAR` shapes + probe-file reader (`_load_ui_file`, `%`-comment grammar) — reuse shapes, keep execution subprocess. |
| [palace](./palace.md) | 11 | 8874e6cf8f3c / 2026-10-30 | No bindings exist → ranked file paths: (1) CSV tables — primary (pandas-parseable; |
| [femwell](./femwell.md) | 5 | be2c54763f62 / 2026-03-06 | Rank 1 (only sane path): BINDINGS — subprocess driver script that imports femwell, runs compute_modes/solvers, and emits a JSON envelope of {n_effs (re/im), k, te_fraction, power, confinement, loss_dB, effective_area, field-dof arrays or interpolated grids} + mesh metadata. |
| [elmerfem](./elmerfem.md) | 13 | 31f541c74737 / 2026-10-29 | 1. SaveScalars `Json Format=True` — self-describing structured file (validate the hand-rolled writer once with a fixture). |
| [devsim](./devsim.md) | 10 | e3a25f08c7f1 / 2026-10-23 | 1) Bindings: run user/devsim script in subprocess; driver calls A1/A2/A4/A5/A6 + solve(info=True) and dumps JSON — full fidelity, zero parsing. |
| [kfactory](./kfactory.md) | 16 | 380796e9b38d / 2026-10-23 | 1. (bindings) Drive via subprocess `python -c`/`kf build` writing artifacts, then READ in-process: KCell.netlist()[name].sort().to_json() for connectivity/LVS-equality; |
| [xschem](./xschem.md) | 14 | 7a20d5610129 / 2026-11-01 | (1) STRUCTURED FILES: run `xschem <cell>.sch -q -x -r -n -s [-f] -o <dir> [-N <file>]` (canonical flags from tests/netlisting.tcl:85: `… -q -x -r -$opt -o $netlist_output_dir -n`, opt∈s/V/w/t), assert exit∈{0,10}, read `$dir/<cell>.spice` (+`.vhdl/.v/.tdx/.spectre` as needed)… |
| [vlsir](./vlsir.md) | 15 | 194c7a76f01e / 2026-02-15 | 1. **Bindings (first)**: read via `vlsirtools.spice.sim(..., SimOptions(fmt=SIM_DATA))` for numpy-native post-processing, or `VLSIR_PROTO` (default) for portable `SimResult` protos; |
| [amaranth](./amaranth.md) | 12 | 90449f1e6d5a / 2026-09-18 | 1) Native API returns — `back.*.convert()` str (+rtlil name_map), `products.get()`, testbench ctx reads; |
| [ghdl](./ghdl.md) | 19 | 428cc4b734be / 2026-11-01 | 1) Analyze-stage: pyGHDL.dom/libghdl + errorout_memory for AST/diagnostics (no text scrape). |
| [verilator](./verilator.md) | 21 | 1b27515019d7 / 2026-11-01 | No bindings exist, so ranked file-first: 1. check.syntax (lint): `--lint-only --diagnostics-sarif` → parse `<prefix>.sarif` (machine grammar, rule+loc native); |
| [openvaf](./openvaf.md) | 20 | a9697ae77805 / 2023-10-30 | 1. **Structured file (primary, subprocess-clean): CLI `openvaf in.va -o out.osdi`, then read descriptors via dlopen/dlsym per `osdi_0_3.h`.** Keeps execution subprocess; |
| [nextpnr](./nextpnr.md) | 18 | a2c6479977d6 / 2026-10-31 | if staffed later: (1) C2 --report JSON (util+fmax+critical paths; |
| [yosys_slang](./yosys_slang.md) | 17 | 4a77e391c2a6 / 2026-10-29 | 1st -- Structured file (KEEP-STRUCTURED, audit row confirmed): `read_slang ...` then Yosys `write_json <file>`; |

## Shared-format map (one reader serves many tools)

Derived by keyword scan over the full dissector texts; counts are mention-based, not proof of identical schema.

| Shared format | Tools mentioning it | Reader win |
|---|---|---|
| JSON report | amaranth, cace, devsim, elmerfem, eqy, femwell, ghdl, kfactory, nextpnr, openrcx, openroad, openvaf, palace, verilator, vlsir, yosys_slang (16) | stdlib json + per-tool schema |
| Verilog netlist | amaranth, eqy, ghdl, mcy, openrcx, openroad, openvaf, verilator, vlsir, xschem, yosys_slang (11) | one Verilog parser |
| CSV table (.csv) | cace, elmerfem, ghdl, meep, nextpnr, palace, vlsir, xyce (8) | one CSV reader |
| SPICE netlist | cace, openroad, vlsir, xschem, xyce (5) | one SPICE reader |
| VCD waveform (.vcd) | amaranth, eqy, ghdl, verilator, xschem (5) | one VCD reader (e.g. pywellen) |
| RTLIL netlist (.il) | amaranth, eqy, mcy, yosys_slang (4) | one RTLIL reader |
| VTK/VTU field dump (.vtk/.vtu) | devsim, elmerfem, openems, palace (4) | one VTK reader (pyvista/paraview) |
| GDSII layout (.gds) | cace, kfactory, openroad (3) | one GDS reader (gdstk/klayout) |
| Run log file | cace, eqy, mcy (3) | log tail + exit code |
| SDC/SDF timing | amaranth, nextpnr, openroad (3) | one SDC/SDF reader |
| Touchstone S-param (.sNp) | openems, palace, xyce (3) | one Touchstone reader (scikit-rf) |
| Transient/AC table (.prn/.raw) | vlsir, xschem, xyce (3) | one Xyce/Ngspice raw reader |
| DEF/LEF physical | openrcx, openroad (2) | one DEF/LEF reader |
| FST/GHW waveform | ghdl, verilator (2) | one FST/GHW reader (pywellen/libghw) |
| HDF5 (.h5) | meep, openems (2) | one HDF5 reader (h5py) |
| SPEF parasitics (.spef) | openrcx, openroad (2) | one SPEF reader (IEEE 1481) |
| YAML datasheet | cace, kfactory (2) | one YAML reader (pyyaml) |

## Top shared-format wins

- JSON report: 16 tools (amaranth, cace, devsim, elmerfem, eqy, femwell, ghdl, kfactory, nextpnr, openrcx, openroad, openvaf, palace, verilator, vlsir, yosys_slang) — stdlib json + per-tool schema.
- Verilog netlist: 11 tools (amaranth, eqy, ghdl, mcy, openrcx, openroad, openvaf, verilator, vlsir, xschem, yosys_slang) — one Verilog parser.
- CSV table (.csv): 8 tools (cace, elmerfem, ghdl, meep, nextpnr, palace, vlsir, xyce) — one CSV reader.
- SPICE netlist: 5 tools (cace, openroad, vlsir, xschem, xyce) — one SPICE reader.
- VCD waveform (.vcd): 5 tools (amaranth, eqy, ghdl, verilator, xschem) — one VCD reader (e.g. pywellen).
- RTLIL netlist (.il): 4 tools (amaranth, eqy, mcy, yosys_slang) — one RTLIL reader.
- VTK/VTU field dump (.vtk/.vtu): 4 tools (devsim, elmerfem, openems, palace) — one VTK reader (pyvista/paraview).
- GDSII layout (.gds): 3 tools (cace, kfactory, openroad) — one GDS reader (gdstk/klayout).

## Weak-evidence gaps (cross-tool)

- xyce: - `.fftN` + `-rsf` file + `.csd` byte layout: partially UNRESOLVED (emitters verified: `N_IO_FFTMgr.C:285`, `N_IO_OutputResponse.C:51`, `N_IO_OutputCsd.C`/`N_IO_Probe.*`; bodies not read — see gaps).
- openroad: | 10 | SDC | `write_sdc ...` (OpenSTA submodule — UNINSPECTED, empty clone; usage src/dbSta/test/write_sdc1.tcl:9) | `*.sdc` |
- eqy: V1 verdict file: content = summary lines only (eqy_job.py:708-709). Gating is by FILENAME: examples/simple/Makefile test target = `aliases/PASS combine/PASS …` (file-existence gate). NOTE outdir.rst s
- mcy: | C5 | Yosys logs/scripts | `init`/`reset` | `database/design.ys/.log`, `mutations.ys/.log`, `mutations2.ys/.log`, `setup.sh`, `setup/` | files | Provenance/debug; setup.sh only if [setup] (mcy.py:462
- openrcx: Clone: /tmp/rocket-tool-src/openrcx @ a0c988ddc591b0b6e18c073d72a112aeb81a4bc3, date 2020-12-16. NOTE: standalone repo, stale; upstream now lives at The-OpenROAD-Project/OpenROAD src/rcx, docs https:/
- cace: PIN/VERSION: provision pins `CACE_PIN="2.13.0"` (`rocket-engine/scripts/provision_toolchain.sh:84`, pip version-assert in engine venv). MISMATCH: evidence below verified at 2.5.6, ~8 minors behind the
- meep: 4. STDIO-ONLY RESIDUE: nearly zero for physics. Every S1 CSV table has an in-API twin (flux/force/energy getters, `ldos_data`, `Harminv.modes`), because `display_*` only pretty-prints the same objects
- openems: | C9 | Debug VTK + CSX XML | `--debug-material|--debug-PEC|--debug-operator|--debug-boxes|--debug-CSX` | `material_dump.vtk`,`PEC_dump.vtk`,`operator_dump.vtk`,`box_dump_*.vtk`,`debugCSX.xml` |
- palace: No bindings exist → ranked file paths: (1) CSV tables — primary (pandas-parseable; stable Table writer; headers carry units; parse positionally); port-S.csv needs mag/phase→complex conversion for Touc
- femwell: | E | stdout text (demo/debug only) | `print(modes)`, `print(modes[0].te_fraction)` (maxwell/waveguide.py:917-918, __main__); `Mode.__repr__`/`Modes.__repr__` (:161-162,:516-518); `print(sign)` tcad.p
- elmerfem: Version evidence: all verified at clone 31f541c7 dated 2026-10-29; provision pin is PPA-only/ambient, so an adapter must record `ElmerSolver --version` banner + the sif keywords above in its fixture p
- kfactory: | F7 | Report DB (DRC/connectivity) | KCell.connectivity_check -> rdb.ReportDatabase (kcell.py:2497); checks.port_mismatch_check / dangling_ports_check / instance_overlap_check / shape_instance_overla
- xschem: 7 | C diagnostics | any run; `-l/--log file` redirects (options.c:120-129); `-d n` debug level; `-b/--detach` discards stdio (main.c:123-134) | stderr (errfp; main.c:81, editprop.c:312 `info()`→errfp,
- vlsir: PIN/VERSION: vlsir==7.0.0 + vlsirtools==7.0.0 — verified at: `bindings/python/setup.py:18`, `VlsirTools/setup.py:18`, `VlsirTools/vlsirtools/__init__.py:5`, `bindings/python/vlsir/__init__.py:8`, test
- amaranth: | F | Build tree + products | `Platform.build(elab,name="top",build_dir="build",do_build)` → `prepare()` → `BuildPlan.execute_local(root)` runs `sh build_{name}.sh` in root (build/run.py:95, build/pla
- ghdl: | 16 | Exit code | all | 0 ok / 1 fail / 3 exec-err / 2 bug-box (src/ghdldrv/ghdlmain.adb:697-706); sim rc=Grt.Errors.Exit_Status (ghdlrun.adb:428-429) |
- verilator: | C17 | build-internal | -MMD/--skip-identical/--hierarchical/--make json/--debug/--dump-tree* | __ver.d, __verFiles.dat, __hier*, *.mk/__hierMkJsonArgs, *.tree/*.dot/*.vpp, <prefix>.json | internal/d
- openvaf: | C4 | `--dump-json` | DEAD FLAG: driver bails `currently unimplemented` (`main.rs:74-81`); impl commented out (`lib.rs:49-105`) | intended `<stem>_<module>.json` (never written) | none |
- nextpnr: 4. STDIO-ONLY RESIDUE (never written to a file channel)
- yosys_slang: | C3 | Raw-stdout AST JSON (dev/debug) | `read_slang --dump-ast ...` (option slang_frontend.cc:127; emit driver.cc:584-590; test-expr path driver.cc:846-851) | real stdout via `std::cout` (NOT yosys l

## Evidence refs

Handoff index: /home/alrida-ismail/.local/share/muse/sessions/2026/10/28/01a1810f-c750-7420-b6df-aabebe100b2a/tool-outputs/workflow-results/handoff-e0fe429174068eade6486406e134e250e3b501568f1d91149fc4fed0f094fbb5-61a947f6378a6cceb2420ca9b682c9dfd23bda0e684d7bfe7dcb49a709a7342b.txt
Per-tool text/summary filenames are recorded at the top of each report.
