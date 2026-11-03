# xyce — output dissection

Dissector ref: prior result 9 (text `handoff-5f6a4005327a10eae5b48aaa2731c2756b46b6e15cb02f2fe375d192b12337eb-c2a216aa0a3fb05108968611af6bcc58cf298454521631c0fe0b6bb6751b9f9b.txt`, summary `handoff-278197aaf119a0952b263735e59ae6b12845bcec4a631b2d8fd2a32815ef9e8c-8863fc9106cd03e4aaf8859b100a6f97ed949f48abf6bb490e6f467cffac627c.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `a592a42ae7472151d1c8e3bca0ca62d27476f2f3`
- Clone date: `2025-06-10`
- Pin: Clone: /tmp/rocket-tool-src/xyce/ @ SHA a592a42ae7472151d1c8e3bca0ca62d27476f2f3, date 2025-06-10 (`git rev-parse HEAD`, `git log -1 --format=%cs`). Pin evidence: `CMakeLists.txt:34` project(Xyce VERSION 7.10.0) + `configure.ac:9` AC_INIT(Xyce,R::7.10) — consistent with provision pin XYCE_REF=Releas
- Doc/source URLs:
  - https://xyce.sandia.gov/
  - https://xyce.sandia.gov/documentation-tutorials/building-guide/

### Dissector header (verbatim, whitespace-trimmed)

```text
XYCE OUTPUT DISSECTION (review only, no edits)
Clone: /tmp/rocket-tool-src/xyce/ @ SHA a592a42ae7472151d1c8e3bca0ca62d27476f2f3, date 2025-06-10 (`git rev-parse HEAD`, `git log -1 --format=%cs`). Pin evidence: `CMakeLists.txt:34` project(Xyce VERSION 7.10.0) + `configure.ac:9` AC_INIT(Xyce,R::7.10) — consistent with provision pin XYCE_REF=Release-7.10.0 (`provision_toolchain.sh:76-80`). Trilinos 17-2-1 pin not verifiable from this clone (separate repo). Docs HTML present but content-free for outputs (home page + autotools build guide only; canonical URLs https://xyce.sandia.gov/ and https://xyce.sandia.gov/documentation-tutorials/building-guide/); output semantics taken from in-repo `doc/Reference_Guide/*.tex` + source below.

FILENAME BASE RULE (all file channels): base = `-o <basename>` if given, else the netlist path exactly as typed (extension NOT stripped, e.g. `Xyce rc.cir` -> `rc.cir.prn`); suffix appended (`N_IO_CmdParse.C:96-109`). Per-`.PRINT` precedence: `-r` file (raw-capable formats only) > `-o` base+defaultExtension > `FILE=` on `.PRINT` > netlist base; step/sweep suffix inserted between stem and extension (`N_IO_OutputterLocal.C:87-178`).
```

## 1. Result channels

1. RESULT CHANNELS
| # | Channel | Producing flag/command | Filename pattern (<B>=base) |
|---|---|---|---|
| 1 | TRAN table | `.PRINT TRAN [FORMAT=STD\|NOINDEX\|GNUPLOT\|SPLOT]` | `<B>.prn` |
| 2 | TRAN CSV | `.PRINT TRAN FORMAT=CSV` | `<B>.csv` |
| 3 | TRAN raw | `.PRINT TRAN FORMAT=RAW` (+CLI `-a` for ASCII) | `<B>.raw` (binary default) |
| 4 | TRAN Tecplot | `.PRINT TRAN FORMAT=TECPLOT` | `<B>.dat` |
| 5 | TRAN Probe | `.PRINT TRAN FORMAT=PROBE` | `<B>.csd` |
| 6 | DC table/csv/raw/dat/csd | `.PRINT DC [FORMAT=...]` | `<B>.prn`/`.csv`/`.raw`/`.dat`/`.csd` |
| 7 | AC freq-domain | `.PRINT AC [FORMAT=...]` | `<B>.FD.prn`/`.FD.csv`/`.FD.dat`/`.csd`/`.raw` |
| 8 | AC initial-cond tran | `.PRINT AC_IC [FORMAT=...]` | `<B>.TD.prn`/`.TD.csv`/`.TD.dat`/`.TD.csd`/`.raw` |
| 9 | NOISE | `.PRINT NOISE [FORMAT=STD\|NOINDEX\|GNUPLOT\|SPLOT\|CSV\|TECPLOT]` (PROBE disabled, `N_IO_OutputMgr.C:1805`) | `<B>.NOISE.prn`/`.csv`/`.dat` |
| 10 | HB (+TD/FD/IC/STARTUP) | `.PRINT HB[_TD\|_FD\|_IC] [FORMAT=...]` | `<B>.HB.TD.{prn,csv,dat}`, `<B>.HB.FD.{prn,csv,dat}`, `<B>.hb_ic.{prn,csv}` |
| 11 | HOMOTOPY/SENS/PCE/ES/MPDE/TRADJ | `.PRINT <TYPE> [FORMAT=...]` | `<B>.HOMOTOPY.*`, `<B>[.FD].SENS.{prn,csv,dat,txt}`, `<B>.PCE.*`, `<B>.ES.*`, `<B>.MPDE.{csv,dat}`, `<B>.TRADJ.*` |
| 12 | S-param Touchstone | `.LIN ...` + `.PRINT ... FORMAT=TOUCHSTONE[2]` | `<B>.sNp` (N=port count, `N_IO_OutputterSParamTS1.C:201-203`) |
| 13 | Raw override (ALL circuit vars) | CLI `-r <file>` (+`-a` = ASCII) | exactly `<file>` |
| 14 | Measures | `.MEASURE ...` (`.OPTIONS MEASURE PRINT=ALL`) | `<B>.mtN` TRAN / `.maN` AC,NOISE / `.msN` DC (N=`.STEP` idx); continuous-mode: `<B>_<meas>.(mt\|ma\|ms)N` |
| 15 | Stepped expressions | `.RESULT {expr}` (emitted ONLY if `.STEP` present) | `<B>.res` |
| 16 | Fourier | `.FOUR <freq> <ov>...` | `<B>.fourN` |
| 17 | FFT | `.FFT <ov> ...` | `<B>.fftN` |
| 18 | Log stream | default stdout; CLI `-l <path>` (`cout`=stdout), `-per-processor` adds `.<n>.<r>` | stdout or `<path>` |
| 19 | `.PRINT` to console | `.PRINT ... FILE=CONSOLE` (also `-l` path `CONSOLE`) | stdout (`N_IO_OutputFileBase.C:103`, `N_IO_OutputMgr.C:414`) |
| 20 | Response file | CLI `-rsf <file>` (Dakota/external coupling; default `response.out`) | `<file>` |
| 21 | Diagnostics | CLI `-param`, `-namesfile`, `-noise_names_file`, `-doc[_cat]`, `-syntax`, `-norun`, `-count` | stdout or named path / latex files |
| 22 | In-process C API | libxycecinterface (ctypes/VPI/MATLAB/Simulink) | API returns (see 3) |
| 23 | Databases | — | NONE in source |

## 2. Format grammars

2. FORMAT GRAMMARS (parser-author detail; `doc/Reference_Guide/PRINT_{TRAN,AC,DC,NOISE,HB}_Command.tex` confirm files+lead columns)
- STD `.prn`: line1 = header, col names joined by delimiter (default single space; `-delim`/`.PRINT DELIMITER=` TAB|COMMA|COLON|SEMICOLON|"str", `N_IO_CmdParse.C:202`, `N_IO_OutputMgr.C:1589-1618`). Col1 `Index` (int, fixed w5) unless `FORMAT=NOINDEX`; data cols default width 17 precision 9 (`N_IO_Outputter.h:192-193`), `.PRINT PRECISION=/WIDTH=` overridable; `TIME`/`FREQ`/sweep col follows, then requested vars. Footer `End of Xyce(TM) Simulation` IFF no `.STEP` (`N_IO_OutputterTimePrn.C:150-165`). GNUPLOT/SPLOT = STD + blank-line block separators between steps. CSV: comma-joined, NO Index col (`TIME`/`FREQ` first). AC (non-PROBE): each complex var expands to TWO cols `Re(V(a))`, `Im(V(a))` (`N_IO_OutputterLocal.C:296-367`); explicit `VR/VI/VM/VP()` ops exist (`N_IO_OpBuilders.C:658-660,781-788`); PROBE never expands (`N_IO_OutputMgr.C:1713`). No gold `.prn` in `test/` (regression suite external) — grammar from writer source.
- RAW ASCII `.raw` (SPICE3 rawfile, `N_IO_OutputterTimeRawASCII.C:110-260`, values scientific prec 8): `Title: <title>` (once) / `Date: <ctime>` (NON-DETERMINISTIC, strip for goldens) / per plot: `Plotname: {Transient Analysis|DC operating point|DC transfer characteristic|Step Analysis: Step i of n params: name = v ...}` / `Flags: real` (freq variant: complex) / `No. Variables: N` / `No. Points: N` (backpatched in place) / optional `Version:` / `Variables:` + `\t<i>\t<name>\t<type>` per var (`time|frequency|current|voltage|expression|unknown`; `FREQ` renamed `FREQUENCY`) / `Values:` + rows. -r override uses same writers (`N_IO_OutputterOverrideRaw[ASCII]`), all vars.
- RAW binary `.raw`: identical text header through `Variables:`, then `Binary:` marker + native-endian double stream via `fwrite` (`N_IO_OutputterTimeRaw.C:~150-269`).
- Tecplot `.dat`: `TITLE = "<netlist> - <title>",` / `VARIABLES = ...` / `ZONE F=POINT ...` then rows; freq variant `TITLE = " Xyce Frequency Domain data, ..."` (`N_IO_Tecplot.C:113-114,130,205-206,226`).
- Touchstone `.sNp`: TS1 (col-row order special-cased for 2-port, `SParamTS1.C:222-224`) or TS2; `Freq` col1; `.LIN DATAFORMAT=RI|MA|DB`, `LINTYPE=S|Y|Z` (`N_IO_OutputMgr.C:1543-1571`); standard Touchstone grammar (scikit-rf readable).
- `.mtN/.maN/.msN`: one line per measure: `<NAME> = <sci>` or `<NAME> = FAILED` (failed + `.OPTIONS MEASURE MEASFAIL=1`; `N_IO_MeasureAverage.C:144-160`); `PRINT=NONE` kills file+stdout, `STDOUT` kills file only (`N_IO_MeasureBase.C:540-541`).
- `.res`: header `STEP <sweepname:20> <{expr}:20>...`; one row per `.STEP` iteration `<stepidx:10> <sweepvals> <results>`, scientific prec 8 (`N_IO_OutputResults.C:203-284`).
- `.fourN`: per freq x var: `Fourier analysis for <name>:` / `  No. Harmonics: <#>, THD: <sci,prec6>, Gridsize: <G>, Interpolation Type: Cubic Spline` / header `Harmonic Frequency Magnitude Phase Norm. Mag Norm. Phase` (w12/16x5) / rows k=0..8 (DC+9 harmonics); phase ALWAYS degrees (`N_IO_FourierMgr.C:924-958`, `FOUR_Command.tex:34,68`).
- `.fftN` + `-rsf` file + `.csd` byte layout: partially UNRESOLVED (emitters verified: `N_IO_FFTMgr.C:285`, `N_IO_OutputResponse.C:51`, `N_IO_OutputCsd.C`/`N_IO_Probe.*`; bodies not read — see gaps).
- Log/stdout: `lout/dout/pout` all -> stdout by default, tee'd post-init; `-l` redirects rank 0 (`N_UTL_LogStream.C:53-72,126-128`); `-quiet` drops some progress (`N_IO_CmdParse.C:196`).

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row: essentially CONFIRMED, one refinement)
- No pip-installable results binding in repo (no setup.py/pyproject; PyPI-placeholder claim not re-probed here — no network claim made). What exists is source-build-only:
  (a) C interface `utils/XyceCInterface/N_CIR_XyceCInterface.h` + ctypes wrapper `xyce_interface.py.cmake` (`class xyce_interface`): requires building Xyce as shared objects + PYTHONPATH setup (`utils/XyceCInterface/README`). Natively returns: `obtainResponse(varName)` scalar, `getTimeVoltagePairsADC[LimitData]` / `getTimeStatePairsADC[LimitData]` (time+voltage/state arrays per ADC device), `getSimTime/getFinalTime`, `getDeviceParamVal/getCircuitValue`, device/ADC maps; inputs: `updateTimeVoltagePairs` (DAC stimuli), `setCircuitParameter/setADCWidths`, `runSimulation/simulateUntil`. VPI + MATLAB (`XyceRest.py`) + Simulink s-function share it.
  (b) PyMi (`Xyce_PYMI` CMake opt, pybind11 embed, `src/test/GenExtTestHarnesses/CMakeLists.txt:3`) is a Python MODEL interpreter (device models) — input-side, NOT a results API. Refinement: the audit's "PyMi needs shared-object build" conflates the two; the shared-object requirement that matters for results is libxycecinterface, and using it violates TOOL-OUTPUTS (bindings read results, never run in-process) since reads require an in-process run.
- File outputs (`.raw/.prn/.csv/.mt0`) have no reader binding; `utils/{plotXyce,gnuplotXyce}.py` are plotting helpers only (not grammar-verified). Verdict DEFER stands.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (why: streamed through log system / verbose-only writers, no file equivalent)
- `.OP` device-model+instance dump -> log file only (`PRINT_TRAN_Command.tex:29` + `.OP` runs bias print, `OP_Command.tex:13-30`).
- Measure window/diagnostics: `.mtN` carries ONLY `NAME = value`; stdout block (`***** Measure Functions *****`, `N_IO_MeasureManager.C:793-828`) adds per-measure warnings + `Measure Start/End <time|freq|<sweep> value>= ...` lines (`N_IO_MeasureAverage.C:196-216`).
- FFT verbose stdout (`outputVerboseResults(lout)`, `N_IO_FFTMgr.C:115`); banner/progress/errors/warnings; `-param` terse param dump; anything routed via `FILE=CONSOLE` (user choice).

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text; all verified at 7.10.0 sources above)
1. `.PRINT FORMAT=CSV` + `.MEASURE` (`.mtN` `NAME = value`) — primary; header row + trivial measure grammar; strip nothing. 2. `.LIN` Touchstone `.sNp` for S-params (standard grammar). 3. `FORMAT=RAW` + `-a` ASCII raw (SPICE3 grammar, existing readers; strip `Date:`, handle multi-plot `.STEP`). 4. STD `.prn` (+`NOINDEX`) — deterministic but fixed-width/justified; assert footer only when no `.STEP`. 5. Tecplot `.dat` (zone per step). REJECT for MVP: ctypes in-process reads (execution rule + DEFER + shared-object build); binary `.raw`/`.csd` (endian/binary, csd grammar unresolved); `-rsf` (Dakota-facing, unresolved); stdout scraping except `NAME =` fallback. GAPS (unresolved): `.csd` byte grammar, `.fftN` body, `-rsf` grammar, no in-repo gold outputs, PyPI `xyce` placeholder not re-probed.

