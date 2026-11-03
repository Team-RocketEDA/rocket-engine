# elmerfem — output dissection

Dissector ref: prior result 13 (text `handoff-17815dd6d551e62b4566162440b9a2a00eb02235e2f6439a09b86f130ce1bd1d-d62684b151064a4b5d1f7dfedeb645afd7c8677b7ff740a68f33e892677d7784.txt`, summary `handoff-d61c6cc2ef261f8873177bd133772d2828cc3de433d2244040491733f6fee6f0-d62684b151064a4b5d1f7dfedeb645afd7c8677b7ff740a68f33e892677d7784.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `31f541c747376c2eebbac5ce171f77b4b3883683`
- Clone date: `2026-10-29`
- Pin: Pin/version: UNPINNED. `scripts/provision_toolchain.sh:92-93` pins only `ELMER_PPA="ppa:elmer-csc-ubuntu/elmer-csc-ppa"`, `ELMER_EXPECT="ElmerSolver"`; `check_elmer` (:521-547) accepts any ambient banner (`ambient-recorded`). All findings verified at the clone above.
- Doc/source URLs: none in header (see dissector header below)

### Dissector header (verbatim, whitespace-trimmed)

```text
ELMERFEM OUTPUT DISSECTION (review only, no edits)

Clone SHA: 31f541c747376c2eebbac5ce171f77b4b3883683, date 2026-10-29 (`git -C /tmp/rocket-tool-src/elmerfem rev-parse HEAD / log -1 --format=%cs`).
Pin/version: UNPINNED. `scripts/provision_toolchain.sh:92-93` pins only `ELMER_PPA="ppa:elmer-csc-ubuntu/elmer-csc-ppa"`, `ELMER_EXPECT="ElmerSolver"`; `check_elmer` (:521-547) accepts any ambient banner (`ambient-recorded`). All findings verified at the clone above.
Docs: /tmp/rocket-tool-docs/elmer-index.html is a CSC webinar page ("Elmer FEM free webinar series"), NOT tool docs — fell back to upstream web. Canonical docs: ElmerSolver Manual + ElmerModelsManual (Solver/ResultOutput/SaveScalars sections) via elmerfem.org; module doc-comments in-tree. Audit row (tool-bindings-audit.md:94): elmer_fem UNPINNED (PPA), no official bindings, pyelmer=SIF writer only, VTU via ResultOutputSolve, SaveScalars .dat, DEFER post_mvp-only.

Invocation: `ElmerSolver [case.sif]` (args parsed fem/src/Solver.F90:78-92), or no-arg mode reading `ELMERSOLVER_STARTINFO` (mesh dir + sif name; fem/src/ElmerSolver.F90:354-356). `ElmerGrid` for mesh conversion/partitioning (elmergrid/src/fempre.c:main). No whole-sif echo found; sif filename is recorded into SaveScalars .names/JSON only.
```

## 1. Result channels

1. RESULT CHANNELS (one table; paths relative to clone)

| # | Channel | Producing flag/command (sif section) | Filename pattern | Stream/format |
|---|---|---|---|---|
| 1 | Restart/result file | Simulation or Solver section `Output File = <name>` (+`Output File Each Timestep`, `Output File Cycle`, `Separate Results Files`); SaveCurrent ElmerSolver.F90:3776-3855 via SaveResult ModelDescription.F90:3815 | `<meshdir>/<name>`; parallel appends `.<PE>` (:3905 SaveToPost, :3899 SaveResult); EachTimestep appends `.<timestep>`; Cycle/Separate appends `_<i>nc`; sidecar `<name>.pos` | ASCII default, binary opt (`SaveResult ... Binary`) |
| 2a | VTU field export (DEFAULT) | Solver `Procedure="ResultOutputSolve" "ResultOutputSolver"`, `Output File Name=<prefix>` (default 'Case', :173-177; Vtu default 'Output' VtuOutputSolver.F90:407-409); `Vtu Format=True` or `Output Format=vtu`; default when no format given (:163-167) | `<prefix>[_<body/bc group>][_<PE>np<part>][_t<IIII>].vtu`; parallel wrapper `.pvtu`; `Vtu Time Collection` adds `<base>.pvd` index | VTK XML UnstructuredGrid, base64-binary default; `Ascii Output`, `Single Precision` opts (:353-393). Naming: VtuOutputSolver.F90:146-230 |
| 2b | VTK legacy | `Vtk Format=True` / `Output Format=vtk` | `<prefix><TTTT>.vtk`; eigen `<prefix><TTTT>_<jjj>.vtk` (VtkOutputSolver.F90:625-641) | VTK legacy ASCII |
| 2c | ElmerPost | `Elmerpost Format=True` | `<prefix>.ep` (ElmerPostOutputSolver.F90:82-86) | ElmerPost legacy |
| 2d | GiD | `Gid Format=True` | `<prefix>.flavia.res` + `<prefix>.flavia.msh` (GidOutputSolver.F90:125-132) | GiD post |
| 2e | OpenDX | `Dx Format=True` | `<prefix>Master.dx`, `<prefix><var>.dx`, `Mesh.dx` (DXOutputSolver.F90:54,150,156,240,334) | DX |
| 2f | Gmsh | `Gmsh Format=True` | .msh ("Saving in gmsh 2.0 (.msh) format" ResultOutputSolver.F90:323) | Gmsh 2.0 ASCII |
| 2g | STL | `Stl Format=True` (:105-111) | writer below :260, not inspected | STL |
| 3 | SaveScalars tables | Solver `Procedure="SaveData" "SaveScalars"`, `Filename=<f>` (SaveScalars.F90:43-3512; open logic :208-280) | `<f>` (whitespace table); `<f>.names` metadata; `<f>.csv` if `Live Graph`/`CVS Format`; `<f>.json` if `Json Format`; `FINISHED_MARKER_<n>` if `Mark Failed Strategy`; parallel `<f>.<PE>` unless `Parallel Reduce` | fixed-format text ES22.12E3/I10; JSON hand-rolled |
| 4 | SaveLine profiles | `Procedure="SaveData" "SaveLine"`, `Filename` default `sides.dat` (SaveLine.F90:129,177-178) | `<f>` (+`.<PE>` parallel, OpenLineFile :688-728) | label ints + ES20.11E3 (:925-930,1111-1116) |
| 5 | convergence.dat | Simulation `Convergence Monitor=True`, `Convergence Monitor File` default `convergence.dat` | `convergence.dat` (SolverBasics.F90:4249-4286, rank 0 only) | header + `(5I8,2G16.8)` rows |
| 6 | SaveMesh mesh dump | `Save Mesh=True`, `Mesh Name`, `Save Mesh Directory`, `Save All Timesteps` (SaveMesh.F90:41-115) | `<dir>/<name>[_<TTTT>]`; parallel `<dir>_<name>/partitioning.<P>/` | native mesh.header/nodes/elements/boundary |
| 7 | NetCDF particle/grid | SaveGridData `Filename Prefix` (SaveGridData.F90:722, ParticleOutputNetCDF :651-1200) | prefix-based .nc (not fully inspected) | NetCDF |
| 8 | ADIOS2/Fides | ADIOS2OutputSolver (ADIOS2OutputSolver.F90:255-423; MakeFidesJson :75) | .bp + fides JSON (names not inspected) | ADIOS2 |
| 9 | FourierLoss | `Fourier Loss Filename`, `Series Loss Filename` (FourierLoss.F90:1171,1187) | as given | text tables (row fmt not inspected) |
| 10 | In-memory Simulation vars | VolumeProbe (Probes.F90:171-176) writes `res: volume probe <name>`; SaveScalars re-exports every value + `Cost Function` (SaveScalars.F90:1541-1560) | none (consumed via `res:` prefix / FindOptimum) | Fortran list, no file/API |
| 11 | stdout log | always (InfoOutUnit=stdout, Messages.F90:67; `InfoToFile` can redirect) | — | banner, NS/SS iteration lines, echoes, warnings |
| 12 | stderr/exit | Fatal→`ERROR STOP 1`, FatalInput→`STOP 1` (Messages.F90:301-359; EXIT_ERROR=1 :71) | — | code 1 on fatal; 0 + `*** Elmer Solver: ALL DONE ***` (ElmerSolver.F90:773) on success |
| 13 | ElmerGrid outputs | `ElmerGrid <in> <out> <meshdir> [options]` (fempre.c) | mesh.header/nodes/elements/boundary (+.bin/.sbin variants; egnative.c:5075-5321), partitioning.<P> dirs | native mesh ASCII/binary |
| — | SaveBoundaryValues/SaveMaterials/SaveDependence/SaveProjection | present in fem/src/modules/SaveData/ | not inspected (bounded pass) | — |
| — | Databases / socket / Python API returns | NONE in clone | — | — |

## 2. Format grammars

2. FORMAT GRAMMARS (writer-verified; line refs are file:line in clone)

(a) Restart/result ASCII (ModelDescription.F90:3930-4262). Real example fem/tests/NonconformingRestart3/cube/case_b.dat:
```
 ASCII 3
!File started at: 2018/06/08 16:08:39
 Degrees of freedom:
tempb                    :      891     891   1 : heat equation
 Total DOFs:            1
 Number Of Nodes:          891
Time:       1      1  1.00000000E+000
tempb
Perm:          891          891
          1          1
 ... (2i11 pairs, only k>0)
<value per line, list-directed `WRITE(*,*) r`>
```
Grammar: header `!File started at: <date>`; `Degrees of freedom:`; per var `'<name>' : <nvals I8><permsize I8><dofs I4> : <equation>` (T25 if name<25 chars, :4001-4007); `Total DOFs:`, `Number Of Nodes:`; per step `Time: <saves I7><nTime I7><simtime ES17.8E3>`; per var: name line, `Perm: NULL`|`Perm: use previous`|`Perm: <size I12> <nonzero I12>` + `(2i11)` pairs, then one value/line. Binary variant: same logical records via BinWrite* + `.pos` index of int64 offsets.

(b) SaveScalars `<f>`: one row per call; optional `I10` line marker; ints `(I10)`, reals `(ES22.12E3)` non-advancing (:1385-1404), e.g. `  3.000000000000E+002  9.999950000000E-001`. `<f>.names`: `Metadata for SaveScalars file:`, `Elmer version/revision/compilation date:`, `Solver input file:`, `File started at:`, `Variables in columns of matrix:` + `(I4,": ",A)` (:1293-1355). `<f>.csv`: header names row, then `ES22.12E3,` rows (:1423-1443). `<f>.json`: `{"elmerver","elmerrev"?,"elmercompiled"?,"siffile"?,"starttime","columns":N,"names":[...],"values":[[...],...]}` (:1445-1519; appended via stream POS juggling — validate before trusting).
Sif use (fem/tests/ThermalBiMetal2/case.sif:98-104): `Equation = SaveScalars; Procedure = "SaveData" "SaveScalars"; Filename = "f.dat"; Variable 1 = Displacement 2; Operator 1 = max abs`.

(c) convergence.dat (SolverBasics.F90:4258-4284): header `! solver  ss/ns  timestep  coupled  nonlin  norm  change`; rows `(5I8,2G16.8)` = solverId, ss(1)/ns(0), timestep, coupledIter, nonlinIter, norm, change.

(d) VTU: root `<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">` (VtuOutputSolver.F90:793-795), `<UnstructuredGrid>` (:829), standard VTK XML Points/Cells/PointData/CellData + AppendedData (base64) in binary mode; `<VTKFile type="Collection"...><Collection>` for .pvd (:2233-2252). Readable by VTK/pyvista (pyvista already KEEP-BINDINGS per audit:113).

(e) VTK legacy: `<prefix><TTTT>.vtk` via WriteVtkLegacyFile (VtkOutputSolver.F90:638-641); standard `# vtk DataFile Version` ASCII (writer body not read — treat as VTK-legacy grammar).

(f) SaveLine: rows `[<int labels> ]<ES20.11E3>...` (:925-930 serial-reduce path :1111-1116); no header.

(g) stdout deterministic lines: `ELMER SOLVER (v <ver>) STARTED AT: <date>` (Solver.F90:70); per nonlinear/steady iteration `NS (ITER=<n>) (NRM,RELC): (<G15.8> <G15.8> ) :: <solver>` and `SS ...` at Level=3 (SolverBasics.F90:4145-4155); SaveScalars echo `(<I4>): <name><ES22.12E3>` when no Filename (:1525-1533); `SOLVER TOTAL TIME(CPU,REAL): <F12.2><F12.2>` + `ELMER SOLVER FINISHED AT: <date>` (Solver.F90:96-103); parallel prefixes `Part<n>:` (Messages.F90:149-172). Env `ELMERSOLVER_OUTPUT_TOTAL=0/false` silences banners (Solver.F90:63-64).

## 3. Python bindings verdict

3. PYTHON BINDINGS — audit row CONFIRMED with one correction. `find` over clone: no solver/results Python API (only FreeCAD pre/post workflow scripts under ElmerWorkflows/, elmerice example plot scripts, umfpack deps.py); zero f90wrap/forpy/CFFI/Python hooks in fem/src or modules. pyelmer (3rd-party, hansernhm/pyelmer, PyPI pyelmer) is sif-dict→`write_sif()` setup + gmsh preprocessing + ElmerGrid/ElmerSolver execution wrappers + "some post-processing routines" ([PyPI pyelmer](https://pypi.org/project/pyelmer/1.1.0/), [GitHub](https://github.com/hansernhm/pyelmer)) — i.e. slightly more than "SIF writer only", but NOT an official result-reading binding; nothing native returns results to Python. Execution stays subprocess regardless.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (no file equivalent found): linear-solver inner-iteration residuals/timings; `Warn` diagnostics; `Fatal` messages (exit 1); SaveScalars echo and `Info` solver traces when no file/Monitor flags set; VolumeProbe values unless harvested by SaveScalars (`res:`); timing breakdowns. NOT residue: nonlinear/steady norm+change (duplicated to convergence.dat via `Convergence Monitor`), all field data (VTU/VTK/...), all reductions (SaveScalars file modes), sif identity (.names/JSON).

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (ranked per TOOL-OUTPUTS: bindings > structured files > deterministic text):
1. SaveScalars `Json Format=True` — self-describing structured file (validate the hand-rolled writer once with a fixture).
2. SaveScalars `.dat` + `.names` (or `.csv` via `Live Graph`) — fixed Fortran formats, deterministic.
3. VTU (`Vtu Format`, default) read with pyvista/VTK — for fields/modes; prefer `Binary Output` default + `Single Precision` as needed.
4. `convergence.dat` (`Convergence Monitor=True`) — iteration history without log scraping.
5. Restart `Output File` ASCII — deterministic grammar above; writer-verified, needs a golden fixture.
6. stdout NS/SS + banner lines — last resort; formats quoted verbatim above (Level=3 must be enabled; MaxOutputLevel default 32).
Version evidence: all verified at clone 31f541c7 dated 2026-10-29; provision pin is PPA-only/ambient, so an adapter must record `ElmerSolver --version` banner + the sif keywords above in its fixture provenance. Gaps (bounded pass, named): STL/Gmsh/DX/ElmerPost/GiD payload grammars, SaveGridData .nc schema, ADIOS2 .bp names, SaveBoundaryValues/Materials/Dependence/Projection, Eigen/FFT side files — all writers located, row formats not read.

## Weak-evidence gaps (flagged by dissector)

- Version evidence: all verified at clone 31f541c7 dated 2026-10-29; provision pin is PPA-only/ambient, so an adapter must record `ElmerSolver --version` banner + the sif keywords above in its fixture provenance. Gaps (bounded pass, named): STL/Gmsh/DX/ElmerPost

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
ELMERFEM OUTPUT DISSECTION (review only, no edits)

Clone SHA: 31f541c747376c2eebbac5ce171f77b4b3883683, date 2026-10-29 (`git -C /tmp/rocket-tool-src/elmerfem rev-parse HEAD / log -1 --format=%cs`).
Pin/version: UNPINNED. `scripts/provision_toolchain.sh:92-93` pins only `ELMER_PPA="ppa:elmer-csc-ubuntu/elmer-csc-ppa"`, `ELMER_EXPECT="ElmerSolver"`; `check_elmer` (:521-547) accepts any ambient banner (`ambient-recorded`). All findings verified at the clone above.
Docs: /tmp/rocket-tool-docs/elmer-index.html is a CSC webinar page ("Elmer FEM free webinar series"), NOT tool docs — fell back to upstream web. Canonical docs: ElmerSolver Manual + ElmerModelsManual (Solver/ResultOutput/SaveScalars sections) via elmerfem.org; module doc-comments in-tree. Audit row (tool-bindings-audit.md:94): elmer_fem UNPINNED (PPA), no official bindings, pyelmer=SIF writer only, VTU via ResultOutputSolve, SaveScalars .dat, DEFER post_mvp-only.

Invocation: `ElmerSolver [case.sif]` (args parsed fem/src/Solver.F90:78-92), or no-arg mode reading `ELMERSOLVER_STARTINFO` (mesh dir + sif name; fem/src/ElmerSolver.F90:354-356). `ElmerGrid` for mesh conversion/partitioning (elmergrid/src/fempre.c:main). No whole-sif echo found; sif filename is recorded into SaveScalars .names/JSON only.

1. RESULT CHANNELS (one table; paths relative to clone)

| # | Channel | Producing flag/command (sif section) | Filename pattern | Stream/format |
|---|---|---|---|---|
| 1 | Restart/result file | Simulation or Solver section `Output File = <name>` (+`Output File Each Timestep`, `Output File Cycle`, `Separate Results Files`); SaveCurrent ElmerSolver.F90:3776-3855 via SaveResult ModelDescription.F90:3815 | `<meshdir>/<name>`; parallel appends `.<PE>` (:3905 SaveToPost, :3899 SaveResult); EachTimestep appends `.<timestep>`; Cycle/Separate appends `_<i>nc`; sidecar `<name>.pos` | ASCII default, binary opt (`SaveResult ... Binary`) |
| 2a | VTU field export (DEFAULT) | Solver `Procedure="ResultOutputSolve" "ResultOutputSolver"`, `Output File Name=<prefix>` (default 'Case', :173-177; Vtu default 'Output' VtuOutputSolver.F90:407-409); `Vtu Format=True` or `Output Format=vtu`; default when no format given (:163-167) | `<prefix>[_<body/bc group>][_<PE>np<part>][_t<IIII>].vtu`; parallel wrapper `.pvtu`; `Vtu Time Collection` adds `<base>.pvd` index | VTK XML UnstructuredGrid, base64-binary default; `Ascii Output`, `Single Precision` opts (:353-393). Naming: VtuOutputSolver.F90:146-230 |
| 2b | VTK legacy | `Vtk Format=True` / `Output Format=vtk` | `<prefix><TTTT>.vtk`; eigen `<prefix><TTTT>_<jjj>.vtk` (VtkOutputSolver.F90:625-641) | VTK legacy ASCII |
| 2c | ElmerPost | `Elmerpost Format=True` | `<prefix>.ep` (ElmerPostOutputSolver.F90:82-86) | ElmerPost legacy |
| 2d | GiD | `Gid Format=True` | `<prefix>.flavia.res` + `<prefix>.flavia.msh` (GidOutputSolver.F90:125-132) | GiD post |
| 2e | OpenDX | `Dx Format=True` | `<prefix>Master.dx`, `<prefix><var>.dx`, `Mesh.dx` (DXOutputSolver.F90:54,150,156,240,334) | DX |
| 2f | Gmsh | `Gmsh Format=True` | .msh ("Saving in gmsh 2.0 (.msh) format" ResultOutputSolver.F90:323) | Gmsh 2.0 ASCII |
| 2g | STL | `Stl Format=True` (:105-111) | writer below :260, not inspected | STL |
| 3 | SaveScalars tables | Solver `Procedure="SaveData" "SaveScalars"`, `Filename=<f>` (SaveScalars.F90:43-3512; open logic :208-280) | `<f>` (whitespace table); `<f>.names` metadata; `<f>.csv` if `Live Graph`/`CVS Format`; `<f>.json` if `Json Format`; `FINISHED_MARKER_<n>` if `Mark Failed Strategy`; parallel `<f>.<PE>` unless `Parallel Reduce` | fixed-format text ES22.12E3/I10; JSON hand-rolled |
| 4 | SaveLine profiles | `Procedure="SaveData" "SaveLine"`, `Filename` default `sides.dat` (SaveLine.F90:129,177-178) | `<f>` (+`.<PE>` parallel, OpenLineFile :688-728) | label ints + ES20.11E3 (:925-930,1111-1116) |
| 5 | convergence.dat | Simulation `Convergence Monitor=True`, `Convergence Monitor File` default `convergence.dat` | `convergence.dat` (SolverBasics.F90:4249-4286, rank 0 only) | header + `(5I8,2G16.8)` rows |
| 6 | SaveMesh mesh dump | `Save Mesh=True`, `Mesh Name`, `Save Mesh Directory`, `Save All Timesteps` (SaveMesh.F90:41-115) | `<dir>/<name>[_<TTTT>]`; parallel `<dir>_<name>/partitioning.<P>/` | native mesh.header/nodes/elements/boundary |
| 7 | NetCDF particle/grid | SaveGridData `Filename Prefix` (SaveGridData.F90:722, ParticleOutputNetCDF :651-1200) | prefix-based .nc (not fully inspected) | NetCDF |
| 8 | ADIOS2/Fides | ADIOS2OutputSolver (ADIOS2OutputSolver.F90:255-423; MakeFidesJson :75) | .bp + fides JSON (names not inspected) | ADIOS2 |
| 9 | FourierLoss | `Fourier Loss Filename`, `Series Loss Filename` (FourierLoss.F90:1171,1187) | as given | text tables (row fmt not inspected) |
| 10 | In-memory Simulation vars | VolumeProbe (Probes.F90:171-176) writes `res: volume probe <name>`; SaveScalars re-exports every value + `Cost Function` (SaveScalars.F90:1541-1560) | none (consumed via `res:` prefix / FindOptimum) | Fortran list, no file/API |
| 11 | stdout log | always (InfoOutUnit=stdout, Messages.F90:67; `InfoToFile` can redirect) | — | banner, NS/SS iteration lines, echoes, warnings |
| 12 | stderr/exit | Fatal→`ERROR STOP 1`, FatalInput→`STOP 1` (Messages.F90:301-359; EXIT_ERROR=1 :71) | — | code 1 on fatal; 0 + `*** Elmer Solver: ALL DONE ***` (ElmerSolver.F90:773) on success |
| 13 | ElmerGrid outputs | `ElmerGrid <in> <out> <meshdir> [options]` (fempre.c) | mesh.header/nodes/elements/boundary (+.bin/.sbin variants; egnative.c:5075-5321), partitioning.<P> dirs | native mesh ASCII/binary |
| — | SaveBoundaryValues/SaveMaterials/SaveDependence/SaveProjection | present in fem/src/modules/SaveData/ | not inspected (bounded pass) | — |
| — | Databases / socket / Python API returns | NONE in clone | — | — |

2. FORMAT GRAMMARS (writer-verified; line refs are file:line in clone)

(a) Restart/result ASCII (ModelDescription.F90:3930-4262). Real example fem/tests/NonconformingRestart3/cube/case_b.dat:
```
 ASCII 3
!File started at: 2018/06/08 16:08:39
 Degrees of freedom:
tempb                    :      891     891   1 : heat equation
 Total DOFs:            1
 Number Of Nodes:          891
Time:       1      1  1.00000000E+000
tempb
Perm:          891          891
          1          1
 ... (2i11 pairs, only k>0)
<value per line, list-directed `WRITE(*,*) r`>
```
Grammar: header `!File started at: <date>`; `Degrees of freedom:`; per var `'<name>' : <nvals I8><permsize I8><dofs I4> : <equation>` (T25 if name<25 chars, :4001-4007); `Total DOFs:`, `Number Of Nodes:`; per step `Time: <saves I7><nTime I7><simtime ES17.8E3>`; per var: name line, `Perm: NULL`|`Perm: use previous`|`Perm: <size I12> <nonzero I12>` + `(2i11)` pairs, then one value/line. Binary variant: same logical records via BinWrite* + `.pos` index of int64 offsets.

(b) SaveScalars `<f>`: one row per call; optional `I10` line marker; ints `(I10)`, reals `(ES22.12E3)` non-advancing (:1385-1404), e.g. `  3.000000000000E+002  9.999950000000E-001`. `<f>.names`: `Metadata for SaveScalars file:`, `Elmer version/revision/compilation date:`, `Solver input file:`, `File started at:`, `Variables in columns of matrix:` + `(I4,": ",A)` (:1293-1355). `<f>.csv`: header names row, then `ES22.12E3,` rows (:1423-1443). `<f>.json`: `{"elmerver","elmerrev"?,"elmercompiled"?,"siffile"?,"starttime","columns":N,"names":[...],"values":[[...],...]}` (:1445-1519; appended via stream POS juggling — validate before trusting).
Sif use (fem/tests/ThermalBiMetal2/case.sif:98-104): `Equation = SaveScalars; Procedure = "SaveData" "SaveScalars"; Filename = "f.dat"; Variable 1 = Displacement 2; Operator 1 = max abs`.

(c) convergence.dat (SolverBasics.F90:4258-4284): header `! solver  ss/ns  timestep  coupled  nonlin  norm  change`; rows `(5I8,2G16.8)` = solverId, ss(1)/ns(0), timestep, coupledIter, nonlinIter, norm, change.

(d) VTU: root `<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">` (VtuOutputSolver.F90:793-795), `<UnstructuredGrid>` (:829), standard VTK XML Points/Cells/PointData/CellData + AppendedData (base64) in binary mode; `<VTKFile type="Collection"...><Collection>` for .pvd (:2233-2252). Readable by VTK/pyvista (pyvista already KEEP-BINDINGS per audit:113).

(e) VTK legacy: `<prefix><TTTT>.vtk` via WriteVtkLegacyFile (VtkOutputSolver.F90:638-641); standard `# vtk DataFile Version` ASCII (writer body not read — treat as VTK-legacy grammar).

(f) SaveLine: rows `[<int labels> ]<ES20.11E3>...` (:925-930 serial-reduce path :1111-1116); no header.

(g) stdout deterministic lines: `ELMER SOLVER (v <ver>) STARTED AT: <date>` (Solver.F90:70); per nonlinear/steady iteration `NS (ITER=<n>) (NRM,RELC): (<G15.8> <G15.8> ) :: <solver>` and `SS ...` at Level=3 (SolverBasics.F90:4145-4155); SaveScalars echo `(<I4>): <name><ES22.12E3>` when no Filename (:1525-1533); `SOLVER TOTAL TIME(CPU,REAL): <F12.2><F12.2>` + `ELMER SOLVER FINISHED AT: <date>` (Solver.F90:96-103); parallel prefixes `Part<n>:` (Messages.F90:149-172). Env `ELMERSOLVER_OUTPUT_TOTAL=0/false` silences banners (Solver.F90:63-64).

3. PYTHON BINDINGS — audit row CONFIRMED with one correction. `find` over clone: no solver/results Python API (only FreeCAD pre/post workflow scripts under ElmerWorkflows/, elmerice example plot scripts, umfpack deps.py); zero f90wrap/forpy/CFFI/Python hooks in fem/src or modules. pyelmer (3rd-party, hansernhm/pyelmer, PyPI pyelmer) is sif-dict→`write_sif()` setup + gmsh preprocessing + ElmerGrid/ElmerSolver execution wrappers + "some post-processing routines" ([PyPI pyelmer](https://pypi.org/project/pyelmer/1.1.0/), [GitHub](https://github.com/hansernhm/pyelmer)) — i.e. slightly more than "SIF writer only", but NOT an official result-reading binding; nothing native returns results to Python. Execution stays subprocess regardless.

4. STDIO-ONLY RESIDUE (no file equivalent found): linear-solver inner-iteration residuals/timings; `Warn` diagnostics; `Fatal` messages (exit 1); SaveScalars echo and `Info` solver traces when no file/Monitor flags set; VolumeProbe values unless harvested by SaveScalars (`res:`); timing breakdowns. NOT residue: nonlinear/steady norm+change (duplicated to convergence.dat via `Convergence Monitor`), all field data (VTU/VTK/...), all reductions (SaveScalars file modes), sif identity (.names/JSON).

5. ADAPTER RECOMMENDATION (ranked per TOOL-OUTPUTS: bindings > structured files > deterministic text):
1. SaveScalars `Json Format=True` — self-describing structured file (validate the hand-rolled writer once with a fixture).
2. SaveScalars `.dat` + `.names` (or `.csv` via `Live Graph`) — fixed Fortran formats, deterministic.
3. VTU (`Vtu Format`, default) read with pyvista/VTK — for fields/modes; prefer `Binary Output` default + `Single Precision` as needed.
4. `convergence.dat` (`Convergence Monitor=True`) — iteration history without log scraping.
5. Restart `Output File` ASCII — deterministic grammar above; writer-verified, needs a golden fixture.
6. stdout NS/SS + banner lines — last resort; formats quoted verbatim above (Level=3 must be enabled; MaxOutputLevel default 32).
Version evidence: all verified at clone 31f541c7 dated 2026-10-29; provision pin is PPA-only/ambient, so an adapter must record `ElmerSolver --version` banner + the sif keywords above in its fixture provenance. Gaps (bounded pass, named): STL/Gmsh/DX/ElmerPost/GiD payload grammars, SaveGridData .nc schema, ADIOS2 .bp names, SaveBoundaryValues/Materials/Dependence/Projection, Eigen/FFT side files — all writers located, row formats not read.
```
