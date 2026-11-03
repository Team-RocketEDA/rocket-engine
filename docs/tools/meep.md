# meep — output dissection

Dissector ref: prior result 4 (text `handoff-adaf3a654432d901aa363a26a81cabd8dbaae61ced86e73c417d758b3a0f6d81-2591073c2ca07171f761e9a89ce832388544bd8245b3c92434281cadc8a0fa7b.txt`, summary `handoff-8f99ab8c3f91a00e73272f2c59e5a8d3d7bf2f59cbef62100d8b2c0c7ce7f660-2591073c2ca07171f761e9a89ce832388544bd8245b3c92434281cadc8a0fa7b.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `b08d226ba311a04e59c984e97f3e88dd82bc56d1`
- Clone date: `2026-10-09`
- Pin: PIN/VERSION VERIFIED: source tree is 1.35.0 (`configure.ac:3` AC_INIT 1.35.0) == `PYMEEP_PIN="1.35.0"` in rocket-engine/scripts/provision_toolchain.sh:85. Docs: /tmp/rocket-tool-docs/meep-index.html (= https://meep.readthedocs.io/en/latest/), meep-install.html (= .../Installation/).
- Doc/source URLs:
  - https://meep.readthedocs.io/en/latest/

### Dissector header (verbatim, whitespace-trimmed)

```text
MEEP output dissection (REVIEW ONLY, no edits)

CLONE: /tmp/rocket-tool-src/meep/ @ b08d226ba311a04e59c984e97f3e88dd82bc56d1, date 2026-10-09
PIN/VERSION VERIFIED: source tree is 1.35.0 (`configure.ac:3` AC_INIT 1.35.0) == `PYMEEP_PIN="1.35.0"` in rocket-engine/scripts/provision_toolchain.sh:85. Docs: /tmp/rocket-tool-docs/meep-index.html (= https://meep.readthedocs.io/en/latest/), meep-install.html (= .../Installation/).
```

## 1. Result channels

1. RESULT CHANNELS (one table; no databases anywhere)

| # | channel | producing flag/command (exact) | filename pattern |
|---|---|---|---|
| F1 | HDF5 field/material snapshot | py step fns `output_epsilon/mu/hpwr/dpwr/tot_pwr`, `output_{e,d,h,b,s}field[_x/_y/_z/_r/_p]`, `output_dfield_*`, `output_bfield_*`, `output_sfield_*` (`python/simulation.py:6249+`); all funnel to `Simulation.output_component` (:3993) / `output_components` (:4025) → C++ `fields::output_hdf5` (`src/h5fields.cpp:388`) | `{outdir}/{prefix-}{comp}{-stamp}.h5`; stamp=`-%09.2f` meep-time if 0.01<=dt<10 else `-%09d` step (`src/h5fields.cpp:433-453`). Real ex: `test_simulation-ez-000200.00.h5` (`python/tests/test_simulation.py:23`) |
| F2 | HDF5 DFT volume | `Simulation.output_dft(dft_fields, fname)` (:3220) → `fields::output_dft` (`src/dft.cpp:1397+`) | `{outdir}/{fname}.h5` (no timestamp; `.h5` appended if missing, `src/dft.cpp:1383-1385`) |
| F3 | HDF5 far fields | `Simulation.output_farfields(n2f, fname, resolution, where)` (:3450) → `save_farfields` (`src/near2far.cpp:517`) | `{outdir}/{prefix-}{fname}.h5` (prefix prepended automatically, :3468) |
| F4 | HDF5 restart/monitor dumps | `dump_structure/dump_fields/dump_chunk_layout` (:2436-2511), `save_flux/save_force/save_energy/save_near2far` + `load*`/`load_minus*` (:3356+, :3483+, :3590+, :3749+) → `save_dft_hdf5` (`src/dft.cpp:452`) | caller `fname` (+ auto filename-prefix); chunk-layout dump is also HDF5 |
| F5 | PNG image | `output_png(comp, h5topng_opts, rm_h5=True)` (:6172) = F1 then external `h5topng` (h5utils), deletes .h5 by default; `$EPS` = last eps file | `{stem}.png` (h5topng default naming) |
| F6 | CSV timing file | `Simulation.output_times(fname)` (:4962) → `fields::output_times` (`src/time.cpp:192`) | `{fname}[.csv]` (suffix appended if missing) |
| S1 | stdout CSV telemetry | `display_fluxes/display_forces/display_{electric,magnetic,total}_energy` (:3326-3346, :3576, :3734), `dft_ldos` (:6599), `Harminv` (:1128), all via `display_run_data` (:6142) | stream, not file (master rank only, gated on `verbosity.meep>0`) |
| S2 | stdout diagnostics | `run N finished`, `creating output file`, `Meep progress:`, `Field time usage`, `Fragment stats`, geometry echo, solve_cw/bicgstab lines | stream |
| A1 | in-process API returns | `get_array/get_dft_array/get_source/get_field_point`, `get_fluxes/get_forces/get_{electric,magnetic,total}_energy`, `Harminv.modes`, `ldos_data/Fdata/Jdata`, `get_eigenmode_coefficients`, `get_farfield(s)`, `get_array_metadata` | numpy / lists / namedtuples (see §3) |
| C1 | CLI binaries | `meep foo.ctl` (Scheme/libctl driver; `scheme/Makefile.am:1` `bin_PROGRAMS=meep`, hooks in `scheme/meep.cpp:13`); py scripts via `python`+`import meep`; `h5topng` external | emits F1-F6/S1-S2 identically |

## 2. Format grammars

2. FORMAT GRAMMARS
- Units: dimensionless Meep units; frequencies in 2πc/a units (Harminv docstring :1156 "usual Meep 2πc units"); ε/μ relative; fields/energies/flux in self-consistent arbitrary units (freq-domain flux normalized to source power; see docs Units_and_Nonlinearity page, nav in meep-index.html).
- Component vocabulary (`src/vec.cpp:73-112`): `ex ey ez er ep hx hy hz hr hp dx dy dz dr dp bx by bz br bp eps mu` + derived `sx sy sz sr sp energy denergy henergy`. File stem = this name (`eps-000020.00.h5`, `energy-000020.00.h5`, `python/tests/test_simulation.py:479-490` reads all three via h5py).
- F1 datasets: real field → single dataset `{comp}`; complex (Bloch/k-point, or `frequency!=0`) → two datasets `{comp}.r`, `{comp}.i` (`src/h5fields.cpp:390-412`). `output_components("h",Hx,Hy,...)` → one file, one dataset per component (:4025). Dtype float32/float64 follows build precision (`output_single_precision`, `is_single_precision()`); rank/dims = grid slice dims. Plain h5utils-style datasets, no attribute schema (read/write paths in `src/h5file.cpp` carry extent only).
- F2 datasets: per frequency index i: `{comp}_{i}.r`, `{comp}_{i}.i` (`src/dft.cpp:1211,1383`), e.g. `ez_0.r`. One file holds all freqs.
- F3 datasets: exactly 12: `ex.r ex.i … hz.r hz.i`, each nx×ny×nz×nfreq 4-D (singleton dims omitted) (:3450-3471 docstring; `src/near2far.cpp:517`).
- F4 DFT-monitor datasets: flat 1-D `{dprefix_}{comp}_dft`, length Σ Nchunk·nomega·2 realnums, i.e. (re,im) realnum pairs per grid point per freq (`src/dft.cpp:452-466`). Opaque restart grammar: only loadable by same grid/chunks build (`dump_structure` docstring :2436 warns; structure/fields dumps are HDF5 per `src/structure_dump.cpp:18`, `src/fields_dump.cpp:18`).
- F6 CSV (`src/time.cpp:192-222`): header = TimeSink descriptions joined `", "`; one row per MPI rank, `%g` values. Example header family visible in `print_times` (:150): `connecting chunks, time stepping, copying boundaries, …` (exact strings from `DescriptionByTimeSink`).
- S1 grammar (`display_run_data`, :6131-6149): `{name}{run_index}:, {v1}, {v2}, …`; complex rendered `{re}{+|-}{im}i` (`data_to_str`). Names: `flux`, `force`, `electric-energy`, `magnetic-energy`, `total-energy`, `ldos` (col1=freq, col2+=spectra), `harminv` (header row first: `frequency, imag. freq., Q, |amp|, amplitude, error`, :1250-1252, then one row/mode). Example shape: `flux0:, 0.15, 1.0234, …`.
- S2 lines: `run {i} finished at t = {t} ({n} timesteps)` (:3020-3025); `creating output file "{path}"...` (`src/h5fields.cpp:459`); `Meep progress: {t}/{T} = {p}% done in {s}s, {r}s to go` (:6119); `Field time usage:` + `  {desc}: {mean} s +/- {std} s` (`src/time.cpp:150-174`); `Fragment stats` + `  {key}: {n}` (`src/meepgeom.cpp:2473-2480`); `Working in {n} dimensions.` / `Computational cell is …` (:1994-1995).
- Real repo example (`python/examples/bend-flux.py:71,111-116`): `straight_tran_flux = mp.get_fluxes(tran)` → `flux_freqs = mp.get_flux_freqs(refl)` → `R/T = -bend_refl_flux[i]/straight_tran_flux[i]` etc. — canonical flux-ratio post-processing in-API.

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row needs correction)
Audit row (tool-bindings-audit.md:83): "official Python interface, CONDA-ONLY. PyPI meep 1.0.6 is unrelated squat". Half-stale: the **import is `meep`**, the **distribution is `pymeep`**, and upstream now publishes **official `pymeep` binary wheels to PyPI** (`pip install pymeep`, CPython ≥3.10, Linux x86-64/aarch64 + Apple-silicon macOS ≥14, bundling MPB/Harminv/HDF5/FFTW/GSL/LAPACK + mpi4py/mpich — meep-install.html "PyPI Packages" section, pypi.org/project/pymeep/). The squat warning holds only for the bare PyPI name `meep`. Conda-forge route (`conda create -n mp -c conda-forge pymeep[=1.35.0]`, incl. `*=mpi_mpich_*` parallel builds) is still documented and is what provision_toolchain.sh:491-500 asserts (conda-env python only — a pip-installed pymeep is NOT detected there).
Native results returned (all in-process, SWIG `python/meep.i` over libmeep): `get_array` → ndarray float32/64 (complex iff `cmplx`, :4053); `get_dft_array` → complex64/128 (:4196); `get_fluxes/get_forces/get_*_energy` → float lists (:6664-6745); `Harminv.modes` → list of `Mode(freq, decay, Q, amp, err)` (:1272-1280); `get_eigenmode_coefficients` → `EigCoeffsResult(alpha[nbands,nfreq,2] complex, vgrp, kpoints, kdom, cscale)` (:4480-4568); `get_farfield(s)` → complex E/H vectors (:3388-3450); `get_array_metadata` → `ArrayMetadata(x,y,z,w)` ndarrays (:4294, :72); `ldos_data/ldos_Fdata/ldos_Jdata` lists (:6624-6627). Verdict stays DEFER (directive: heavy physics, post_mvp) but binding availability is CONFIRMED and richer than the row implies.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE: nearly zero for physics. Every S1 CSV table has an in-API twin (flux/force/energy getters, `ldos_data`, `Harminv.modes`), because `display_*` only pretty-prints the same objects. Genuinely stdio-only: S2 diagnostics (`run N finished`, progress, `creating output file`, `Field time usage` — though F6 file + C++ `get_timing_data` cover timing), `solve_cw` convergence/eigen-freq lines (`src/cw_fields.cpp:215-234`), BiCGSTAB residuals (:162-223), geometry/susceptibility echo. Why: they are master_printf progress/debug chatter, not result APIs; all gated on verbosity>0.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text; execution stays subprocess)
1) In-API numpy (rank 1): run user script under subprocess `python` (pymeep env), results via `get_fluxes/get_dft_array/get_array/Harminv.modes` — zero parsing. 2) Structured files (rank 2): read F1/F2/F3 HDF5 with h5py using grammars above + F6 timing CSV; filename→quantity mapping is deterministic (`{comp}{-stamp}.h5`). 3) Deterministic text (rank 3, fallback/verify): regex `^(flux|force|(?:electric|magnetic|total)-energy|ldos|harminv)\d:, ` on stdout; never trust exit code alone. Verified at: tree 1.35.0 == pin 1.35.0, clone SHA b08d226ba311a04e59c984e97f3e88dd82bc56d1 (2026-10-09).

## Weak-evidence gaps (flagged by dissector)

- 4. STDIO-ONLY RESIDUE: nearly zero for physics. Every S1 CSV table has an in-API twin (flux/force/energy getters, `ldos_data`, `Harminv.modes`), because `display_*` only pretty-prints the same objects. Genuinely stdio-only: S2 diagnostics (`run N finished`, pr
- Audit row (tool-bindings-audit.md:83): "official Python interface, CONDA-ONLY. PyPI meep 1.0.6 is unrelated squat". Half-stale: the **import is `meep`**, the **distribution is `pymeep`**, and upstream now publishes **official `pymeep` binary wheels to PyPI** (

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
MEEP output dissection (REVIEW ONLY, no edits)

CLONE: /tmp/rocket-tool-src/meep/ @ b08d226ba311a04e59c984e97f3e88dd82bc56d1, date 2026-10-09
PIN/VERSION VERIFIED: source tree is 1.35.0 (`configure.ac:3` AC_INIT 1.35.0) == `PYMEEP_PIN="1.35.0"` in rocket-engine/scripts/provision_toolchain.sh:85. Docs: /tmp/rocket-tool-docs/meep-index.html (= https://meep.readthedocs.io/en/latest/), meep-install.html (= .../Installation/).

1. RESULT CHANNELS (one table; no databases anywhere)

| # | channel | producing flag/command (exact) | filename pattern |
|---|---|---|---|
| F1 | HDF5 field/material snapshot | py step fns `output_epsilon/mu/hpwr/dpwr/tot_pwr`, `output_{e,d,h,b,s}field[_x/_y/_z/_r/_p]`, `output_dfield_*`, `output_bfield_*`, `output_sfield_*` (`python/simulation.py:6249+`); all funnel to `Simulation.output_component` (:3993) / `output_components` (:4025) → C++ `fields::output_hdf5` (`src/h5fields.cpp:388`) | `{outdir}/{prefix-}{comp}{-stamp}.h5`; stamp=`-%09.2f` meep-time if 0.01<=dt<10 else `-%09d` step (`src/h5fields.cpp:433-453`). Real ex: `test_simulation-ez-000200.00.h5` (`python/tests/test_simulation.py:23`) |
| F2 | HDF5 DFT volume | `Simulation.output_dft(dft_fields, fname)` (:3220) → `fields::output_dft` (`src/dft.cpp:1397+`) | `{outdir}/{fname}.h5` (no timestamp; `.h5` appended if missing, `src/dft.cpp:1383-1385`) |
| F3 | HDF5 far fields | `Simulation.output_farfields(n2f, fname, resolution, where)` (:3450) → `save_farfields` (`src/near2far.cpp:517`) | `{outdir}/{prefix-}{fname}.h5` (prefix prepended automatically, :3468) |
| F4 | HDF5 restart/monitor dumps | `dump_structure/dump_fields/dump_chunk_layout` (:2436-2511), `save_flux/save_force/save_energy/save_near2far` + `load*`/`load_minus*` (:3356+, :3483+, :3590+, :3749+) → `save_dft_hdf5` (`src/dft.cpp:452`) | caller `fname` (+ auto filename-prefix); chunk-layout dump is also HDF5 |
| F5 | PNG image | `output_png(comp, h5topng_opts, rm_h5=True)` (:6172) = F1 then external `h5topng` (h5utils), deletes .h5 by default; `$EPS` = last eps file | `{stem}.png` (h5topng default naming) |
| F6 | CSV timing file | `Simulation.output_times(fname)` (:4962) → `fields::output_times` (`src/time.cpp:192`) | `{fname}[.csv]` (suffix appended if missing) |
| S1 | stdout CSV telemetry | `display_fluxes/display_forces/display_{electric,magnetic,total}_energy` (:3326-3346, :3576, :3734), `dft_ldos` (:6599), `Harminv` (:1128), all via `display_run_data` (:6142) | stream, not file (master rank only, gated on `verbosity.meep>0`) |
| S2 | stdout diagnostics | `run N finished`, `creating output file`, `Meep progress:`, `Field time usage`, `Fragment stats`, geometry echo, solve_cw/bicgstab lines | stream |
| A1 | in-process API returns | `get_array/get_dft_array/get_source/get_field_point`, `get_fluxes/get_forces/get_{electric,magnetic,total}_energy`, `Harminv.modes`, `ldos_data/Fdata/Jdata`, `get_eigenmode_coefficients`, `get_farfield(s)`, `get_array_metadata` | numpy / lists / namedtuples (see §3) |
| C1 | CLI binaries | `meep foo.ctl` (Scheme/libctl driver; `scheme/Makefile.am:1` `bin_PROGRAMS=meep`, hooks in `scheme/meep.cpp:13`); py scripts via `python`+`import meep`; `h5topng` external | emits F1-F6/S1-S2 identically |

2. FORMAT GRAMMARS
- Units: dimensionless Meep units; frequencies in 2πc/a units (Harminv docstring :1156 "usual Meep 2πc units"); ε/μ relative; fields/energies/flux in self-consistent arbitrary units (freq-domain flux normalized to source power; see docs Units_and_Nonlinearity page, nav in meep-index.html).
- Component vocabulary (`src/vec.cpp:73-112`): `ex ey ez er ep hx hy hz hr hp dx dy dz dr dp bx by bz br bp eps mu` + derived `sx sy sz sr sp energy denergy henergy`. File stem = this name (`eps-000020.00.h5`, `energy-000020.00.h5`, `python/tests/test_simulation.py:479-490` reads all three via h5py).
- F1 datasets: real field → single dataset `{comp}`; complex (Bloch/k-point, or `frequency!=0`) → two datasets `{comp}.r`, `{comp}.i` (`src/h5fields.cpp:390-412`). `output_components("h",Hx,Hy,...)` → one file, one dataset per component (:4025). Dtype float32/float64 follows build precision (`output_single_precision`, `is_single_precision()`); rank/dims = grid slice dims. Plain h5utils-style datasets, no attribute schema (read/write paths in `src/h5file.cpp` carry extent only).
- F2 datasets: per frequency index i: `{comp}_{i}.r`, `{comp}_{i}.i` (`src/dft.cpp:1211,1383`), e.g. `ez_0.r`. One file holds all freqs.
- F3 datasets: exactly 12: `ex.r ex.i … hz.r hz.i`, each nx×ny×nz×nfreq 4-D (singleton dims omitted) (:3450-3471 docstring; `src/near2far.cpp:517`).
- F4 DFT-monitor datasets: flat 1-D `{dprefix_}{comp}_dft`, length Σ Nchunk·nomega·2 realnums, i.e. (re,im) realnum pairs per grid point per freq (`src/dft.cpp:452-466`). Opaque restart grammar: only loadable by same grid/chunks build (`dump_structure` docstring :2436 warns; structure/fields dumps are HDF5 per `src/structure_dump.cpp:18`, `src/fields_dump.cpp:18`).
- F6 CSV (`src/time.cpp:192-222`): header = TimeSink descriptions joined `", "`; one row per MPI rank, `%g` values. Example header family visible in `print_times` (:150): `connecting chunks, time stepping, copying boundaries, …` (exact strings from `DescriptionByTimeSink`).
- S1 grammar (`display_run_data`, :6131-6149): `{name}{run_index}:, {v1}, {v2}, …`; complex rendered `{re}{+|-}{im}i` (`data_to_str`). Names: `flux`, `force`, `electric-energy`, `magnetic-energy`, `total-energy`, `ldos` (col1=freq, col2+=spectra), `harminv` (header row first: `frequency, imag. freq., Q, |amp|, amplitude, error`, :1250-1252, then one row/mode). Example shape: `flux0:, 0.15, 1.0234, …`.
- S2 lines: `run {i} finished at t = {t} ({n} timesteps)` (:3020-3025); `creating output file "{path}"...` (`src/h5fields.cpp:459`); `Meep progress: {t}/{T} = {p}% done in {s}s, {r}s to go` (:6119); `Field time usage:` + `  {desc}: {mean} s +/- {std} s` (`src/time.cpp:150-174`); `Fragment stats` + `  {key}: {n}` (`src/meepgeom.cpp:2473-2480`); `Working in {n} dimensions.` / `Computational cell is …` (:1994-1995).
- Real repo example (`python/examples/bend-flux.py:71,111-116`): `straight_tran_flux = mp.get_fluxes(tran)` → `flux_freqs = mp.get_flux_freqs(refl)` → `R/T = -bend_refl_flux[i]/straight_tran_flux[i]` etc. — canonical flux-ratio post-processing in-API.

3. PYTHON BINDINGS (audit row needs correction)
Audit row (tool-bindings-audit.md:83): "official Python interface, CONDA-ONLY. PyPI meep 1.0.6 is unrelated squat". Half-stale: the **import is `meep`**, the **distribution is `pymeep`**, and upstream now publishes **official `pymeep` binary wheels to PyPI** (`pip install pymeep`, CPython ≥3.10, Linux x86-64/aarch64 + Apple-silicon macOS ≥14, bundling MPB/Harminv/HDF5/FFTW/GSL/LAPACK + mpi4py/mpich — meep-install.html "PyPI Packages" section, pypi.org/project/pymeep/). The squat warning holds only for the bare PyPI name `meep`. Conda-forge route (`conda create -n mp -c conda-forge pymeep[=1.35.0]`, incl. `*=mpi_mpich_*` parallel builds) is still documented and is what provision_toolchain.sh:491-500 asserts (conda-env python only — a pip-installed pymeep is NOT detected there).
Native results returned (all in-process, SWIG `python/meep.i` over libmeep): `get_array` → ndarray float32/64 (complex iff `cmplx`, :4053); `get_dft_array` → complex64/128 (:4196); `get_fluxes/get_forces/get_*_energy` → float lists (:6664-6745); `Harminv.modes` → list of `Mode(freq, decay, Q, amp, err)` (:1272-1280); `get_eigenmode_coefficients` → `EigCoeffsResult(alpha[nbands,nfreq,2] complex, vgrp, kpoints, kdom, cscale)` (:4480-4568); `get_farfield(s)` → complex E/H vectors (:3388-3450); `get_array_metadata` → `ArrayMetadata(x,y,z,w)` ndarrays (:4294, :72); `ldos_data/ldos_Fdata/ldos_Jdata` lists (:6624-6627). Verdict stays DEFER (directive: heavy physics, post_mvp) but binding availability is CONFIRMED and richer than the row implies.

4. STDIO-ONLY RESIDUE: nearly zero for physics. Every S1 CSV table has an in-API twin (flux/force/energy getters, `ldos_data`, `Harminv.modes`), because `display_*` only pretty-prints the same objects. Genuinely stdio-only: S2 diagnostics (`run N finished`, progress, `creating output file`, `Field time usage` — though F6 file + C++ `get_timing_data` cover timing), `solve_cw` convergence/eigen-freq lines (`src/cw_fields.cpp:215-234`), BiCGSTAB residuals (:162-223), geometry/susceptibility echo. Why: they are master_printf progress/debug chatter, not result APIs; all gated on verbosity>0.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text; execution stays subprocess)
1) In-API numpy (rank 1): run user script under subprocess `python` (pymeep env), results via `get_fluxes/get_dft_array/get_array/Harminv.modes` — zero parsing. 2) Structured files (rank 2): read F1/F2/F3 HDF5 with h5py using grammars above + F6 timing CSV; filename→quantity mapping is deterministic (`{comp}{-stamp}.h5`). 3) Deterministic text (rank 3, fallback/verify): regex `^(flux|force|(?:electric|magnetic|total)-energy|ldos|harminv)\d:, ` on stdout; never trust exit code alone. Verified at: tree 1.35.0 == pin 1.35.0, clone SHA b08d226ba311a04e59c984e97f3e88dd82bc56d1 (2026-10-09).
```