## Weak-evidence gaps (flagged by dissector)

- - `.fftN` + `-rsf` file + `.csd` byte layout: partially UNRESOLVED (emitters verified: `N_IO_FFTMgr.C:285`, `N_IO_OutputResponse.C:51`, `N_IO_OutputCsd.C`/`N_IO_Probe.*`; bodies not read — see gaps).
- - No pip-installable results binding in repo (no setup.py/pyproject; PyPI-placeholder claim not re-probed here — no network claim made). What exists is source-build-only:
- 1. `.PRINT FORMAT=CSV` + `.MEASURE` (`.mtN` `NAME = value`) — primary; header row + trivial measure grammar; strip nothing. 2. `.LIN` Touchstone `.sNp` for S-params (standard grammar). 3. `FORMAT=RAW` + `-a` ASCII raw (SPICE3 grammar, existing readers; strip `

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
XYCE OUTPUT DISSECTION (review only, no edits)
Clone: /tmp/rocket-tool-src/xyce/ @ SHA a592a42ae7472151d1c8e3bca0ca62d27476f2f3, date 2025-06-10 (`git rev-parse HEAD`, `git log -1 --format=%cs`). Pin evidence: `CMakeLists.txt:34` project(Xyce VERSION 7.10.0) + `configure.ac:9` AC_INIT(Xyce,R::7.10) — consistent with provision pin XYCE_REF=Release-7.10.0 (`provision_toolchain.sh:76-80`). Trilinos 17-2-1 pin not verifiable from this clone (separate repo). Docs HTML present but content-free for outputs (home page + autotools build guide only; canonical URLs https://xyce.sandia.gov/ and https://xyce.sandia.gov/documentation-tutorials/building-guide/); output semantics taken from in-repo `doc/Reference_Guide/*.tex` + source below.

FILENAME BASE RULE (all file channels): base = `-o <basename>` if given, else the netlist path exactly as typed (extension NOT stripped, e.g. `Xyce rc.cir` -> `rc.cir.prn`); suffix appended (`N_IO_CmdParse.C:96-109`). Per-`.PRINT` precedence: `-r` file (raw-capable formats only) > `-o` base+defaultExtension > `FILE=` on `.PRINT` > netlist base; step/sweep suffix inserted between stem and extension (`N_IO_OutputterLocal.C:87-178`).

1. RESULT CHANNELS
| # | Channel | Producing flag/command | Filename pattern (<B>=base) |
|---|---|---|---|
| 1 | TRAN table | `.PRINT TRAN [FORMAT=STD\|NOINDEX\|GNUPLOT\|SPLOT]` | `<B>.prn` |
| 2 | TRAN CSV | `.PRINT TRAN FORMAT=CSV` | `<B>.csv` |
| 3 | TRAN raw | `.PRINT TRAN FORMAT=RAW` (+CLI `-a` for ASCII) | `<B>.raw` (binary default) |
| 4 | TRAN Tecplot | `.PRINT TRAN FORMAT=TECPLOT` | `<B>.dat` |
| 5 | TRAN Probe | `.PRINT TRAN FORMAT=PROBE` | `<B>.csd` |
| 6 | DC table/csv/raw/dat/csd | `.PRINT DC [FORMAT=...]` | `<B>.prn`/`.csv`/`.raw`/`.dat`/`.csd` |
| 7 | AC freq-domain | `.PRINT AC [FORMAT=...]` | `<B>.FD.prn`/`.FD.csv`/`.FD.dat`/`.csd`/`.raw` |
| 8 | AC initial-cond tran | `.PRINT AC_IC [FORMAT=...]` | `<B>.TD.prn`/`.TD.csv`/`.TD.dat`/`.TD.csd`/`.raw` |
| 9 | NOISE | `.PRINT NOISE [FORMAT=STD\|NOINDEX\|GNUPLOT\|SPLOT\|CSV\|TECPLOT]` (PROBE disabled, `N_IO_OutputMgr.C:1805`) | `<B>.NOISE.prn`/`.csv`/`.dat` |
| 10 | HB (+TD/FD/IC/STARTUP) | `.PRINT HB[_TD\|_FD\|_IC] [FORMAT=...]` | `<B>.HB.TD.{prn,csv,dat}`, `<B>.HB.FD.{prn,csv,dat}`, `<B>.hb_ic.{prn,csv}` |
| 11 | HOMOTOPY/SENS/PCE/ES/MPDE/TRADJ | `.PRINT <TYPE> [FORMAT=...]` | `<B>.HOMOTOPY.*`, `<B>[.FD].SENS.{prn,csv,dat,txt}`, `<B>.PCE.*`, `<B>.ES.*`, `<B>.MPDE.{csv,dat}`, `<B>.TRADJ.*` |
| 12 | S-param Touchstone | `.LIN ...` + `.PRINT ... FORMAT=TOUCHSTONE[2]` | `<B>.sNp` (N=port count, `N_IO_OutputterSParamTS1.C:201-203`) |
| 13 | Raw override (ALL circuit vars) | CLI `-r <file>` (+`-a` = ASCII) | exactly `<file>` |
| 14 | Measures | `.MEASURE ...` (`.OPTIONS MEASURE PRINT=ALL`) | `<B>.mtN` TRAN / `.maN` AC,NOISE / `.msN` DC (N=`.STEP` idx); continuous-mode: `<B>_<meas>.(mt\|ma\|ms)N` |
| 15 | Stepped expressions | `.RESULT {expr}` (emitted ONLY if `.STEP` present) | `<B>.res` |
| 16 | Fourier | `.FOUR <freq> <ov>...` | `<B>.fourN` |
| 17 | FFT | `.FFT <ov> ...` | `<B>.fftN` |
| 18 | Log stream | default stdout; CLI `-l <path>` (`cout`=stdout), `-per-processor` adds `.<n>.<r>` | stdout or `<path>` |
| 19 | `.PRINT` to console | `.PRINT ... FILE=CONSOLE` (also `-l` path `CONSOLE`) | stdout (`N_IO_OutputFileBase.C:103`, `N_IO_OutputMgr.C:414`) |
| 20 | Response file | CLI `-rsf <file>` (Dakota/external coupling; default `response.out`) | `<file>` |
| 21 | Diagnostics | CLI `-param`, `-namesfile`, `-noise_names_file`, `-doc[_cat]`, `-syntax`, `-norun`, `-count` | stdout or named path / latex files |
| 22 | In-process C API | libxycecinterface (ctypes/VPI/MATLAB/Simulink) | API returns (see 3) |
| 23 | Databases | — | NONE in source |

2. FORMAT GRAMMARS (parser-author detail; `doc/Reference_Guide/PRINT_{TRAN,AC,DC,NOISE,HB}_Command.tex` confirm files+lead columns)
- STD `.prn`: line1 = header, col names joined by delimiter (default single space; `-delim`/`.PRINT DELIMITER=` TAB|COMMA|COLON|SEMICOLON|"str", `N_IO_CmdParse.C:202`, `N_IO_OutputMgr.C:1589-1618`). Col1 `Index` (int, fixed w5) unless `FORMAT=NOINDEX`; data cols default width 17 precision 9 (`N_IO_Outputter.h:192-193`), `.PRINT PRECISION=/WIDTH=` overridable; `TIME`/`FREQ`/sweep col follows, then requested vars. Footer `End of Xyce(TM) Simulation` IFF no `.STEP` (`N_IO_OutputterTimePrn.C:150-165`). GNUPLOT/SPLOT = STD + blank-line block separators between steps. CSV: comma-joined, NO Index col (`TIME`/`FREQ` first). AC (non-PROBE): each complex var expands to TWO cols `Re(V(a))`, `Im(V(a))` (`N_IO_OutputterLocal.C:296-367`); explicit `VR/VI/VM/VP()` ops exist (`N_IO_OpBuilders.C:658-660,781-788`); PROBE never expands (`N_IO_OutputMgr.C:1713`). No gold `.prn` in `test/` (regression suite external) — grammar from writer source.
- RAW ASCII `.raw` (SPICE3 rawfile, `N_IO_OutputterTimeRawASCII.C:110-260`, values scientific prec 8): `Title: <title>` (once) / `Date: <ctime>` (NON-DETERMINISTIC, strip for goldens) / per plot: `Plotname: {Transient Analysis|DC operating point|DC transfer characteristic|Step Analysis: Step i of n params: name = v ...}` / `Flags: real` (freq variant: complex) / `No. Variables: N` / `No. Points: N` (backpatched in place) / optional `Version:` / `Variables:` + `\t<i>\t<name>\t<type>` per var (`time|frequency|current|voltage|expression|unknown`; `FREQ` renamed `FREQUENCY`) / `Values:` + rows. -r override uses same writers (`N_IO_OutputterOverrideRaw[ASCII]`), all vars.
- RAW binary `.raw`: identical text header through `Variables:`, then `Binary:` marker + native-endian double stream via `fwrite` (`N_IO_OutputterTimeRaw.C:~150-269`).
- Tecplot `.dat`: `TITLE = "<netlist> - <title>",` / `VARIABLES = ...` / `ZONE F=POINT ...` then rows; freq variant `TITLE = " Xyce Frequency Domain data, ..."` (`N_IO_Tecplot.C:113-114,130,205-206,226`).
- Touchstone `.sNp`: TS1 (col-row order special-cased for 2-port, `SParamTS1.C:222-224`) or TS2; `Freq` col1; `.LIN DATAFORMAT=RI|MA|DB`, `LINTYPE=S|Y|Z` (`N_IO_OutputMgr.C:1543-1571`); standard Touchstone grammar (scikit-rf readable).
- `.mtN/.maN/.msN`: one line per measure: `<NAME> = <sci>` or `<NAME> = FAILED` (failed + `.OPTIONS MEASURE MEASFAIL=1`; `N_IO_MeasureAverage.C:144-160`); `PRINT=NONE` kills file+stdout, `STDOUT` kills file only (`N_IO_MeasureBase.C:540-541`).
- `.res`: header `STEP <sweepname:20> <{expr}:20>...`; one row per `.STEP` iteration `<stepidx:10> <sweepvals> <results>`, scientific prec 8 (`N_IO_OutputResults.C:203-284`).
- `.fourN`: per freq x var: `Fourier analysis for <name>:` / `  No. Harmonics: <#>, THD: <sci,prec6>, Gridsize: <G>, Interpolation Type: Cubic Spline` / header `Harmonic Frequency Magnitude Phase Norm. Mag Norm. Phase` (w12/16x5) / rows k=0..8 (DC+9 harmonics); phase ALWAYS degrees (`N_IO_FourierMgr.C:924-958`, `FOUR_Command.tex:34,68`).
- `.fftN` + `-rsf` file + `.csd` byte layout: partially UNRESOLVED (emitters verified: `N_IO_FFTMgr.C:285`, `N_IO_OutputResponse.C:51`, `N_IO_OutputCsd.C`/`N_IO_Probe.*`; bodies not read — see gaps).
- Log/stdout: `lout/dout/pout` all -> stdout by default, tee'd post-init; `-l` redirects rank 0 (`N_UTL_LogStream.C:53-72,126-128`); `-quiet` drops some progress (`N_IO_CmdParse.C:196`).

3. PYTHON BINDINGS (audit row: essentially CONFIRMED, one refinement)
- No pip-installable results binding in repo (no setup.py/pyproject; PyPI-placeholder claim not re-probed here — no network claim made). What exists is source-build-only:
  (a) C interface `utils/XyceCInterface/N_CIR_XyceCInterface.h` + ctypes wrapper `xyce_interface.py.cmake` (`class xyce_interface`): requires building Xyce as shared objects + PYTHONPATH setup (`utils/XyceCInterface/README`). Natively returns: `obtainResponse(varName)` scalar, `getTimeVoltagePairsADC[LimitData]` / `getTimeStatePairsADC[LimitData]` (time+voltage/state arrays per ADC device), `getSimTime/getFinalTime`, `getDeviceParamVal/getCircuitValue`, device/ADC maps; inputs: `updateTimeVoltagePairs` (DAC stimuli), `setCircuitParameter/setADCWidths`, `runSimulation/simulateUntil`. VPI + MATLAB (`XyceRest.py`) + Simulink s-function share it.
  (b) PyMi (`Xyce_PYMI` CMake opt, pybind11 embed, `src/test/GenExtTestHarnesses/CMakeLists.txt:3`) is a Python MODEL interpreter (device models) — input-side, NOT a results API. Refinement: the audit's "PyMi needs shared-object build" conflates the two; the shared-object requirement that matters for results is libxycecinterface, and using it violates TOOL-OUTPUTS (bindings read results, never run in-process) since reads require an in-process run.
- File outputs (`.raw/.prn/.csv/.mt0`) have no reader binding; `utils/{plotXyce,gnuplotXyce}.py` are plotting helpers only (not grammar-verified). Verdict DEFER stands.

4. STDIO-ONLY RESIDUE (why: streamed through log system / verbose-only writers, no file equivalent)
- `.OP` device-model+instance dump -> log file only (`PRINT_TRAN_Command.tex:29` + `.OP` runs bias print, `OP_Command.tex:13-30`).
- Measure window/diagnostics: `.mtN` carries ONLY `NAME = value`; stdout block (`***** Measure Functions *****`, `N_IO_MeasureManager.C:793-828`) adds per-measure warnings + `Measure Start/End <time|freq|<sweep> value>= ...` lines (`N_IO_MeasureAverage.C:196-216`).
- FFT verbose stdout (`outputVerboseResults(lout)`, `N_IO_FFTMgr.C:115`); banner/progress/errors/warnings; `-param` terse param dump; anything routed via `FILE=CONSOLE` (user choice).

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text; all verified at 7.10.0 sources above)
1. `.PRINT FORMAT=CSV` + `.MEASURE` (`.mtN` `NAME = value`) — primary; header row + trivial measure grammar; strip nothing. 2. `.LIN` Touchstone `.sNp` for S-params (standard grammar). 3. `FORMAT=RAW` + `-a` ASCII raw (SPICE3 grammar, existing readers; strip `Date:`, handle multi-plot `.STEP`). 4. STD `.prn` (+`NOINDEX`) — deterministic but fixed-width/justified; assert footer only when no `.STEP`. 5. Tecplot `.dat` (zone per step). REJECT for MVP: ctypes in-process reads (execution rule + DEFER + shared-object build); binary `.raw`/`.csd` (endian/binary, csd grammar unresolved); `-rsf` (Dakota-facing, unresolved); stdout scraping except `NAME =` fallback. GAPS (unresolved): `.csd` byte grammar, `.fftN` body, `-rsf` grammar, no in-repo gold outputs, PyPI `xyce` placeholder not re-probed.
```
