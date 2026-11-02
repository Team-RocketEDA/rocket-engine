# palace — output dissection

Dissector ref: prior result 11 (text `handoff-25d74ee6de74d71bc168f2687f60ce5000ef94f9a033fd5bd48a078c317e99fc-f558b9fc748a339462ec820a8de5962a95906a2a55a7e34cd5b0c23f9e7cb8dc.txt`, summary `handoff-b19f43a5c3845ad2a13293eae3fffdd73d0ebd7cb9ada2e0a86fbbbf40244664-f558b9fc748a339462ec820a8de5962a95906a2a55a7e34cd5b0c23f9e7cb8dc.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `8874e6cf8f3c6111867cb0c01cb7efacd73fd48c`
- Clone date: `2026-10-30`
- Pin: - Pin/version: UNSOURCED, no pin (scripts/provision_toolchain.sh:95; audit row). All evidence verified at the clone SHA above.
- Doc/source URLs:
  - https://awslabs.github.io/palace/stable/
  - https://github.com/awslabs/palace

### Dissector header (verbatim, whitespace-trimmed)

```text
PALACE output-capability dissection (REVIEW ONLY, no edits)

PROVENANCE
- Clone: /tmp/rocket-tool-src/palace/ @ 8874e6cf8f3c6111867cb0c01cb7efacd73fd48c, date 2026-10-30. Remote: https://github.com/awslabs/palace
- DOCS HTML /tmp/rocket-tool-docs/palace-index.html = 2-line Documenter.jl redirect stub (missing) → fell back to in-repo docs/ (docs/src/guide/postprocessing.md, docs/src/run.md, docs/src/config/) + upstream https://awslabs.github.io/palace/stable/ (unverified render; content grounded in repo files below).
- Pin/version: UNSOURCED, no pin (scripts/provision_toolchain.sh:95; audit row). All evidence verified at the clone SHA above.
- Audit-row check (tool-bindings-audit.md:86): CONFIRMED "NONE official (C++ binary, JSON config)" + DEFER, but "structured escapes" cell needs correction: there is NO Touchstone writer (port-S.csv is mag-dB/phase-deg CSV, not .sNp); palace.json is run metadata only (no S-params); VTU confirmed; plus many more CSVs, MFEM .gf gridfunctions, and a _resolved.json sidecar (see §1).

CLI: `palace [OPTIONS] CONFIG_FILE` (palace/main.cpp:183-194); `-h/--help, --version, -dry-run/--dry-run` (dry-run prints resolved config JSON to stdout, main.cpp:224-236). Run under MPI launcher; binary name `palace-<ARCH>.bin` (docs/src/run.md). All file results land under `config["Problem"]["Output"]`, default `postpro/` (palace/utils/configfile.hpp:60-66; schema scripts/schema/config-schema.json).
```

## 1. Result channels

1. RESULT CHANNELS (one table; <OUT> = Problem.Output)

| # | Channel | Producing flag / call site | Filename pattern (under <OUT>/) | Content |
|---|---|---|---|---|
| F1 | CSV tables (always; root rank only) | any solve; `WriteTable/WriteFullTableTrunc` (palace/utils/tablecsv.hpp:163-189) | `domain-E.csv`, `surface-F.csv`, `surface-Q.csv`, `surface-I.csv`, `port-V.csv`, `port-I.csv`, `port-S.csv`, `port-Z.csv` (only if wave-port voltage coords, postoperatorcsv.cpp:1268), `port-floquet-S.csv`, `probe-E/-En/-Bt/-B.csv`, `farfield-rE.csv`, `eig.csv`, `port-EPR.csv`, `port-Q.csv`, `mode-kn/-Z/-V.csv`, `error-indicators.csv`, `terminal-C/-Cinv/-Cm/-V.csv` (electrostatic, electrostaticsolver.cpp:175-181), `terminal-M/-Minv/-Mm/-I/-Phi.csv` (magnetostatic, magnetostaticsolver.cpp:560,939-947), `rom-*.csv` (adaptive/PROM driven only, romoperator.cpp:2890-3314) | §2 |
| F2 | Run metadata JSON (always; root; atomic via .tmp+rename) | `BaseSolver::SaveMetadata*` (palace/drivers/basesolver.cpp:117-135,184-199,386-520) | `palace.json` | GitTag, Problem{MPISize,OpenMPThreads,MeshElements,DegreesOfFreedom,MultigridDegreesOfFreedom,Iteration}, SavedAdaptedMesh{Dimension,TrueVertices,TrueEdges,TrueFaces?,Cells,DomainAttributes,BoundaryAttributes}, LinearSolver{TotalSolves,TotalIts}, ElapsedTime{Durations,Counts}, PeakMemoryGrowthMegabytes/Min/Max/Sum, PeakNodeMemory…, PeakMemoryMegabytes{Min,Max,Average,Total}, Excitations{} |
| F3 | Resolved-config JSON (always; world root) | `WriteResolvedConfig` (palace/utils/iodata.hpp:65-72; main.cpp:248-251) | `<input_stem>_resolved.json` (e.g. `cavity_resolved.json`) | Input config + all defaults concretized; schema-valid, re-runnable (docs/src/guide/postprocessing.md "Resolved configuration record") |
| F4 | ParaView/VTK (DEFAULT ON) | `Problem.OutputFormats.Paraview=true` (configfile.cpp:218; configfile.hpp:51) | `paraview/<solver>/Cycle%06d/data.pvtu` + per-rank `.vtu`; `paraview/<solver>_boundary/...` for boundary mesh (postoperator.cpp:764-775). `<solver>` = driven|eigenmode|electrostatic|magnetostatic|transient|boundarymode (postoperator.cpp:76-94). Confirmed by example path `postpro/thick_impedance/paraview/boundarymode/Cycle000002/data.pvtu` (examples/cpw2d/plot_cpw2d_docs.py:22-24) | §2 |
| F5 | MFEM gridfunction / GLVis (opt-in) | `OutputFormats.GridFunction=true` (default false, configfile.hpp:54) | `gridfunction/<solver>/<Field>_<step %06d>.gf.<rank %06d>` (postoperator.cpp:1373-1377; docs postprocessing.md) | E/E_real/E_imag, En*, B*, Bt_real/imag, V, A, U_e, U_m, S, Sn (postoperator.cpp:1385-1505), MFEM `GridFunction::Save` ASCII |
| F6 | Adapted mesh (opt-in) | Model.Refinement save-adapted-mesh flag (palace/utils/geodata.cpp:2715-2727) | `<mesh_stem>.mesh` (or `.meshgz` if MFEM+zlib) | Serial MFEM mesh of final AMR state |
| F7 | AMR iteration archives (AMR only, max_it>0) | `SaveIteration` (basesolver.hpp:86-93; basesolver.cpp:30-110) | `iterationXX/<moved outputs>` + relative symlinks left behind; palace.json copied (not moved); `Problem.Iteration` = 1-based index | Per-iteration snapshots |
| S1 | stdout/stderr (no log file; docs advise `…| tee log.out`, docs/src/run.md:28-33) | `Mpi::Print` everywhere; final `BlockTimer::Print` (palace/driver.cpp:89) | stream only | §4 |
| A1 | In-process API | `palace::Run(iodata,…)` (palace/driver.hpp, main.cpp:260) reused by Catch2 regression harness (test/unit/regression/) | n/a | test-only driver entry; NOT a results API. No databases, no sockets. |

## 2. Format grammars

2. FORMAT GRAMMARS
CSV engine (palace/utils/tablecsv.{hpp,cpp}): col sep `,`, row sep `\n` (tablecsv.hpp:104-105); header row = human `header_text` with units in parens — NOT stable IDs, parse by position; floats `{:+.{prec}e}` e.g. `+2.000000000e+00` (tablecsv.cpp:57-64); default prec 12 (tablecsv.hpp:22); index-col prec 8 for f/t, 2 for m/i (postoperatorcsv.cpp:344-358); missing cell `NULL` (hpp:26); evanescent Floquet_S pads `NaN` (postoperatorcsv.cpp:1446-1459). Real example from test/unit/test-tablecsv.cpp:101-107:
```
            Header Col 1,            Header Col 2,            Header Col 3
                    NULL,        +2.000000000e+00,        +3.000000000e+00
                    NULL,                    NULL,        +6.000000000e+00
```
Units: SI, dimensionalized at write (postoperatorcsv.cpp:26-150); index col per solver: driven `f (GHz)`, transient `t (ns)`, eigen/boundarymode `m`, electro/magnetostatic `i` (LabelIndexCol, postoperatorcsv.cpp:326-342). S conversions: mag = 20·log10|S| dB, phase = arg° (postoperatorcsv.hpp:221-226).
Per-file columns (headers verbatim):
- domain-E.csv: `E_elec/E_mag/E_cap/E_ind (J)` + per-domain `E_elec[i]/p_elec[i]/E_mag[i]/p_mag[i]` (postoperatorcsv.cpp:571-600).
- port-V/I.csv: `V_inc[i]/I_inc[i]`, `Re/Im{V[i]} (V)`, `Re/Im{I[i]} (A)` (+`V_wp` for wave ports w/ voltage coords); complex peak phasors (postoperatorcsv.cpp:1063-1130; docs).
- port-S.csv (DRIVEN, multi-simple excitations only): `|S[o][e]| (dB)`, `arg(S[o][e]) (deg.)` per obs/exc port pair — NOT Touchstone (postoperatorcsv.cpp:1217-1232).
- port-Z.csv: `Re/Im{Z_PV[i]}`, `Re/Im{Z[i][e]} (Ohm)` (postoperatorcsv.cpp:1283-1325).
- port-floquet-S.csv: `|S[Pp(m,n)POL][exc]|/arg` per order/pol (TE/TM or RHC/LHC) (postoperatorcsv.cpp:1330-1400).
- eig.csv: `m, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)` (postoperatorcsv.cpp:1470-1477). port-EPR.csv: `p[i]`; port-Q.csv: `Q_ext[i], κ_ext[i] (GHz)` (:1510-1555).
- mode-kn.csv: `m, Re/Im{kn} (1/m), Re/Im{n_eff}, errors`; mode-Z.csv: `Z_PV/L_PV/C_PV (+Z_VI/L_VI/C_VI)`; mode-V.csv: `Re/Im{V[i]} (V)` (:1581-1680).
- probe-E.csv `Re/Im{E_x/y/z[probe][exc]} (V/m)` (scalar probes drop _x; static solvers real-only); probe-En (V/m), probe-Bt (T), probe-B (Wb/m²) (:852-983).
- surface-F.csv: `Re/Im{Φ_elec} (C)`, `Φ_mag (Wb)`, `Φ_pow (W)` (:645-700). surface-Q.csv: `p_surf[i], Q_surf[i]` (:725-741). surface-I.csv: `I_inc[i] (A)` (:1002-1016). farfield-rE.csv: driven `f,exc,theta,phi,r*Re/Im{E_x,y,z} (V)`; eigenmode adds m,f_re,f_im (:773-810). error-indicators.csv: single row `Norm,Minimum,Maximum,Mean` (:1706-1719).
- terminal-C/-Cinv/-Cm.csv: `i, C[i][attr] (F)` etc. (electrostaticsolver.cpp:153-177); terminal-V.csv: `V_inc[i] (V)`; terminal-M/-Minv/-Mm (H), terminal-I.csv `I_inc[i] (A)`; terminal-Phi.csv has TWO schemas on different paths: energy+`Phi_inc[loop] (Wb)` (:560-578) vs excitation list `Phi_inc[i] (Wb)` (:962-975) — same filename, check columns.
- rom-*.csv (drivensolver.cpp:397; romoperator.cpp): `rom-port-reference.csv` (f, Re/Im Y_ref S, Z_ref Ω, prec 17), `rom-coupled-S.csv` (f, Re/Im per S key), `rom-coupled-G/H.csv`, `rom-Linv/C/Rinv-re/im.csv` (+`<load>-*` variants, if nonzero), `rom-orthogonalization-matrix-R.csv`, `rom-eigenvalues.csv` (Re/Im f GHz,Q,errors — same convention as eig.csv), `rom-eigenvectors-re/im.csv`.
ParaView: raw-appended binary VTK XML, BINARY32, compression 0, high-order + levels-of-detail (postoperator.cpp:776-806; docs: needs ParaView ≥5.12.1). Domain fields: E(_real/_imag) V/m, B* Wb/m², En*, Bt_real/imag, V (V), A (A), U_e/U_m (J/m³), S (W/m²), Sn; boundary adds Q_s* (C/m²), J_s* (A/m), E0_<idx>_real/imag (V/m) (postoperator.cpp:899-1117; docs). Final extra cycle: cell fields `Rank` (1-based), `Indicator`, at sentinel time 99/999… (postoperator.cpp:1273-1311). Cycle index = step/mode/freq/source ordinal; driven time attr = f_Hz (postoperator.cpp:1235-1247).
palace.json: nlohmann json, `dump(2)` + \n (basesolver.cpp:127-135). Schema = keys in §1/F2; no formal schema file for outputs (scripts/schema/config-schema.json covers INPUT config only, incl. Problem{Type,Verbose,Output,OutputFormats{Paraview,GridFunction}}).

## 3. Python bindings verdict

3. PYTHON BINDINGS: NONE. Zero pybind/nanobind/C-API in palace/ or CMake (only .py in repo: examples/*/plot_*_docs.py ParaView/pvpython post-hoc readers, .github CI scripts). Audit "NONE official" CONFIRMED. Closest machine readers: CSV (pandas), palace.json (json), VTU (pyvista/VTK), .gf (no Python reader in repo).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (results on stdout NOT in files, or only at reduced precision):
- Eigenmode/freq summaries are MIRRORED, not residue: eig table printed per mode at prec 6 (`m, Re/Im f, Q, errors`, postoperator.cpp:2361-2379) vs prec 12 in eig.csv; S lines `S[i][j] = re+imi, |S|, arg` (%.3e, :1947-1989) vs port-S.csv mag/phase; boundarymode `eig i: kn, n_eff` (boundarymodesolver.cpp:484) vs mode-kn.csv; ROM estimates `f, Q, bkwd error` (romoperator.cpp:3316-322) vs rom-eigenvalues.csv.
- TRUE residue: solver/convergence chatter (ARPACK/SLEPc config, shift σ, `Found N converged eigenvalues (first=…)`, greedy ω*/error, `Sol. ||E||`, error-estimate notes); `Elapsed Time Report (s)` + `Peak Memory` tables (timer.hpp:383-404) — same numbers ARE in palace.json but the formatted table is stdout-only; `Wrote … to disk (Paraview|grid function)` markers (:2121-2129); warnings/errors (MFEM_ABORT/Mpi::Warning, e.g. AMR halt, non-convergence early-return leaves palace.json at last converged — magnetostaticsolver.cpp:498); banner/version (`--version`, PrintPalaceVersion). Exit-code semantics not enumerated in scope.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference bindings > structured files > deterministic text):
No bindings exist → ranked file paths: (1) CSV tables — primary (pandas-parseable; stable Table writer; headers carry units; parse positionally); port-S.csv needs mag/phase→complex conversion for Touchstone-equivalent use. (2) palace.json — run metadata/timings/memory/DOFs (do NOT look for S-params here). (3) <stem>_resolved.json — exact input record for provenance. (4) VTU/PVTU via pyvista/VTK for fields (BINARY32 raw-appended; ParaView ≥5.12.1). (5) .gf only if GLVis embedding needed. Avoid stdout scraping — all numeric results are in files at equal/higher precision; stdout adds only convergence diagnostics. Pin/version evidence: UNSOURCED, verified at 8874e6cf8f3c6111867cb0c01cb7efacd73fd48c (2026-10-30); doc grounding docs/src/guide/postprocessing.md + docs/src/run.md + scripts/schema/config-schema.json.

## Weak-evidence gaps (flagged by dissector)

- No bindings exist → ranked file paths: (1) CSV tables — primary (pandas-parseable; stable Table writer; headers carry units; parse positionally); port-S.csv needs mag/phase→complex conversion for Touchstone-equivalent use. (2) palace.json — run metadata/timing

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
PALACE output-capability dissection (REVIEW ONLY, no edits)

PROVENANCE
- Clone: /tmp/rocket-tool-src/palace/ @ 8874e6cf8f3c6111867cb0c01cb7efacd73fd48c, date 2026-10-30. Remote: https://github.com/awslabs/palace
- DOCS HTML /tmp/rocket-tool-docs/palace-index.html = 2-line Documenter.jl redirect stub (missing) → fell back to in-repo docs/ (docs/src/guide/postprocessing.md, docs/src/run.md, docs/src/config/) + upstream https://awslabs.github.io/palace/stable/ (unverified render; content grounded in repo files below).
- Pin/version: UNSOURCED, no pin (scripts/provision_toolchain.sh:95; audit row). All evidence verified at the clone SHA above.
- Audit-row check (tool-bindings-audit.md:86): CONFIRMED "NONE official (C++ binary, JSON config)" + DEFER, but "structured escapes" cell needs correction: there is NO Touchstone writer (port-S.csv is mag-dB/phase-deg CSV, not .sNp); palace.json is run metadata only (no S-params); VTU confirmed; plus many more CSVs, MFEM .gf gridfunctions, and a _resolved.json sidecar (see §1).

CLI: `palace [OPTIONS] CONFIG_FILE` (palace/main.cpp:183-194); `-h/--help, --version, -dry-run/--dry-run` (dry-run prints resolved config JSON to stdout, main.cpp:224-236). Run under MPI launcher; binary name `palace-<ARCH>.bin` (docs/src/run.md). All file results land under `config["Problem"]["Output"]`, default `postpro/` (palace/utils/configfile.hpp:60-66; schema scripts/schema/config-schema.json).

1. RESULT CHANNELS (one table; <OUT> = Problem.Output)

| # | Channel | Producing flag / call site | Filename pattern (under <OUT>/) | Content |
|---|---|---|---|---|
| F1 | CSV tables (always; root rank only) | any solve; `WriteTable/WriteFullTableTrunc` (palace/utils/tablecsv.hpp:163-189) | `domain-E.csv`, `surface-F.csv`, `surface-Q.csv`, `surface-I.csv`, `port-V.csv`, `port-I.csv`, `port-S.csv`, `port-Z.csv` (only if wave-port voltage coords, postoperatorcsv.cpp:1268), `port-floquet-S.csv`, `probe-E/-En/-Bt/-B.csv`, `farfield-rE.csv`, `eig.csv`, `port-EPR.csv`, `port-Q.csv`, `mode-kn/-Z/-V.csv`, `error-indicators.csv`, `terminal-C/-Cinv/-Cm/-V.csv` (electrostatic, electrostaticsolver.cpp:175-181), `terminal-M/-Minv/-Mm/-I/-Phi.csv` (magnetostatic, magnetostaticsolver.cpp:560,939-947), `rom-*.csv` (adaptive/PROM driven only, romoperator.cpp:2890-3314) | §2 |
| F2 | Run metadata JSON (always; root; atomic via .tmp+rename) | `BaseSolver::SaveMetadata*` (palace/drivers/basesolver.cpp:117-135,184-199,386-520) | `palace.json` | GitTag, Problem{MPISize,OpenMPThreads,MeshElements,DegreesOfFreedom,MultigridDegreesOfFreedom,Iteration}, SavedAdaptedMesh{Dimension,TrueVertices,TrueEdges,TrueFaces?,Cells,DomainAttributes,BoundaryAttributes}, LinearSolver{TotalSolves,TotalIts}, ElapsedTime{Durations,Counts}, PeakMemoryGrowthMegabytes/Min/Max/Sum, PeakNodeMemory…, PeakMemoryMegabytes{Min,Max,Average,Total}, Excitations{} |
| F3 | Resolved-config JSON (always; world root) | `WriteResolvedConfig` (palace/utils/iodata.hpp:65-72; main.cpp:248-251) | `<input_stem>_resolved.json` (e.g. `cavity_resolved.json`) | Input config + all defaults concretized; schema-valid, re-runnable (docs/src/guide/postprocessing.md "Resolved configuration record") |
| F4 | ParaView/VTK (DEFAULT ON) | `Problem.OutputFormats.Paraview=true` (configfile.cpp:218; configfile.hpp:51) | `paraview/<solver>/Cycle%06d/data.pvtu` + per-rank `.vtu`; `paraview/<solver>_boundary/...` for boundary mesh (postoperator.cpp:764-775). `<solver>` = driven|eigenmode|electrostatic|magnetostatic|transient|boundarymode (postoperator.cpp:76-94). Confirmed by example path `postpro/thick_impedance/paraview/boundarymode/Cycle000002/data.pvtu` (examples/cpw2d/plot_cpw2d_docs.py:22-24) | §2 |
| F5 | MFEM gridfunction / GLVis (opt-in) | `OutputFormats.GridFunction=true` (default false, configfile.hpp:54) | `gridfunction/<solver>/<Field>_<step %06d>.gf.<rank %06d>` (postoperator.cpp:1373-1377; docs postprocessing.md) | E/E_real/E_imag, En*, B*, Bt_real/imag, V, A, U_e, U_m, S, Sn (postoperator.cpp:1385-1505), MFEM `GridFunction::Save` ASCII |
| F6 | Adapted mesh (opt-in) | Model.Refinement save-adapted-mesh flag (palace/utils/geodata.cpp:2715-2727) | `<mesh_stem>.mesh` (or `.meshgz` if MFEM+zlib) | Serial MFEM mesh of final AMR state |
| F7 | AMR iteration archives (AMR only, max_it>0) | `SaveIteration` (basesolver.hpp:86-93; basesolver.cpp:30-110) | `iterationXX/<moved outputs>` + relative symlinks left behind; palace.json copied (not moved); `Problem.Iteration` = 1-based index | Per-iteration snapshots |
| S1 | stdout/stderr (no log file; docs advise `…| tee log.out`, docs/src/run.md:28-33) | `Mpi::Print` everywhere; final `BlockTimer::Print` (palace/driver.cpp:89) | stream only | §4 |
| A1 | In-process API | `palace::Run(iodata,…)` (palace/driver.hpp, main.cpp:260) reused by Catch2 regression harness (test/unit/regression/) | n/a | test-only driver entry; NOT a results API. No databases, no sockets. |

2. FORMAT GRAMMARS
CSV engine (palace/utils/tablecsv.{hpp,cpp}): col sep `,`, row sep `\n` (tablecsv.hpp:104-105); header row = human `header_text` with units in parens — NOT stable IDs, parse by position; floats `{:+.{prec}e}` e.g. `+2.000000000e+00` (tablecsv.cpp:57-64); default prec 12 (tablecsv.hpp:22); index-col prec 8 for f/t, 2 for m/i (postoperatorcsv.cpp:344-358); missing cell `NULL` (hpp:26); evanescent Floquet_S pads `NaN` (postoperatorcsv.cpp:1446-1459). Real example from test/unit/test-tablecsv.cpp:101-107:
```
            Header Col 1,            Header Col 2,            Header Col 3
                    NULL,        +2.000000000e+00,        +3.000000000e+00
                    NULL,                    NULL,        +6.000000000e+00
