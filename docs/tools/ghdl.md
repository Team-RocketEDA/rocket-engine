# ghdl — output dissection

Dissector ref: prior result 19 (text `handoff-b94788d4763c6e8cbbe6bbd571dd714d2acd0575e4cabd224e606a55f6d4438c-991329fd9c6d5eea25fb712695776bca6fc2f2660ad221e3ba7e7d53223c1a13.txt`, summary `handoff-9b2915fa8f92e828185a80066e90dd6d402ee12fb9ed34fe90ea50a5453a41aa-991329fd9c6d5eea25fb712695776bca6fc2f2660ad221e3ba7e7d53223c1a13.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `428cc4b734be467f280501528571739c3298d8a6`
- Clone date: `2026-11-01`
- Pin: Clone: SHA 428cc4b734be467f280501528571739c3298d8a6, date 2026-11-01 (/tmp/rocket-tool-src/ghdl). Docs: /tmp/rocket-tool-docs/ghdl-index.html present (title "GHDL — 7.0.0-dev"); subpages not fetched, cited as clone doc/*.rst + ghdl.github.io URLs. Pin: audit row = "bundle"; provision_toolchain.sh pi
- Doc/source URLs: none in header (see dissector header below)

### Dissector header (verbatim, whitespace-trimmed)

```text
GHDL output-capability dissection
Clone: SHA 428cc4b734be467f280501528571739c3298d8a6, date 2026-11-01 (/tmp/rocket-tool-src/ghdl). Docs: /tmp/rocket-tool-docs/ghdl-index.html present (title "GHDL — 7.0.0-dev"); subpages not fetched, cited as clone doc/*.rst + ghdl.github.io URLs. Pin: audit row = "bundle"; provision_toolchain.sh pins oss-cad-suite 20261025 (OSS_CAD_SUITE_PIN), no separate ghdl pin; provision-sources.md lists ghdl as bundle member. Version evidence: pyGHDL/__init__.py:51 __version__="7.0.0-dev"; NEWS.md latest "## [2026-03-07] 6.0".
```

## 1. Result channels

1. RESULT CHANNELS
| # | Channel | Producing command/flag | Filename/stream |
|---|---|---|---|
| 1 | VCD waveform | `ghdl -r/-e+run … --vcd=FILE` (`-`=stdout) | user-named, text VCD (src/grt/grt-vcd.adb:110-159) |
| 2 | gzipped VCD | `--vcdgz=FILE` | user-named .gz (src/grt/grt-vcdz.adb:61-95) |
| 3 | FST waveform | `--fst=FILE` | user-named (src/grt/grt-fst.adb:73-98) |
| 4 | GHW waveform | `--wave=FILE` (`-`=stdout) | user-named, binary (src/grt/grt-waves.adb:61-77,300-318) |
| 5 | PSL report JSON | `--psl-report=FILE` (+`-fpsl` at analyze) | user-named (src/grt/grt-psl.adb:47-65) |
| 6 | Stmt-coverage JSON | `ghdl run … --coverage[=stmt] [--coverage-output=FILE]` | default `coverage-<ts>.json` (src/ghdldrv/ghdlrun.adb:504-510, ghdlcovout.adb:195-199) |
| 7 | Coverage renders | `ghdl coverage --format=gcov\|lcov\|gcovr\|summary [-o F] COV…` | `<src>.gcov` files; lcov+summary→stdout; gcovr→stdout or -o (src/ghdldrv/ghdlcov.adb:480-644,786-821) |
| 8 | AMS quantities CSV | `--wave-csv=FILE` (`-`=stdout) | Time+quantity columns (src/simul/simul-main.adb:41-62, simul-vhdl_simul.adb:4206-4211,4490-4504) |
| 9 | Wave-opt filter file | `--write-wave-opt=FILE` (input: `--read-wave-opt=`) | `$version M.m` + signal paths (src/grt/grt-wave_opt-file.adb) |
| 10 | Synth netlist | `ghdl --synth --out=FMT [-o=FILE]` | stdout default, else -o= (src/ghdldrv/ghdlsynth.adb:170-194,447-491; src/outputs.adb:24-29) |
| 11 | XML AST dump | `ghdl --file-to-xml FILEs` | stdout (src/ghdldrv/ghdlxml.adb:596-602) |
| 12 | HTML pretty/xref | `ghdl --pp-html/--xref-html FILEs` | stdout (src/ghdldrv/ghdlprint.adb:1442-1483) |
| 13 | Analyzed-lib DB | `ghdl -a` | `<lib>-obj{87,93,08,19}.cf` (src/libraries.adb:129-144) |
| 14 | stdout (sim) | `ghdl -r` | asserts/reports, TEXTIO `output`, `--stats`, `--disp-time`, traces, `simulation failed` |
| 15 | stderr (compile) | `ghdl -a/-e/--synth` | diagnostics (src/errorout-console.adb:110-126) |
| 16 | Exit code | all | 0 ok / 1 fail / 3 exec-err / 2 bug-box (src/ghdldrv/ghdlmain.adb:697-706); sim rc=Grt.Errors.Exit_Status (ghdlrun.adb:428-429) |
| 17 | In-process APIs | VPI/VHPI C (`ghdl.load_vpi`), pyGHDL ctypes | callbacks during sim (src/grt/grt-vpi.adb, grt-vhpi.adb, vpi_user.h/vhpi_user.h) |
| 18 | libghw/ghwdump | reader lib + text dumper for ch.4 | ghw/libghw.h, ghw/ghwdump.c |

## 2. Format grammars

2. FORMAT GRAMMARS
- Assert/report line (stdout! Error_Stream=stdout at runtime, grt-main.adb:120): `FILE:LINE:COL:@TIME:(assertion|report|psl assertion|psl assumption|psl cover|psl cover failure SEV): MSG` (grt-lib.adb:48-94; interp twin simul-vhdl_simul.adb:1403-1441). SEV∈note|warning|error|failure. Defaults: assert→error, report/cover→note (synth-vhdl_stmts.adb:4120-4137). TIME=`<int><fs|ps|ns|us|ms|sec>`, auto-scaled ×1000 while divisible (grt-astdio-vhdl.adb:50-70). If SEV ≥ stop-level (default failure; `--assert-level=` note|warning|error|failure|none, grt-options.ads:131-133): second line `<kind> failed` + backtrace, sim aborts, `simulation failed`, exit 1 (grt-lib.adb:85-89, grt-main.adb:173-182). `--expect-failure` inverts. Example shape: `tb.vhdl:42:7:@10ns:(assertion error): counter mismatch`.
- Compile diag (stderr): `file:line:col:[level:] msg`; `error:` printed only w/o location or color/caret on; warnings append ` [-Wname]`; optional source+caret lines (errorout-console.adb:147-272). Location `??:??:??` if nil (files_map.adb:1082-1107).
- PSL JSON (grt-psl.adb:96-210; golden testsuite/gna/ticket24/psl.ref + .sh `simulate psl --psl-report=psl.out` + diff): `{ "details":[{directive:assertion|assumption|cover, name:".ctx.label", file, line:int, finished-count:int, started-count:int, status:passed|failed|covered|not covered|...}], "summary":{assert, assert-failure, assert-pass, assume, assume-failure, assume-pass, cover, cover-failure, cover-pass} }`. Real example: `{ "details" : [ { "directive": "assertion", "name": ".psl(behav).a1", "file": "psl.vhdl", "line": 27, "finished-count": 0, "started-count": 8, "status": "passed"}, …], "summary" : { "assert": 2, "assert-failure": 0, "assert-pass": 2, "assume": 0, … "cover": 1, "cover-failure": 0, "cover-pass": 1} }`.
- Coverage JSON (ghdlcovout.adb:204-297): `{app:"GHDL coverage output file", version:"1.0.0", testcase:"unknown", timestamp:"…", outputs:[{file, dir("." if local), sha1, mode:"stmt", max-line:int, result:{"LINE":0|1,…}}]}`. Mini-JSON grammar mirrored in reader (ghdlcov.adb:78-270).
- Coverage renders: gcov `     -:    0:Source:NAME`, per-line `     1:`|` #####:`|`     -:` + `LN:code`; lcov `TN:/SF:/FN:1,file/FNDA:0|1,file/DA:line,0|1/end_of_record`; gcovr JSON `"gcovr/format_version":"0.6"` files[{file,lines[{branches:[],count,line_number}],functions:[]}]; summary `NAME COV/TOT P.P%` + `Summary: …`.
- VCD (grt-vcd.adb): `$date`(skip w/ `--vcd-nodate`)→`$version`(``  GHDL v0``)→`$timescale`(``  1 fs|ps|ns|us|ms|sec`` per resolution, :267-275)→`$scope module INST $end`→`$var integer 32|real 64|reg N|string 8 ID NAME [L:R] $end`→`$enddefinitions $end`→`#<int-time>` + scalar `0|1ID`, vector `bBITS ID` (int32 MSB-trimmed ≥1 bit, :756-766), real `r<%.16g> ID` (:780-800), enum `sNAME ID` (only `--vcd-enums`). std_logic map `UX01ZWLH-`, or `xx01zz01x` w/ `--vcd-4states` (:736-754). Full dump at t=0, deltas later, final timestamp at end (:1000-1041).
- FST (grt-fst.adb:106-119): fstWriterCreate, FileType=VHDL, Pack=LZ4, Timescale=-3×resolution-scale, Version="GHDL FST v0", repack-on-close.
- GHW (grt-waves.adb:320-334): magic `GHDLwave\n` (9B) + hdr-len 16 + ver-major 0 + ver-minor 1 + size/order bytes; sections `DIR\0…EOD\0`, `TAI\0`; values LEB128/SLEB128. Contract explicitly unstable: doc/ghw/index.rst:19-22; read via ghw/libghw.h or ghwdump, or pywellen. Kaitai notes: github.com/nturley/ghw-notes.
- AMS CSV: header `Time,q1,q2'…` (`'dot` suffix for dot-attrs), rows `Put_F64` comma-separated (simul-vhdl_simul.adb:4189-4211,4495-4504).
- Synth `--out=`: raw|dump|dot|none|vhdl|vhdl-ieee|raw-vhdl|raw-vhdl-ieee|verilog, default vhdl (ghdlsynth.adb:172-194,534). `-o=FILE` else stdout. `--stats`→stdout `Statistics for netlists:` + `snames/modules/instances (free:)/nets (free:)/inputs (free:)/params` + `Number of instances (per module)` (netlists.adb:1507-1574). Sim `--stats`→stdout `total/elab/… wall:/user:/sys:` + signal/cycle/process counters (grt-stats.adb:304-367).
- XML: `<?xml …?>` `<root version="0.13">` `<el id kind file line col …>` per IIR node; fields→attributes/subelements (`ref|list-ref|flist-ref|list-id|flist-id`, string8→length+content); schema=src/vhdl/nodes_meta.* (ghdlxml.adb:304-507).
- `--version`: `GHDL <ver> <release>` + ` Compiled with …` + copyright; `version ref|hash` prints hash (ghdlmain.adb:312-358). Doc URLs: ghdl.github.io/ghdl/using/{Simulation,Synthesis,InvokingGHDL,CommandReference}.html, ghw/index.html; clone doc/using/*.rst.

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row: CONFIRMED, refined)
pyGHDL in-repo (pyGHDL/): `pyGHDL.libghdl` low-level ctypes → versioned `libghdl-7_0_0_dev.{so,dll,dylib}` (auto-located via GHDL_PREFIX/VUNIT_GHDL_PATH/GHDL/pyGHDL/lib/which/build-dir; libghdl/__init__.py); `pyGHDL.dom` high-level VHDL DOM on pyVHDLModel (parse+analyze only); `pyGHDL.cli`, `pyGHDL.lsp`. Returns natively: AST/IIR nodes, DOM objects, in-memory diagnostics via errorout_memory.Get_Nbr_Messages/Get_Error_Record (id/group/file/line/offset/length struct). NO simulation-runner/waveform/assert binding — sim results are files/stdio only. Stale-PyPI warning stands: use bundle/upstream, not PyPI `pyghdl`.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE
Asserts/reports/PSL-failure lines, TEXTIO `output`, `simulation failed`, sim `--stats`, trace/debug (`--disp-time/--trace-signals/--trace-processes/--disp-*`), synth `--stats`, coverage lcov/summary, XML/HTML dumps (no -o flag; outputs.adb defaults null→stdout): only on stdio because GRT has file flags solely for wave/PSL/CSV channels and compile drivers default dumps to stdout. Note trap: runtime diags go to STDOUT (grt-main.adb:120), compile diags to STDERR — never merge blindly.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1) Analyze-stage: pyGHDL.dom/libghdl + errorout_memory for AST/diagnostics (no text scrape). 2) Sim verdicts: exit code + assert-line regex `^(.+):(\d+):(\d+):@(\S+):\((\w[\w ]*) (\w+)\): (.*)$` + `simulation failed`; PSL verdicts from --psl-report JSON summary (skip line-scraping). 3) Waveforms: --fst/--vcd (+--vcd-nodate for determinism) read via pywellen; GHW only via libghw/pywellen (format unstable). 4) Coverage: --coverage-output JSON → `ghdl coverage --format=gcovr -o` or summary. 5) Synth: --out=verilog|vhdl -o= + --stats text (pinned, stable-ish debug grammar). Verified at: clone 428cc4b7 (2026-11-01) ≈ 7.0.0-dev; provision pin oss-cad-suite 20261025 (bundle carries ghdl, no separate pin).

## Weak-evidence gaps (flagged by dissector)

- | 16 | Exit code | all | 0 ok / 1 fail / 3 exec-err / 2 bug-box (src/ghdldrv/ghdlmain.adb:697-706); sim rc=Grt.Errors.Exit_Status (ghdlrun.adb:428-429) |
- - Assert/report line (stdout! Error_Stream=stdout at runtime, grt-main.adb:120): `FILE:LINE:COL:@TIME:(assertion|report|psl assertion|psl assumption|psl cover|psl cover failure SEV): MSG` (grt-lib.adb:48-94; interp twin simul-vhdl_simul.adb:1403-1441). SEV∈not
- Asserts/reports/PSL-failure lines, TEXTIO `output`, `simulation failed`, sim `--stats`, trace/debug (`--disp-time/--trace-signals/--trace-processes/--disp-*`), synth `--stats`, coverage lcov/summary, XML/HTML dumps (no -o flag; outputs.adb defaults null→stdout
- 1) Analyze-stage: pyGHDL.dom/libghdl + errorout_memory for AST/diagnostics (no text scrape). 2) Sim verdicts: exit code + assert-line regex `^(.+):(\d+):(\d+):@(\S+):\((\w[\w ]*) (\w+)\): (.*)$` + `simulation failed`; PSL verdicts from --psl-report JSON summar
- Clone: SHA 428cc4b734be467f280501528571739c3298d8a6, date 2026-11-01 (/tmp/rocket-tool-src/ghdl). Docs: /tmp/rocket-tool-docs/ghdl-index.html present (title "GHDL — 7.0.0-dev"); subpages not fetched, cited as clone doc/*.rst + ghdl.github.io URLs. Pin: audit r
- pyGHDL in-repo (pyGHDL/): `pyGHDL.libghdl` low-level ctypes → versioned `libghdl-7_0_0_dev.{so,dll,dylib}` (auto-located via GHDL_PREFIX/VUNIT_GHDL_PATH/GHDL/pyGHDL/lib/which/build-dir; libghdl/__init__.py); `pyGHDL.dom` high-level VHDL DOM on pyVHDLModel (par

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
GHDL output-capability dissection
Clone: SHA 428cc4b734be467f280501528571739c3298d8a6, date 2026-11-01 (/tmp/rocket-tool-src/ghdl). Docs: /tmp/rocket-tool-docs/ghdl-index.html present (title "GHDL — 7.0.0-dev"); subpages not fetched, cited as clone doc/*.rst + ghdl.github.io URLs. Pin: audit row = "bundle"; provision_toolchain.sh pins oss-cad-suite 20261025 (OSS_CAD_SUITE_PIN), no separate ghdl pin; provision-sources.md lists ghdl as bundle member. Version evidence: pyGHDL/__init__.py:51 __version__="7.0.0-dev"; NEWS.md latest "## [2026-03-07] 6.0".

1. RESULT CHANNELS
| # | Channel | Producing command/flag | Filename/stream |
|---|---|---|---|
| 1 | VCD waveform | `ghdl -r/-e+run … --vcd=FILE` (`-`=stdout) | user-named, text VCD (src/grt/grt-vcd.adb:110-159) |
| 2 | gzipped VCD | `--vcdgz=FILE` | user-named .gz (src/grt/grt-vcdz.adb:61-95) |
| 3 | FST waveform | `--fst=FILE` | user-named (src/grt/grt-fst.adb:73-98) |
| 4 | GHW waveform | `--wave=FILE` (`-`=stdout) | user-named, binary (src/grt/grt-waves.adb:61-77,300-318) |
| 5 | PSL report JSON | `--psl-report=FILE` (+`-fpsl` at analyze) | user-named (src/grt/grt-psl.adb:47-65) |
| 6 | Stmt-coverage JSON | `ghdl run … --coverage[=stmt] [--coverage-output=FILE]` | default `coverage-<ts>.json` (src/ghdldrv/ghdlrun.adb:504-510, ghdlcovout.adb:195-199) |
| 7 | Coverage renders | `ghdl coverage --format=gcov\|lcov\|gcovr\|summary [-o F] COV…` | `<src>.gcov` files; lcov+summary→stdout; gcovr→stdout or -o (src/ghdldrv/ghdlcov.adb:480-644,786-821) |
| 8 | AMS quantities CSV | `--wave-csv=FILE` (`-`=stdout) | Time+quantity columns (src/simul/simul-main.adb:41-62, simul-vhdl_simul.adb:4206-4211,4490-4504) |
| 9 | Wave-opt filter file | `--write-wave-opt=FILE` (input: `--read-wave-opt=`) | `$version M.m` + signal paths (src/grt/grt-wave_opt-file.adb) |
| 10 | Synth netlist | `ghdl --synth --out=FMT [-o=FILE]` | stdout default, else -o= (src/ghdldrv/ghdlsynth.adb:170-194,447-491; src/outputs.adb:24-29) |
| 11 | XML AST dump | `ghdl --file-to-xml FILEs` | stdout (src/ghdldrv/ghdlxml.adb:596-602) |
| 12 | HTML pretty/xref | `ghdl --pp-html/--xref-html FILEs` | stdout (src/ghdldrv/ghdlprint.adb:1442-1483) |
| 13 | Analyzed-lib DB | `ghdl -a` | `<lib>-obj{87,93,08,19}.cf` (src/libraries.adb:129-144) |
| 14 | stdout (sim) | `ghdl -r` | asserts/reports, TEXTIO `output`, `--stats`, `--disp-time`, traces, `simulation failed` |
| 15 | stderr (compile) | `ghdl -a/-e/--synth` | diagnostics (src/errorout-console.adb:110-126) |
| 16 | Exit code | all | 0 ok / 1 fail / 3 exec-err / 2 bug-box (src/ghdldrv/ghdlmain.adb:697-706); sim rc=Grt.Errors.Exit_Status (ghdlrun.adb:428-429) |
| 17 | In-process APIs | VPI/VHPI C (`ghdl.load_vpi`), pyGHDL ctypes | callbacks during sim (src/grt/grt-vpi.adb, grt-vhpi.adb, vpi_user.h/vhpi_user.h) |
| 18 | libghw/ghwdump | reader lib + text dumper for ch.4 | ghw/libghw.h, ghw/ghwdump.c |

2. FORMAT GRAMMARS
- Assert/report line (stdout! Error_Stream=stdout at runtime, grt-main.adb:120): `FILE:LINE:COL:@TIME:(assertion|report|psl assertion|psl assumption|psl cover|psl cover failure SEV): MSG` (grt-lib.adb:48-94; interp twin simul-vhdl_simul.adb:1403-1441). SEV∈note|warning|error|failure. Defaults: assert→error, report/cover→note (synth-vhdl_stmts.adb:4120-4137). TIME=`<int><fs|ps|ns|us|ms|sec>`, auto-scaled ×1000 while divisible (grt-astdio-vhdl.adb:50-70). If SEV ≥ stop-level (default failure; `--assert-level=` note|warning|error|failure|none, grt-options.ads:131-133): second line `<kind> failed` + backtrace, sim aborts, `simulation failed`, exit 1 (grt-lib.adb:85-89, grt-main.adb:173-182). `--expect-failure` inverts. Example shape: `tb.vhdl:42:7:@10ns:(assertion error): counter mismatch`.
- Compile diag (stderr): `file:line:col:[level:] msg`; `error:` printed only w/o location or color/caret on; warnings append ` [-Wname]`; optional source+caret lines (errorout-console.adb:147-272). Location `??:??:??` if nil (files_map.adb:1082-1107).
- PSL JSON (grt-psl.adb:96-210; golden testsuite/gna/ticket24/psl.ref + .sh `simulate psl --psl-report=psl.out` + diff): `{ "details":[{directive:assertion|assumption|cover, name:".ctx.label", file, line:int, finished-count:int, started-count:int, status:passed|failed|covered|not covered|...}], "summary":{assert, assert-failure, assert-pass, assume, assume-failure, assume-pass, cover, cover-failure, cover-pass} }`. Real example: `{ "details" : [ { "directive": "assertion", "name": ".psl(behav).a1", "file": "psl.vhdl", "line": 27, "finished-count": 0, "started-count": 8, "status": "passed"}, …], "summary" : { "assert": 2, "assert-failure": 0, "assert-pass": 2, "assume": 0, … "cover": 1, "cover-failure": 0, "cover-pass": 1} }`.
- Coverage JSON (ghdlcovout.adb:204-297): `{app:"GHDL coverage output file", version:"1.0.0", testcase:"unknown", timestamp:"…", outputs:[{file, dir("." if local), sha1, mode:"stmt", max-line:int, result:{"LINE":0|1,…}}]}`. Mini-JSON grammar mirrored in reader (ghdlcov.adb:78-270).
- Coverage renders: gcov `     -:    0:Source:NAME`, per-line `     1:`|` #####:`|`     -:` + `LN:code`; lcov `TN:/SF:/FN:1,file/FNDA:0|1,file/DA:line,0|1/end_of_record`; gcovr JSON `"gcovr/format_version":"0.6"` files[{file,lines[{branches:[],count,line_number}],functions:[]}]; summary `NAME COV/TOT P.P%` + `Summary: …`.
- VCD (grt-vcd.adb): `$date`(skip w/ `--vcd-nodate`)→`$version`(``  GHDL v0``)→`$timescale`(``  1 fs|ps|ns|us|ms|sec`` per resolution, :267-275)→`$scope module INST $end`→`$var integer 32|real 64|reg N|string 8 ID NAME [L:R] $end`→`$enddefinitions $end`→`#<int-time>` + scalar `0|1ID`, vector `bBITS ID` (int32 MSB-trimmed ≥1 bit, :756-766), real `r<%.16g> ID` (:780-800), enum `sNAME ID` (only `--vcd-enums`). std_logic map `UX01ZWLH-`, or `xx01zz01x` w/ `--vcd-4states` (:736-754). Full dump at t=0, deltas later, final timestamp at end (:1000-1041).
- FST (grt-fst.adb:106-119): fstWriterCreate, FileType=VHDL, Pack=LZ4, Timescale=-3×resolution-scale, Version="GHDL FST v0", repack-on-close.
- GHW (grt-waves.adb:320-334): magic `GHDLwave\n` (9B) + hdr-len 16 + ver-major 0 + ver-minor 1 + size/order bytes; sections `DIR\0…EOD\0`, `TAI\0`; values LEB128/SLEB128. Contract explicitly unstable: doc/ghw/index.rst:19-22; read via ghw/libghw.h or ghwdump, or pywellen. Kaitai notes: github.com/nturley/ghw-notes.
- AMS CSV: header `Time,q1,q2'…` (`'dot` suffix for dot-attrs), rows `Put_F64` comma-separated (simul-vhdl_simul.adb:4189-4211,4495-4504).
- Synth `--out=`: raw|dump|dot|none|vhdl|vhdl-ieee|raw-vhdl|raw-vhdl-ieee|verilog, default vhdl (ghdlsynth.adb:172-194,534). `-o=FILE` else stdout. `--stats`→stdout `Statistics for netlists:` + `snames/modules/instances (free:)/nets (free:)/inputs (free:)/params` + `Number of instances (per module)` (netlists.adb:1507-1574). Sim `--stats`→stdout `total/elab/… wall:/user:/sys:` + signal/cycle/process counters (grt-stats.adb:304-367).
- XML: `<?xml …?>` `<root version="0.13">` `<el id kind file line col …>` per IIR node; fields→attributes/subelements (`ref|list-ref|flist-ref|list-id|flist-id`, string8→length+content); schema=src/vhdl/nodes_meta.* (ghdlxml.adb:304-507).
- `--version`: `GHDL <ver> <release>` + ` Compiled with …` + copyright; `version ref|hash` prints hash (ghdlmain.adb:312-358). Doc URLs: ghdl.github.io/ghdl/using/{Simulation,Synthesis,InvokingGHDL,CommandReference}.html, ghw/index.html; clone doc/using/*.rst.

3. PYTHON BINDINGS (audit row: CONFIRMED, refined)
pyGHDL in-repo (pyGHDL/): `pyGHDL.libghdl` low-level ctypes → versioned `libghdl-7_0_0_dev.{so,dll,dylib}` (auto-located via GHDL_PREFIX/VUNIT_GHDL_PATH/GHDL/pyGHDL/lib/which/build-dir; libghdl/__init__.py); `pyGHDL.dom` high-level VHDL DOM on pyVHDLModel (parse+analyze only); `pyGHDL.cli`, `pyGHDL.lsp`. Returns natively: AST/IIR nodes, DOM objects, in-memory diagnostics via errorout_memory.Get_Nbr_Messages/Get_Error_Record (id/group/file/line/offset/length struct). NO simulation-runner/waveform/assert binding — sim results are files/stdio only. Stale-PyPI warning stands: use bundle/upstream, not PyPI `pyghdl`.

4. STDIO-ONLY RESIDUE
Asserts/reports/PSL-failure lines, TEXTIO `output`, `simulation failed`, sim `--stats`, trace/debug (`--disp-time/--trace-signals/--trace-processes/--disp-*`), synth `--stats`, coverage lcov/summary, XML/HTML dumps (no -o flag; outputs.adb defaults null→stdout): only on stdio because GRT has file flags solely for wave/PSL/CSV channels and compile drivers default dumps to stdout. Note trap: runtime diags go to STDOUT (grt-main.adb:120), compile diags to STDERR — never merge blindly.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1) Analyze-stage: pyGHDL.dom/libghdl + errorout_memory for AST/diagnostics (no text scrape). 2) Sim verdicts: exit code + assert-line regex `^(.+):(\d+):(\d+):@(\S+):\((\w[\w ]*) (\w+)\): (.*)$` + `simulation failed`; PSL verdicts from --psl-report JSON summary (skip line-scraping). 3) Waveforms: --fst/--vcd (+--vcd-nodate for determinism) read via pywellen; GHW only via libghw/pywellen (format unstable). 4) Coverage: --coverage-output JSON → `ghdl coverage --format=gcovr -o` or summary. 5) Synth: --out=verilog|vhdl -o= + --stats text (pinned, stable-ish debug grammar). Verified at: clone 428cc4b7 (2026-11-01) ≈ 7.0.0-dev; provision pin oss-cad-suite 20261025 (bundle carries ghdl, no separate pin).
```
