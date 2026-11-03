# openems — output dissection

Dissector ref: prior result 6 (text `handoff-e7fa185aa9a55ec0633faaa68c653d38791728d5b8f6372b744ef14ba3c1edf9-1f5fa0884e8f5b5c6321aad0bdc2617aabb0aa25953dc1e0451ef119e19817e0.txt`, summary `handoff-30ad07866fbf22c0f0e6c0528da9c8305401daf3edc82382270ed33f0cd5dd55-1f5fa0884e8f5b5c6321aad0bdc2617aabb0aa25953dc1e0451ef119e19817e0.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `305df56aa7df4d2f18c687083f484a96f9a22610`
- Clone date: `2026-10-09`
- Pin: IDENTITY: openEMS clone /tmp/rocket-tool-src/openems @ 305df56aa7df4d2f18c687083f484a96f9a22610, date 2026-10-09 (post-v0.37.0 master). CSXCAD clone @ c46e3206f20027b0b4605c797d07bddab76de942, 2026-10-09. Pin verified: provision_toolchain.sh:87-90 OPENEMS_REF=v0.37.0, CSXCAD_REF=v0.7.0; docs HTML ti
- Doc/source URLs: none in header (see dissector header below)

### Dissector header (verbatim, whitespace-trimmed)

```text
openEMS output dissection (REVIEW ONLY)

IDENTITY: openEMS clone /tmp/rocket-tool-src/openems @ 305df56aa7df4d2f18c687083f484a96f9a22610, date 2026-10-09 (post-v0.37.0 master). CSXCAD clone @ c46e3206f20027b0b4605c797d07bddab76de942, 2026-10-09. Pin verified: provision_toolchain.sh:87-90 OPENEMS_REF=v0.37.0, CSXCAD_REF=v0.7.0; docs HTML title "openEMS 0.37.0 documentation". Evidence verified at master SHAs above (superset of v0.37.0).
```

## 1. Result channels

1. RESULT CHANNELS (producing flag/command -> file pattern; all paths relative to CWD/sim_path)
| # | Channel | Producer | Pattern |
|---|---|---|---|
| C1 | Port/probe TD series (ext-less text) | `openEMS <xml>`; ProbeBox in CSX; names from python ports.py or user | `<ProbeName>` e.g. `port_ut_1`,`port_it_1`; MSL `port_ut_1{A,B,C}`,`port_it_1{A,B}`; multibox `<name>_<n>` |
| C2 | Port/probe FD companion (ext-less text) | same, when ProbeBox has FDSamples | `<ProbeName>_FD` |
| C3 | Field dump HDF5 | DumpBox FileType=1 (CSX attr) | `<DumpName>.h5` |
| C4 | Field dump VTK legacy | DumpBox FileType=0 | TD `<name>_<ts8>.vtk`; FD `<name>_f=<f>_p=<000..360>.vtk` x21 + `<name>_f=<f>_{abs,arg}.vtk` |
| C5 | Field dump VTK-XML | same writer, XML path | same basenames + writer default ext (.vtr/.vts) |
| C6 | nf2ff far-field HDF5 | `nf2ff <nf2ff-xml>` (outfile attr) or python CalcNF2FF (default `<name>.h5`) | user outfile, conventionally `*.h5` |
| C7 | SAR HDF5 | DumpBox type 20/21/22/29 | `<DumpName>.h5` (FD-shaped) |
| C8 | Run stats text | `openEMS --dump-statistics` | `openEMS_run_stats.txt`, `openEMS_stats.txt` (fixed names) |
| C9 | Debug VTK + CSX XML | `--debug-material|--debug-PEC|--debug-operator|--debug-boxes|--debug-CSX` | `material_dump.vtk`,`PEC_dump.vtk`,`operator_dump.vtk`,`box_dump_*.vtk`,`debugCSX.xml` |
| C10 | stdout / stderr streams | any run | progress, verdict, timing lines (see 4) |
| C11 | In-process returns | python post-readers only (never the solver) | numpy arrays / result objects (see 3) |
| — | Touchstone .sNp | NOT a tool output (see 3, correction) | — |
| — | `lm_*` files | NONE FOUND (repo-wide grep empty); focus-hint "lm" = lumped-port `port_ut/it` files | — |

## 2. Format grammars

2. FORMAT GRAMMARS
C1 probe TD (Common/processintegral.cpp:52-72,144-155; processing.cpp:77-82,240-250): filename IS probe name, no extension (`m_filename=m_Name`). Header: `% time-domain <proc> by openEMS <GIT_VERSION> @<ctime>`; `% start-coordinates: (x,y,z) m -> [i,j,k]`; `% stop-coordinates: ...`; `% t/s\t<col1>[\t<col2>]`. Rows: `<t>\t<v1>[\t<v2>]` (setprecision(m_precision), tab-sep, SI units). Column vocab: voltage probe `voltage` (V, processvoltage.cpp:30-35); current `current` (A, processcurrent.cpp:35-40); E-field probe `Ex/(V/m) Ey/(V/m) Ez/(V/m)`, H `Hx/(A/m)...` (processfieldprobe.cpp:41-62); modematch `voltage|current\tmode_purity` (processmodematch.cpp:48-60). Probe types 0/1/2/3/10/11 (openems.cpp:532-573). Port naming: `lbl_temp=prefix+'port_{}_{number}'` (ports.py:119); LumpedPort `port_ut_N`/`port_it_N` (ports.py:280-294); WaveguidePort same via p_type 10/11 (ports.py:589-601).
C2 probe FD (processintegral.cpp:92-132): `<name>_FD`, header `% frequency-domain ...`, `% f/Hz\t<name>\t...`, `%\treal\timag...`, rows `<f_Hz>\t<re>\t<im>...` (single-sided spectrum, x2 factor, :160-166).
C3/C7 field HDF5 (Common/processfields.cpp:129-166; tools/hdf5_file_writer.cpp/h): file `<name>.h5`. Root attrs: `openEMS_HDF5_version`=0.3 (double), `dump_type` (int, enum processfields.h:43: 0 E,1 H,2 J,3 rotH,4 D,5 B; FD file stores base type 0-5 while CSX DumpType is +10; 20 local SAR,21 1g,22 10g,29 raw), `dual_mesh` (bool), optional `legacy_fmt`. /Mesh: attrs `mesh_type` (0 cart/1 cyl/2 sph), `mesh_scaling` (=GridDelta, SI metres; alpha/theta/phi unscaled); datasets `x,y,z` | `rho,alpha,z` | `r,theta,phi`, float64 1-D (hdf5_file_writer.cpp:154-183; mirrored utilities.py:225-229). TD: `/FieldData/TD/<8-zero-padded ts>` vector float32 (3,Nx,Ny,Nz), attr `time` (processfields_td.cpp:67-74; pad default 8, processfields_td.h:35). FD: `/FieldData/FD/f<n>` complex64 vector + group attr `frequency` (Hz vector) (processfields_fd.cpp:178-190). Layout: new `d_order` attr `NXYZ`/`XYZ` x-inner; legacy `NZYX`/`ZYX` split `f<n>_real/_imag` float64 (writer :199-303; reader utilities.py:363-385, returns always (3,Nx,Ny,Nz) x-inner). Raw SAR adds `/CellData`,`/CellWidth` (sar_utils.py docstring).
C4 VTK (tools/vtk_file_writer.cpp:209-248; processfields_fd.cpp:117-173): legacy `.vtk` via VTK lib, header `openEMS {TD,FD} Field Dump -- Interpolation: ...`; TD one file per dumped ts; FD 21 phase files + abs + arg per frequency; freq rendered as int when integral (`:121-125`).
C6 nf2ff HDF5 (nf2ff/nf2ff.cpp:557-698; python nf2ff.py:159-230): /Mesh/{theta,phi,r} + `MeshType`=2; `/nf2ff/E_theta/FD/f<n>`, `/nf2ff/E_phi/FD/f<n>` complex (theta,phi) (legacy: `f<n>_real/_imag` (phi,theta)); `/nf2ff/P_rad/FD/f<n>`; attrs `Frequency`,`Prad`,`Dmax`,`Eps_r`,`Mue_r`. Python CalcNF2FF consumes 6 face pairs `<e_file>_<0..5>.h5`+`<h_file>_<0..5>.h5` (nf2ff.py:138-143).
C8 stats (openems.h:32-33; openems.cpp:1562-1618): `openEMS_stats.txt`: 6 lines `<value>\t% {number of cells,timestep (s),number of iterations,total numerical time (s),simulation time (s),speed (cells/s)}`, prec 16. `openEMS_run_stats.txt`: header `%time\ttimestep\tspeed\tenergy` + appended rows.
CSX input .xml/.csx (sibling evidence): root `<ContinuousStructure CoordSystem>` (ContinuousStructure.cpp:473), `<RectGrid DeltaUnit>` + `XLines/YLines/ZLines Qty=n` (CSRectGrid.cpp:325-347), properties Material/Metal/Excitation/ProbeBox/DumpBox/... (ContinuousStructure.cpp:554-565); DumpBox attrs DumpType/DumpMode/FileType/MultiGridLevel/SubSampling/OptResolution (CSPropDumpBox.cpp:123-160). openEMS FDTD xml = openEMS settings + embedded ContinuousStructure (`ParseFDTDSetup`, main.cpp:46).
Exit codes (main.cpp:32-56): -1 usage; 1 ParseFDTDSetup fail; SetupFDTD EC; 0 after RunFDTD even if end-criteria missed (only stderr warning) — gates must parse stdout verdict.

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row: PARTLY CORRECT)
Exists: `import CSXCAD` (ContinuousStructure, Write2XML — CSXCAD.pyx:164-267) + `from openEMS.openEMS import openEMS` (cdef class, openEMS.pyx:29; __init__.py:22). CORRECTION 1: audit's "update_openEMS.sh --python" is stale — no update script in this clone (only openEMS.sh, an LD_LIBRARY_PATH-clearing exec wrapper); install is CMake Cython extensions + venv per python/README.md and CSXCAD/python/README.md, docs https://docs.openems.de/en/latest/python/install.html (URL string verified in both READMEs); reqs doc cites scripts/install_deps.sh --python. CORRECTION 2: Touchstone is NOT emitted by the tool — sole repo hit is matlab/Tutorials/Patch_Antenna_Phased_Array.m:76-86 calling user-side `write_touchstone(...)` (no such .m ships in-tree); S-params are numpy ratios (`s11=port.uf_ref/port.uf_inc`, ports.py:186-248) exported downstream (docs TOC lists scikit-rf/SignalIntegrity/ParaView/Qucs-S post-processing). Native returns: `Run()` returns EC int only on setup path else None (openEMS.pyx:649-701) — solver yields files, not objects; readers return numpy: Port.CalcPort attrs `uf/if/ut/it_tot/inc/ref, P_inc/P_ref/P_acc, Z_ref`; `utilities.HDF5Dump` (h5py-backed, ROI/plane/sampling, IterFD/IterTD); `nf2ff_results` (theta/phi/r/freq/Dmax/Prad/E_theta/E_phi/E_norm/E_cprh/E_cplh/P_rad); `sar_utils.readSAR` -> (sar W/kg (nx,ny,nz), mesh metres, dict).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE: stdout welcome banner w/ version (openems.cpp:389-393); `[@<t>] Timestep: N || Speed: X MC/s (...) || Energy: ~E (-XdB)` / `|| SteadyState: X dB` every >4s wall (RunFDTD ~:1505-1533); `RunFDTD: end-criteria of -XdB reached after N timesteps` verdict (:1542) or stderr `Warning: Max. number of timesteps was reached before the end-criteria...` (:1538-1541); `Time for N iterations with M cells : T sec` + `Speed: X MCells/s` (:1547-1549); per-probe/dump setup lines (verbose). Stats subset is file-backed only with --dump-statistics (C8). WHY: verdict/energy/progress are computed in RunFDTD and printed, never written to result files; exit code stays 0 on criteria-miss, so the verdict line is the only machine signal.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (TOOL-OUTPUTS preference: bindings > structured files > deterministic text): (1) BINDINGS-READ: h5py via `HDF5Dump`/`nf2ff_results`/`readSAR` shapes + probe-file reader (`_load_ui_file`, `%`-comment grammar) — reuse shapes, keep execution subprocess. (2) STRUCTURED FILES (no heavy build): C1/C2 probe text (stable headers/columns), C3/C6/C7 HDF5 (check `openEMS_HDF5_version`, `legacy_fmt`, `d_order`), C8 stats. (3) TEXT RESIDUE ONLY: stdout end-criteria verdict + timing/speed regex; stderr warning taxonomy. Do NOT parse: progress Speed lines (wall-clock jitter), VTK (ParaView-oriented; HDF5 carries same data). Touchstone via scikit-rf from CalcPort outputs, not from tool. Verified at: openEMS 305df56a (2026-10-09), CSXCAD c46e3206 (2026-10-09), pins v0.37.0/v0.7.0, docs "openEMS 0.37.0" (/tmp/rocket-tool-docs/openems-index.html TOC: "Field Dump HDF5 File Format" reference; openems-reqs.html deps/install).

## Weak-evidence gaps (flagged by dissector)

- | C9 | Debug VTK + CSX XML | `--debug-material|--debug-PEC|--debug-operator|--debug-boxes|--debug-CSX` | `material_dump.vtk`,`PEC_dump.vtk`,`operator_dump.vtk`,`box_dump_*.vtk`,`debugCSX.xml` |
- 4. STDIO-ONLY RESIDUE: stdout welcome banner w/ version (openems.cpp:389-393); `[@<t>] Timestep: N || Speed: X MC/s (...) || Energy: ~E (-XdB)` / `|| SteadyState: X dB` every >4s wall (RunFDTD ~:1505-1533); `RunFDTD: end-criteria of -XdB reached after N timest
- | — | `lm_*` files | NONE FOUND (repo-wide grep empty); focus-hint "lm" = lumped-port `port_ut/it` files | — |
- Exists: `import CSXCAD` (ContinuousStructure, Write2XML — CSXCAD.pyx:164-267) + `from openEMS.openEMS import openEMS` (cdef class, openEMS.pyx:29; __init__.py:22). CORRECTION 1: audit's "update_openEMS.sh --python" is stale — no update script in this clone (on
- 5. ADAPTER RECOMMENDATION (TOOL-OUTPUTS preference: bindings > structured files > deterministic text): (1) BINDINGS-READ: h5py via `HDF5Dump`/`nf2ff_results`/`readSAR` shapes + probe-file reader (`_load_ui_file`, `%`-comment grammar) — reuse shapes, keep execu

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
openEMS output dissection (REVIEW ONLY)

IDENTITY: openEMS clone /tmp/rocket-tool-src/openems @ 305df56aa7df4d2f18c687083f484a96f9a22610, date 2026-10-09 (post-v0.37.0 master). CSXCAD clone @ c46e3206f20027b0b4605c797d07bddab76de942, 2026-10-09. Pin verified: provision_toolchain.sh:87-90 OPENEMS_REF=v0.37.0, CSXCAD_REF=v0.7.0; docs HTML title "openEMS 0.37.0 documentation". Evidence verified at master SHAs above (superset of v0.37.0).

1. RESULT CHANNELS (producing flag/command -> file pattern; all paths relative to CWD/sim_path)
| # | Channel | Producer | Pattern |
|---|---|---|---|
| C1 | Port/probe TD series (ext-less text) | `openEMS <xml>`; ProbeBox in CSX; names from python ports.py or user | `<ProbeName>` e.g. `port_ut_1`,`port_it_1`; MSL `port_ut_1{A,B,C}`,`port_it_1{A,B}`; multibox `<name>_<n>` |
| C2 | Port/probe FD companion (ext-less text) | same, when ProbeBox has FDSamples | `<ProbeName>_FD` |
| C3 | Field dump HDF5 | DumpBox FileType=1 (CSX attr) | `<DumpName>.h5` |
| C4 | Field dump VTK legacy | DumpBox FileType=0 | TD `<name>_<ts8>.vtk`; FD `<name>_f=<f>_p=<000..360>.vtk` x21 + `<name>_f=<f>_{abs,arg}.vtk` |
| C5 | Field dump VTK-XML | same writer, XML path | same basenames + writer default ext (.vtr/.vts) |
| C6 | nf2ff far-field HDF5 | `nf2ff <nf2ff-xml>` (outfile attr) or python CalcNF2FF (default `<name>.h5`) | user outfile, conventionally `*.h5` |
| C7 | SAR HDF5 | DumpBox type 20/21/22/29 | `<DumpName>.h5` (FD-shaped) |
| C8 | Run stats text | `openEMS --dump-statistics` | `openEMS_run_stats.txt`, `openEMS_stats.txt` (fixed names) |
| C9 | Debug VTK + CSX XML | `--debug-material|--debug-PEC|--debug-operator|--debug-boxes|--debug-CSX` | `material_dump.vtk`,`PEC_dump.vtk`,`operator_dump.vtk`,`box_dump_*.vtk`,`debugCSX.xml` |
| C10 | stdout / stderr streams | any run | progress, verdict, timing lines (see 4) |
| C11 | In-process returns | python post-readers only (never the solver) | numpy arrays / result objects (see 3) |
| — | Touchstone .sNp | NOT a tool output (see 3, correction) | — |
| — | `lm_*` files | NONE FOUND (repo-wide grep empty); focus-hint "lm" = lumped-port `port_ut/it` files | — |

2. FORMAT GRAMMARS
C1 probe TD (Common/processintegral.cpp:52-72,144-155; processing.cpp:77-82,240-250): filename IS probe name, no extension (`m_filename=m_Name`). Header: `% time-domain <proc> by openEMS <GIT_VERSION> @<ctime>`; `% start-coordinates: (x,y,z) m -> [i,j,k]`; `% stop-coordinates: ...`; `% t/s\t<col1>[\t<col2>]`. Rows: `<t>\t<v1>[\t<v2>]` (setprecision(m_precision), tab-sep, SI units). Column vocab: voltage probe `voltage` (V, processvoltage.cpp:30-35); current `current` (A, processcurrent.cpp:35-40); E-field probe `Ex/(V/m) Ey/(V/m) Ez/(V/m)`, H `Hx/(A/m)...` (processfieldprobe.cpp:41-62); modematch `voltage|current\tmode_purity` (processmodematch.cpp:48-60). Probe types 0/1/2/3/10/11 (openems.cpp:532-573). Port naming: `lbl_temp=prefix+'port_{}_{number}'` (ports.py:119); LumpedPort `port_ut_N`/`port_it_N` (ports.py:280-294); WaveguidePort same via p_type 10/11 (ports.py:589-601).
C2 probe FD (processintegral.cpp:92-132): `<name>_FD`, header `% frequency-domain ...`, `% f/Hz\t<name>\t...`, `%\treal\timag...`, rows `<f_Hz>\t<re>\t<im>...` (single-sided spectrum, x2 factor, :160-166).
C3/C7 field HDF5 (Common/processfields.cpp:129-166; tools/hdf5_file_writer.cpp/h): file `<name>.h5`. Root attrs: `openEMS_HDF5_version`=0.3 (double), `dump_type` (int, enum processfields.h:43: 0 E,1 H,2 J,3 rotH,4 D,5 B; FD file stores base type 0-5 while CSX DumpType is +10; 20 local SAR,21 1g,22 10g,29 raw), `dual_mesh` (bool), optional `legacy_fmt`. /Mesh: attrs `mesh_type` (0 cart/1 cyl/2 sph), `mesh_scaling` (=GridDelta, SI metres; alpha/theta/phi unscaled); datasets `x,y,z` | `rho,alpha,z` | `r,theta,phi`, float64 1-D (hdf5_file_writer.cpp:154-183; mirrored utilities.py:225-229). TD: `/FieldData/TD/<8-zero-padded ts>` vector float32 (3,Nx,Ny,Nz), attr `time` (processfields_td.cpp:67-74; pad default 8, processfields_td.h:35). FD: `/FieldData/FD/f<n>` complex64 vector + group attr `frequency` (Hz vector) (processfields_fd.cpp:178-190). Layout: new `d_order` attr `NXYZ`/`XYZ` x-inner; legacy `NZYX`/`ZYX` split `f<n>_real/_imag` float64 (writer :199-303; reader utilities.py:363-385, returns always (3,Nx,Ny,Nz) x-inner). Raw SAR adds `/CellData`,`/CellWidth` (sar_utils.py docstring).
C4 VTK (tools/vtk_file_writer.cpp:209-248; processfields_fd.cpp:117-173): legacy `.vtk` via VTK lib, header `openEMS {TD,FD} Field Dump -- Interpolation: ...`; TD one file per dumped ts; FD 21 phase files + abs + arg per frequency; freq rendered as int when integral (`:121-125`).
C6 nf2ff HDF5 (nf2ff/nf2ff.cpp:557-698; python nf2ff.py:159-230): /Mesh/{theta,phi,r} + `MeshType`=2; `/nf2ff/E_theta/FD/f<n>`, `/nf2ff/E_phi/FD/f<n>` complex (theta,phi) (legacy: `f<n>_real/_imag` (phi,theta)); `/nf2ff/P_rad/FD/f<n>`; attrs `Frequency`,`Prad`,`Dmax`,`Eps_r`,`Mue_r`. Python CalcNF2FF consumes 6 face pairs `<e_file>_<0..5>.h5`+`<h_file>_<0..5>.h5` (nf2ff.py:138-143).
C8 stats (openems.h:32-33; openems.cpp:1562-1618): `openEMS_stats.txt`: 6 lines `<value>\t% {number of cells,timestep (s),number of iterations,total numerical time (s),simulation time (s),speed (cells/s)}`, prec 16. `openEMS_run_stats.txt`: header `%time\ttimestep\tspeed\tenergy` + appended rows.
CSX input .xml/.csx (sibling evidence): root `<ContinuousStructure CoordSystem>` (ContinuousStructure.cpp:473), `<RectGrid DeltaUnit>` + `XLines/YLines/ZLines Qty=n` (CSRectGrid.cpp:325-347), properties Material/Metal/Excitation/ProbeBox/DumpBox/... (ContinuousStructure.cpp:554-565); DumpBox attrs DumpType/DumpMode/FileType/MultiGridLevel/SubSampling/OptResolution (CSPropDumpBox.cpp:123-160). openEMS FDTD xml = openEMS settings + embedded ContinuousStructure (`ParseFDTDSetup`, main.cpp:46).
Exit codes (main.cpp:32-56): -1 usage; 1 ParseFDTDSetup fail; SetupFDTD EC; 0 after RunFDTD even if end-criteria missed (only stderr warning) — gates must parse stdout verdict.

3. PYTHON BINDINGS (audit row: PARTLY CORRECT)
Exists: `import CSXCAD` (ContinuousStructure, Write2XML — CSXCAD.pyx:164-267) + `from openEMS.openEMS import openEMS` (cdef class, openEMS.pyx:29; __init__.py:22). CORRECTION 1: audit's "update_openEMS.sh --python" is stale — no update script in this clone (only openEMS.sh, an LD_LIBRARY_PATH-clearing exec wrapper); install is CMake Cython extensions + venv per python/README.md and CSXCAD/python/README.md, docs https://docs.openems.de/en/latest/python/install.html (URL string verified in both READMEs); reqs doc cites scripts/install_deps.sh --python. CORRECTION 2: Touchstone is NOT emitted by the tool — sole repo hit is matlab/Tutorials/Patch_Antenna_Phased_Array.m:76-86 calling user-side `write_touchstone(...)` (no such .m ships in-tree); S-params are numpy ratios (`s11=port.uf_ref/port.uf_inc`, ports.py:186-248) exported downstream (docs TOC lists scikit-rf/SignalIntegrity/ParaView/Qucs-S post-processing). Native returns: `Run()` returns EC int only on setup path else None (openEMS.pyx:649-701) — solver yields files, not objects; readers return numpy: Port.CalcPort attrs `uf/if/ut/it_tot/inc/ref, P_inc/P_ref/P_acc, Z_ref`; `utilities.HDF5Dump` (h5py-backed, ROI/plane/sampling, IterFD/IterTD); `nf2ff_results` (theta/phi/r/freq/Dmax/Prad/E_theta/E_phi/E_norm/E_cprh/E_cplh/P_rad); `sar_utils.readSAR` -> (sar W/kg (nx,ny,nz), mesh metres, dict).

4. STDIO-ONLY RESIDUE: stdout welcome banner w/ version (openems.cpp:389-393); `[@<t>] Timestep: N || Speed: X MC/s (...) || Energy: ~E (-XdB)` / `|| SteadyState: X dB` every >4s wall (RunFDTD ~:1505-1533); `RunFDTD: end-criteria of -XdB reached after N timesteps` verdict (:1542) or stderr `Warning: Max. number of timesteps was reached before the end-criteria...` (:1538-1541); `Time for N iterations with M cells : T sec` + `Speed: X MCells/s` (:1547-1549); per-probe/dump setup lines (verbose). Stats subset is file-backed only with --dump-statistics (C8). WHY: verdict/energy/progress are computed in RunFDTD and printed, never written to result files; exit code stays 0 on criteria-miss, so the verdict line is the only machine signal.

5. ADAPTER RECOMMENDATION (TOOL-OUTPUTS preference: bindings > structured files > deterministic text): (1) BINDINGS-READ: h5py via `HDF5Dump`/`nf2ff_results`/`readSAR` shapes + probe-file reader (`_load_ui_file`, `%`-comment grammar) — reuse shapes, keep execution subprocess. (2) STRUCTURED FILES (no heavy build): C1/C2 probe text (stable headers/columns), C3/C6/C7 HDF5 (check `openEMS_HDF5_version`, `legacy_fmt`, `d_order`), C8 stats. (3) TEXT RESIDUE ONLY: stdout end-criteria verdict + timing/speed regex; stderr warning taxonomy. Do NOT parse: progress Speed lines (wall-clock jitter), VTK (ParaView-oriented; HDF5 carries same data). Touchstone via scikit-rf from CalcPort outputs, not from tool. Verified at: openEMS 305df56a (2026-10-09), CSXCAD c46e3206 (2026-10-09), pins v0.37.0/v0.7.0, docs "openEMS 0.37.0" (/tmp/rocket-tool-docs/openems-index.html TOC: "Field Dump HDF5 File Format" reference; openems-reqs.html deps/install).
```