```
Units: SI, dimensionalized at write (postoperatorcsv.cpp:26-150); index col per solver: driven `f (GHz)`, transient `t (ns)`, eigen/boundarymode `m`, electro/magnetostatic `i` (LabelIndexCol, postoperatorcsv.cpp:326-342). S conversions: mag = 20·log10|S| dB, phase = arg° (postoperatorcsv.hpp:221-226).
Per-file columns (headers verbatim):
- domain-E.csv: `E_elec/E_mag/E_cap/E_ind (J)` + per-domain `E_elec[i]/p_elec[i]/E_mag[i]/p_mag[i]` (postoperatorcsv.cpp:571-600).
- port-V/I.csv: `V_inc[i]/I_inc[i]`, `Re/Im{V[i]} (V)`, `Re/Im{I[i]} (A)` (+`V_wp` for wave ports w/ voltage coords); complex peak phasors (postoperatorcsv.cpp:1063-1130; docs).
- port-S.csv (DRIVEN, multi-simple excitations only): `|S[o][e]| (dB)`, `arg(S[o][e]) (deg.)` per obs/exc port pair — NOT Touchstone (postoperatorcsv.cpp:1217-1232).
- port-Z.csv: `Re/Im{Z_PV[i]}`, `Re/Im{Z[i][e]} (Ohm)` (postoperatorcsv.cpp:1283-1325).
- port-floquet-S.csv: `|S[Pp(m,n)POL][exc]|/arg` per order/pol (TE/TM or RHC/LHC) (postoperatorcsv.cpp:1330-1400).
- eig.csv: `m, Re{f} (GHz), Im{f} (GHz), Q, Error (Bkwd.), Error (Abs.)` (postoperatorcsv.cpp:1470-1477). port-EPR.csv: `p[i]`; port-Q.csv: `Q_ext[i], κ_ext[i] (GHz)` (:1510-1555).
- mode-kn.csv: `m, Re/Im{kn} (1/m), Re/Im{n_eff}, errors`; mode-Z.csv: `Z_PV/L_PV/C_PV (+Z_VI/L_VI/C_VI)`; mode-V.csv: `Re/Im{V[i]} (V)` (:1581-1680).
- probe-E.csv `Re/Im{E_x/y/z[probe][exc]} (V/m)` (scalar probes drop _x; static solvers real-only); probe-En (V/m), probe-Bt (T), probe-B (Wb/m²) (:852-983).
- surface-F.csv: `Re/Im{Φ_elec} (C)`, `Φ_mag (Wb)`, `Φ_pow (W)` (:645-700). surface-Q.csv: `p_surf[i], Q_surf[i]` (:725-741). surface-I.csv: `I_inc[i] (A)` (:1002-1016). farfield-rE.csv: driven `f,exc,theta,phi,r*Re/Im{E_x,y,z} (V)`; eigenmode adds m,f_re,f_im (:773-810). error-indicators.csv: single row `Norm,Minimum,Maximum,Mean` (:1706-1719).
- terminal-C/-Cinv/-Cm.csv: `i, C[i][attr] (F)` etc. (electrostaticsolver.cpp:153-177); terminal-V.csv: `V_inc[i] (V)`; terminal-M/-Minv/-Mm (H), terminal-I.csv `I_inc[i] (A)`; terminal-Phi.csv has TWO schemas on different paths: energy+`Phi_inc[loop] (Wb)` (:560-578) vs excitation list `Phi_inc[i] (Wb)` (:962-975) — same filename, check columns.
- rom-*.csv (drivensolver.cpp:397; romoperator.cpp): `rom-port-reference.csv` (f, Re/Im Y_ref S, Z_ref Ω, prec 17), `rom-coupled-S.csv` (f, Re/Im per S key), `rom-coupled-G/H.csv`, `rom-Linv/C/Rinv-re/im.csv` (+`<load>-*` variants, if nonzero), `rom-orthogonalization-matrix-R.csv`, `rom-eigenvalues.csv` (Re/Im f GHz,Q,errors — same convention as eig.csv), `rom-eigenvectors-re/im.csv`.
ParaView: raw-appended binary VTK XML, BINARY32, compression 0, high-order + levels-of-detail (postoperator.cpp:776-806; docs: needs ParaView ≥5.12.1). Domain fields: E(_real/_imag) V/m, B* Wb/m², En*, Bt_real/imag, V (V), A (A), U_e/U_m (J/m³), S (W/m²), Sn; boundary adds Q_s* (C/m²), J_s* (A/m), E0_<idx>_real/imag (V/m) (postoperator.cpp:899-1117; docs). Final extra cycle: cell fields `Rank` (1-based), `Indicator`, at sentinel time 99/999… (postoperator.cpp:1273-1311). Cycle index = step/mode/freq/source ordinal; driven time attr = f_Hz (postoperator.cpp:1235-1247).
palace.json: nlohmann json, `dump(2)` + \n (basesolver.cpp:127-135). Schema = keys in §1/F2; no formal schema file for outputs (scripts/schema/config-schema.json covers INPUT config only, incl. Problem{Type,Verbose,Output,OutputFormats{Paraview,GridFunction}}).

3. PYTHON BINDINGS: NONE. Zero pybind/nanobind/C-API in palace/ or CMake (only .py in repo: examples/*/plot_*_docs.py ParaView/pvpython post-hoc readers, .github CI scripts). Audit "NONE official" CONFIRMED. Closest machine readers: CSV (pandas), palace.json (json), VTU (pyvista/VTK), .gf (no Python reader in repo).

4. STDIO-ONLY RESIDUE (results on stdout NOT in files, or only at reduced precision):
- Eigenmode/freq summaries are MIRRORED, not residue: eig table printed per mode at prec 6 (`m, Re/Im f, Q, errors`, postoperator.cpp:2361-2379) vs prec 12 in eig.csv; S lines `S[i][j] = re+imi, |S|, arg` (%.3e, :1947-1989) vs port-S.csv mag/phase; boundarymode `eig i: kn, n_eff` (boundarymodesolver.cpp:484) vs mode-kn.csv; ROM estimates `f, Q, bkwd error` (romoperator.cpp:3316-322) vs rom-eigenvalues.csv.
- TRUE residue: solver/convergence chatter (ARPACK/SLEPc config, shift σ, `Found N converged eigenvalues (first=…)`, greedy ω*/error, `Sol. ||E||`, error-estimate notes); `Elapsed Time Report (s)` + `Peak Memory` tables (timer.hpp:383-404) — same numbers ARE in palace.json but the formatted table is stdout-only; `Wrote … to disk (Paraview|grid function)` markers (:2121-2129); warnings/errors (MFEM_ABORT/Mpi::Warning, e.g. AMR halt, non-convergence early-return leaves palace.json at last converged — magnetostaticsolver.cpp:498); banner/version (`--version`, PrintPalaceVersion). Exit-code semantics not enumerated in scope.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference bindings > structured files > deterministic text):
No bindings exist → ranked file paths: (1) CSV tables — primary (pandas-parseable; stable Table writer; headers carry units; parse positionally); port-S.csv needs mag/phase→complex conversion for Touchstone-equivalent use. (2) palace.json — run metadata/timings/memory/DOFs (do NOT look for S-params here). (3) <stem>_resolved.json — exact input record for provenance. (4) VTU/PVTU via pyvista/VTK for fields (BINARY32 raw-appended; ParaView ≥5.12.1). (5) .gf only if GLVis embedding needed. Avoid stdout scraping — all numeric results are in files at equal/higher precision; stdout adds only convergence diagnostics. Pin/version evidence: UNSOURCED, verified at 8874e6cf8f3c6111867cb0c01cb7efacd73fd48c (2026-10-30); doc grounding docs/src/guide/postprocessing.md + docs/src/run.md + scripts/schema/config-schema.json.
```
