# verilator — output dissection

Dissector ref: prior result 21 (text `handoff-47b05059980973e0155be9cfb0aa1a9f10510fd5bdcb0780969a38c06d08116d-840aa2927b5922f1f80cecb79dfa528cbe273f6990a72e3d5742fd0752f2bf70.txt`, summary `handoff-ca1d22b2fd68045c77508041f149d7c4090aae6bea85ea56785a98a3d604ec4d-840aa2927b5922f1f80cecb79dfa528cbe273f6990a72e3d5742fd0752f2bf70.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `1b27515019d75345552b9256f65f3df6e85a1688`
- Clone date: `2026-11-01`
- Pin: CLONE: 1b27515019d75345552b9256f65f3df6e85a1688, date 2026-11-01 (`git log -1` "Internals: Fix V3Broken check on assignment LHS"). Changes head = "Verilator 5.055 devel", last release "5.054 2026-11-01" (Changes:12-22). DOCS HTML present: /tmp/rocket-tool-docs/verilator-index.html = "Verilator User'
- Doc/source URLs:
  - https://verilator.org/guide/latest/

### Dissector header (verbatim, whitespace-trimmed)

```text
VERILATOR output-capability dissection (REVIEW ONLY, no edits)

CLONE: 1b27515019d75345552b9256f65f3df6e85a1688, date 2026-11-01 (`git log -1` "Internals: Fix V3Broken check on assignment LHS"). Changes head = "Verilator 5.055 devel", last release "5.054 2026-11-01" (Changes:12-22). DOCS HTML present: /tmp/rocket-tool-docs/verilator-index.html = "Verilator User's Guide — Verilator 5.054 documentation". PIN: oss-cad-suite bundle 20261025 (provision_toolchain.sh:55); script asserts only yosys/sby banners, NO verilator banner assert — bundle→verilator version mapping UNVERIFIED. Ambient probe observed Verilator 5.053 (docs/probe-verilator-lint.md:3). Guide root: https://verilator.org/guide/latest/ (named in src/V3Options.cpp:2343).
```

## 1. Result channels

1. RESULT CHANNELS (all outputs land under --Mdir, default obj_dir; docs/guide/files.rst:34-36)

| # | Channel | Producing flag/command | Filename/stream | Kind |
|---|---|---|---|---|
| C1 | lint/compile diagnostics | any verilator run (only output of --lint-only) | stderr | text, deterministic grammar |
| C2 | Verilation Report | any run unless --quiet-stats/--preproc-only | stdout | fixed 3-line text |
| C3 | --version/--help | --version/--help | stdout | text |
| C4 | JSON AST dump | --json-only (or --json-only-output/--json-only-meta-output, which imply it) | <Mdir>/<prefix>.tree.json + <prefix>.tree.meta.json | machine JSON |
| C5 | SARIF diagnostics | --diagnostics-sarif [--diagnostics-sarif-output] | <Mdir>/<prefix>.sarif (default) | machine JSON (SARIF) |
| C6 | stats | --stats / --stats-vars (implies --stats) | <Mdir>/<prefix>__stats.txt (+__stats_dfg_patterns__*.txt) | fixed-section text |
| C7 | waiver file | --waiver-output <file> | user path, .vlt | Verilator config text |
| C8 | idmap | --protect-ids | <Mdir>/<prefix>__idmap.xml | machine XML |
| C9 | C++/SystemC model+makefiles | --cc/--sc [+--exe --build/--binary/--main/--lib-create] | <Mdir>/<prefix>*.h/*.cpp/*.mk, lib<prefix>.a, <prefix> exe | build artifacts |
| C10 | DPI header | --dpi (+hdr always); --dpi-hdr-only = header only, no other output | <Mdir>/<prefix>__Dpi.h (+__Dpi.cpp, __Dpi_Export*.cpp) | C header |
| C11 | coverage.dat | simulated model linked with --coverage-* calls VerilatedCov::write() (usually at $finish/exit) | ./coverage.dat default; overridable +coverage+file / VerilatedContext::coverageFilename() | machine text (SystemC::Coverage-3) |
| C12 | coverage reports | verilator_coverage --annotate/--report/--write/--write-info | annotated src dir; merged.dat; lcov .info; stdout summary | text/machine |
| C13 | waveforms | simulated model with --trace-vcd/--trace-fst/--trace-saif, testbench tfp->open(path) | testbench-chosen path (.vcd/.fst/.saif) | IEEE/binary |
| C14 | sim stdout/stderr + exit | $display/$write/$error/$fatal/$stop/$finish in model | process stdio; exit code | text + code |
| C15 | profiler files | model built --prof-c/--prof-exec/--prof-pgo | gmon.out; profile_exec.dat; profile.vlt | binary/internal |
| C16 | gantt VCD / profcfunc report | verilator_gantt [profile_exec.dat]; verilator_profcfunc gprof.out | verilator_gantt.vcd (default, --vcd to change; --no-vcd off); stdout text | VCD / text |
| C17 | build-internal | -MMD/--skip-identical/--hierarchical/--make json/--debug/--dump-tree* | __ver.d, __verFiles.dat, __hier*, *.mk/__hierMkJsonArgs, *.tree/*.dot/*.vpp, <prefix>.json | internal/debug |
| C18 | exit code | all | process status | 0 / 1 / make-rc |
| — | in-process API returns, DBs | NONE for the verilator binary (C++-only generated-model API; no server/DB) | — | — |

REMOVED (do not design for): --xml-only/--xml-output removed in 5.046 (docs/guide/exe_verilator.rst:2604-2615); --prof-threads removed 5.020; --trace-threads no-op since 5.048. --cdc has NO option anymore (zero hits in src/V3Options.*) though docs/guide/files.rst:119-120 still lists `<prefix>__cdc.txt (from --cdc)` — stale doc row, file is NOT produced; do not consume.

## 2. Format grammars

2. FORMAT GRAMMARS

C1 stderr diagnostics. Prefix writer src/V3Error.cpp:71-82: `%Error: ` (plain/fatal/many), `%Error-<CODE>: ` (promoted), `%Warning-<CODE>: ` (default), `-Info: `, `-arning-suppressed-<CODE>: ` (debug). Location writer src/V3FileLine.cpp:368-370: `filename:lastLineno:firstColumn` (NOTE: LAST lineno, FIRST column). Assembly src/V3FileLine.cpp:403-408: `<ctx><FileLine "path:line:col">: <msg>\n` + primary context. Context (src/V3FileLine.cpp:476-494, --no-context disables): `␣␣12 | source text\n␣␣␣␣␣␣| ␣␣^~~\n` (5-wide line no, `|`, caret+`~` span). Trailer (src/V3Error.cpp:341-352): `%Error: Exiting due to N error(s)[, M warning(s)]\n` or `%Error: Exiting due to N warning(s)\n`; --quiet-exit suppresses (V3Options + exe_verilator.rst:1861). Doc-link line appended once per code: `... For warning description see https://verilator.org/warn/CODE?rev=v5.054...` (V3Error.cpp:215-219 pattern + probe). Dedup: identical first-lines printed once (V3Error.cpp:178). --error-limit default 50, errors only (exe_verilator.rst:713-716).
Real shape (probe-verilator-lint.md:14-16, verified 5.053): `%Warning-WIDTHTRUNC: t.v:16:21: Operator TRUNC ...` + context + doc-link + `%Error: Exiting due to 1 warning(s)`. Adapter regex (probe): `^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):`, skip context/caret/`... note:`/doc-link lines.

C2 stdout Verilation Report (src/V3StatsReport.cpp:258-288, suppressed by --quiet-stats/--preproc-only, Verilator.cpp:929):
```
- V e r i l a t i o n   R e p o r t: Verilator 5.054 ... rev ...
- Verilator: Built from 0.012 MB sources in 3 modules, into 0.500 MB in 12 C++ files needing 0.100 MB
- Verilator: Walltime 1.234 s (elab=0.5, cvt=0.5, bld=0.2); cpu 2.000 s on 4 threads; allocated 123.456 MB
```
fixed 3 sig figs, MB/sec units, `; allocated` omitted if 0. Machine-parseable but informational only. --version stdout: `<PACKAGE_STRING> rev <DTVERSION_rev>` e.g. `Verilator 5.054 ... rev ...` (V3Options.cpp:1118-1122, showVersion :2331-2333).

C4 JSON AST. Emission: Verilator.cpp:137-147 (tree.json), :759-765 (meta, also on --dump-tree-json). Defaults `<Mdir>/<prefix>.tree.json`, `.tree.meta.json`; explicit paths bypass Mdir. Disables aggressive transforms, dumps FINAL AST only (exe_verilator.rst:1285-1296; "format still evolving"). Node (V3AstNodes.cpp:540-558): `{"type":"MODULE","name":"t","addr":"(F)","loc":"d,7:8,7:9", ...dtypep/child-arrays...}`; `loc` = `<fileletters>,<firstLine>:<firstCol>,<lastLine>:<lastCol>` (V3AstNodes.cpp:154-160); letters = base26 a,b..z,ba.. of file index (V3FileLine.cpp:44-56, `a`=index0); `addr`/`dtypep`/all `*p` = `(B)`-style ids via ptrToId base26 in parens, `0`=null (V3Global.cpp:227-242); --no-json-ids restores hex addresses; --no-json-edit-nums drops editNum (VL_DEBUG only). Meta file (V3Ast.cpp:1561-1572): `{"files": {"d":{"filename":"...","realpath":"...","language":"SystemVerilog"}}, "pointers": {"(B)":"0x..."}, "ptrFieldNames": [...]}` (V3FileLine.cpp:80-97; V3Global.cpp:203-225). Real example (test_regress/t/t_json_only_first.out): `{"type":"NETLIST","name":"$root","addr":"(B)","loc":"a,0:0,0:0","timeunit":"1ps","timeprecision":"1ps","typeTablep":"(C)",... "modulesp": [ {"type":"MODULE","name":"t",...,"stmtsp": [ {"type":"VAR","name":"q",...,"direction":"OUTPUT","varType":"WIRE","dtypeName":"logic"}, ...]}]}`. Golden tests: t_json_only_*.py compare byte-identical with --no-json-edit-nums. No .json-schema file in repo — grammar IS the writers + goldens.

C5 SARIF. Written only if --diagnostics-sarif (V3DiagSarif::output, V3DiagSarif.cpp:191-195; called unconditionally at Verilator.cpp:~918 but returns early). Default path makeDir/prefix.sarif (V3Options.h:733-735). Shape (V3DiagSarif.cpp:42-140): standard SARIF 2.1 envelope; rules[] = {id: CODE ascii, helpUri: code.url()}; results[] level ∈ none/error/warning; message {text (context-stripped), markdown (fenced full)}; locations[].physicalLocation {artifactLocation {uri: file:<rel>+uriBaseId %srcroot% | file://<abs>}, region {sourceLanguage: systemverilog, startLine, startColumn, [endLine,] endColumn, snippit {text, markdown}}}; relatedLocations for __WARNRELATED. Consume with any SARIF reader (sarif-tools, MS viewer links in exe_verilator.rst:578-585).

C6 stats (V3StatsReport.cpp:233-256 file; 179-187 layout): `Verilator Statistics Report\n\nInformation:\n  Version: ...\n  Arguments: ...\n  Build jobs: ..\n  Verilate jobs: ..\n` then `Global Statistics:` (2-space indent, left-just name col, `%9.?.3f`-ish right-just values via V3Statistic::dump `setw(9) fixed setprecision(precision)`), `Performance Statistics:` same, `Stage Statistics:` matrix (`  Stat ...` header, `  -------- ...` rule, one row per stat, 10-wide cols per stage). --stats-vars adds per-variable size rows. Numbers: counts as `N.000`, MB/sec plainly labeled in names (e.g. `Peak Memory Usage (MB)`). Human-oriented but section-stable; parse `  <name><pad><value>` lines only.

C7 waiver .vlt (V3Waiver.cpp:73-104): header `// DESCRIPTION: Verilator output: Waivers generated with --waiver-output`, `` `verilator_config ``, then COMMENTED-OUT suggestions `// lint_off -rule CODE -file "*<path>" -match "<glob1stline>*"`, or `// No waivers needed - great!`. Multiline opt --waiver-multiline. Must uncomment to use; order: .vlt before waived files on cmdline.

C8 idmap (src/V3File.cpp:1123-1137): `<?xml ...?>\n<!-- DESCRIPTION: Verilator output: XML representation of netlist -->\n<verilator_id_map>\n<map from="<hashed>" to="<original>"/>\n...</verilator_id_map>`. NOTE from=hashed, to=original (reverse of intuition).

C11 coverage.dat (include/verilated_cov.cpp:353-424): header `# SystemC::Coverage-3\n`, then per-event lines `C '<\x01key\x02val...>' <uint64count>\n` where keys are SHORT codes (include/verilated_cov_key.h:59-77: f filename, l lineno, n column, o comment, t type, h hier, w weight, s thresh, S linescov, P per_instance, B/Bt bins, C/Cb cross, Ff/Ft/Fv/Fg fsm, Gw group weight) joined as \x01<KEY>\x02<escaped val>; `page` key additionally synthesizes `t` from `sp_<type>/...`. Hier collapsing merges instances with `*` wildcards (combineHier :163-198) unless --coverage-per-instance. Real (t_assert_ctl_arg.dat.out, ^A=\x01 ^B=\x02): `C '^Af^Bt/t_assert_ctl_arg.v^Al^B105^An^B31^At^Buser^Apage^Bv_user/t^Ao^Bcover_simple_immediate_105^Ah^Btop.t.cover_simple_immediate_105' 1`. Default filename coverage.dat (verilated.cpp:3179); runtime override `+coverage+file <f>`-family/VerilatedContext::coverageFilename (verilated.cpp:3282-3288,3676).

C12 verilator_coverage (perl wrapper bin/verilator_coverage → compiled backend; docs/guide/exe_verilator_coverage.rst): --annotate <dir> writes annotated sources, each line prefixed `<mark><count6>` where mark ∈ {` `(all≥min), `%`(all<min), `~`(mixed)} and with --annotate-points extra `point: type=<line|branch|expr|...>` lines marked `+`(≥min)/`-`(<min); default min 10 (--annotate-min). --report summary|hier|hierarchy → stdout; --write merged.dat (same Coverage-3 grammar, counts summed); --write-info .info (lcov: TN:/SF:/DA:/BRDA:/LF:/LH:…; loses comments). --filter-type regex over toggle|line|branch|expr|covergroup|user|fsm_state|fsm_arc.

C13 traces: VCD = IEEE 1364 text (`$version Generated by VerilatedVcd $end`, `$timescale N units $end`, `$scope/$var/$upscope`, `$enddefinitions $end`, `#t`/`v<id>`/`b<vec> <id>` records; include/verilated_vcd_c.cpp:117-129,356-449). FST = GTKWave binary (bundled writer include/fstcpp + verilated_fst_c.*). SAIF = IEEE 1801-2018 Annex I text (`(SAIFILE (TIMESCALE ..) (DURATION ..) (INSTANCE path (NET ...))...)`; verilated_saif_c.cpp:301-360). Filename is 100% testbench-chosen via tfp->open("...") — adapter must know the harness convention; --trace-max-array 32 / --trace-max-width 4096 defaults bound size.

C14 sim runtime: `VL_PRINTF`-based (stdout): $display passthrough; fatal `$error`/assert → `%Error: <file>:<line>: <msg>\nAborting...\n` + exit(1) (abort() if Verilated::debug) via vl_fatal (verilated.cpp:200-223); `CODE: msg` prefix form yields `%Error-CODE: file:line: msg` (verilated.cpp:139-160). $stop → `Stopped...` path + gotFinish; testbench main() decides final exit code (gotError()/gotFinish() polling, verilated.h:722-727) — exit code is HARNESS-defined, never trust alone; parse `%Error`.

C15/C16: profile_exec.dat = versioned BINARY for verilator_gantt only (docs "non-human-friendly", simulating.rst:517); gantt default out verilator_gantt.vcd with signals mtasks/CPU/thread#_mtask/predicted_thread#_mtask (exe_verilator_gantt.rst:40-68,88-100). gmon.out = stock gprof; profcfunc prints per-Verilog-block % report on stdout. profile.vlt = PGO feed consumed by a later verilator run (internal; no adapter grammar needed).

C18 exit codes: 0 = clean through end of main (Verilator.cpp:880-936; note main returns void → 0). 1 = any error OR fatal warning via abortIfErrors/abortIfWarnings→v3fatalMany→vlAbortOrExit→vlExit(1) (V3Error.cpp:341-352, V3Error.h:629-632, V3Global.cpp:73-75; `::_exit(1)` from MT workers). --build/--hier failures propagate make's rc with `%Error: '<cmd>' exited with N` (Verilator.cpp:852-878). Internal error under --debug = std::abort/SIGABRT (V3Error.cpp:84-88). Runtime sim: exit(1) on $fatal (above), else harness-defined.

## 3. Python bindings verdict

3. PYTHON BINDINGS: audit row CONFIRMED with one correction. Repo has NO Python API: no setup.py/pyproject, no pybind/SWIG, Python used only for tests/docs (install.rst:163-182; test .py drivers). Only Python-adjacent fact: README.rst:141-144 lists Cocotb as the supported Python-testbench route (external lib, drives the compiled model via VPI — not a verilator result binding). pyverilator-stale claim is an upstream-registry fact, not repo-verifiable here; nothing in-repo contradicts "reject". So: bindings = none; verdict KEEP-STRUCTURED stands. CORRECTION to audit row: `--xml-only (docs/xml.rst)` is DEAD — xml-only removed in 5.046, there is no docs xml.rst; `--json-only` (5.x, incl. bundle-era 5.053/5.054) is the structured AST path. Gap note "--xml-only vs --json-only unconfirmed" is now RESOLVED: json-only only.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (no file equivalent): (a) C1 diagnostics UNLESS --diagnostics-sarif is passed — SARIF covers file:line:col+message+rule but strips nothing else; waiver text/context lines remain stdio-only. (b) C2 Verilation Report — informational walltime/size summary; --quiet-stats kills it, no file form. (c) Sim-harness stdout ($display text, test PASS/FAIL prints) and runtime %Error context — harness-defined, no canonical file. (d) -E preprocessed output goes to stdout (preprocOnly path skips all file emission; Verilator.cpp:753,929) — verify destination with one run before relying. (e) verilator_coverage --report and verilator_profcfunc reports print to stdout (redirect to capture; --write/--write-info are the file forms for coverage). WHY: Verilator's philosophy is diagnostics-on-stderr + artifacts-in-Mdir; SARIF/JSON/stats exist precisely to shrink this residue, but lint verdicts without --diagnostics-sarif and all sim-console verdicts remain parse-stdio.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text):
No bindings exist, so ranked file-first:
 1. check.syntax (lint): `--lint-only --diagnostics-sarif` → parse `<prefix>.sarif` (machine grammar, rule+loc native); FALLBACK C1 regex `^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):` (probe-verified). Verdict from parsed errors, never exit code (warnings-only exits 1). Pin: bundle 20261025 (mapping unverified) — evidence verified at clone 1b27515 (post-5.054) + docs 5.054 + probe 5.053; SARIF shape stable across these.
 2. AST consumers: `--json-only` → `.tree.json` + `.tree.meta.json` (+ `--no-json-ids`? no — KEEP ids for stability; add `--no-json-edit-nums` for byte-stable goldens). Note docs warn "format still evolving".
 3. simulate.hdl: `--binary/--exe --build --trace-fst --coverage-*` → parse FST/VCD (pywellen per audit), coverage.dat via verilator_coverage --write-info (lcov) or Coverage-3 grammar, and sim-stdio `%Error` scan; harness exit code untrusted.
 4. stats/size gates: `--stats` → `__stats.txt` Global section.
OUT OF SCOPE for adapters (loud unmapped): C9/C10/C17 build artifacts, C15 profiler binaries, C7 waivers (input-side), C8 idmap (only with --protect-ids), C16 gantt (perf debug), --dump-tree* debug dumps, __cdc.txt (stale doc, never emitted).
Version evidence: verified at clone SHA 1b27515019d75345552b9256f65f3df6e85a1688 @2026-11-01 (=5.055-devel, one commit past 5.054 release), docs snapshot 5.054, engine probe 5.053. Re-verify SARIF/JSON keys when bundle rev moves (JSON explicitly evolving).

## Weak-evidence gaps (flagged by dissector)

- | C17 | build-internal | -MMD/--skip-identical/--hierarchical/--make json/--debug/--dump-tree* | __ver.d, __verFiles.dat, __hier*, *.mk/__hierMkJsonArgs, *.tree/*.dot/*.vpp, <prefix>.json | internal/debug |
- C1 stderr diagnostics. Prefix writer src/V3Error.cpp:71-82: `%Error: ` (plain/fatal/many), `%Error-<CODE>: ` (promoted), `%Warning-<CODE>: ` (default), `-Info: `, `-arning-suppressed-<CODE>: ` (debug). Location writer src/V3FileLine.cpp:368-370: `filename:last
- C4 JSON AST. Emission: Verilator.cpp:137-147 (tree.json), :759-765 (meta, also on --dump-tree-json). Defaults `<Mdir>/<prefix>.tree.json`, `.tree.meta.json`; explicit paths bypass Mdir. Disables aggressive transforms, dumps FINAL AST only (exe_verilator.rst:12
- C14 sim runtime: `VL_PRINTF`-based (stdout): $display passthrough; fatal `$error`/assert → `%Error: <file>:<line>: <msg>\nAborting...\n` + exit(1) (abort() if Verilated::debug) via vl_fatal (verilated.cpp:200-223); `CODE: msg` prefix form yields `%Error-CODE:
- C18 exit codes: 0 = clean through end of main (Verilator.cpp:880-936; note main returns void → 0). 1 = any error OR fatal warning via abortIfErrors/abortIfWarnings→v3fatalMany→vlAbortOrExit→vlExit(1) (V3Error.cpp:341-352, V3Error.h:629-632, V3Global.cpp:73-75;
- 3. PYTHON BINDINGS: audit row CONFIRMED with one correction. Repo has NO Python API: no setup.py/pyproject, no pybind/SWIG, Python used only for tests/docs (install.rst:163-182; test .py drivers). Only Python-adjacent fact: README.rst:141-144 lists Cocotb as t

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
VERILATOR output-capability dissection (REVIEW ONLY, no edits)

CLONE: 1b27515019d75345552b9256f65f3df6e85a1688, date 2026-11-01 (`git log -1` "Internals: Fix V3Broken check on assignment LHS"). Changes head = "Verilator 5.055 devel", last release "5.054 2026-11-01" (Changes:12-22). DOCS HTML present: /tmp/rocket-tool-docs/verilator-index.html = "Verilator User's Guide — Verilator 5.054 documentation". PIN: oss-cad-suite bundle 20261025 (provision_toolchain.sh:55); script asserts only yosys/sby banners, NO verilator banner assert — bundle→verilator version mapping UNVERIFIED. Ambient probe observed Verilator 5.053 (docs/probe-verilator-lint.md:3). Guide root: https://verilator.org/guide/latest/ (named in src/V3Options.cpp:2343).

1. RESULT CHANNELS (all outputs land under --Mdir, default obj_dir; docs/guide/files.rst:34-36)

| # | Channel | Producing flag/command | Filename/stream | Kind |
|---|---|---|---|---|
| C1 | lint/compile diagnostics | any verilator run (only output of --lint-only) | stderr | text, deterministic grammar |
| C2 | Verilation Report | any run unless --quiet-stats/--preproc-only | stdout | fixed 3-line text |
| C3 | --version/--help | --version/--help | stdout | text |
| C4 | JSON AST dump | --json-only (or --json-only-output/--json-only-meta-output, which imply it) | <Mdir>/<prefix>.tree.json + <prefix>.tree.meta.json | machine JSON |
| C5 | SARIF diagnostics | --diagnostics-sarif [--diagnostics-sarif-output] | <Mdir>/<prefix>.sarif (default) | machine JSON (SARIF) |
| C6 | stats | --stats / --stats-vars (implies --stats) | <Mdir>/<prefix>__stats.txt (+__stats_dfg_patterns__*.txt) | fixed-section text |
| C7 | waiver file | --waiver-output <file> | user path, .vlt | Verilator config text |
| C8 | idmap | --protect-ids | <Mdir>/<prefix>__idmap.xml | machine XML |
| C9 | C++/SystemC model+makefiles | --cc/--sc [+--exe --build/--binary/--main/--lib-create] | <Mdir>/<prefix>*.h/*.cpp/*.mk, lib<prefix>.a, <prefix> exe | build artifacts |
| C10 | DPI header | --dpi (+hdr always); --dpi-hdr-only = header only, no other output | <Mdir>/<prefix>__Dpi.h (+__Dpi.cpp, __Dpi_Export*.cpp) | C header |
| C11 | coverage.dat | simulated model linked with --coverage-* calls VerilatedCov::write() (usually at $finish/exit) | ./coverage.dat default; overridable +coverage+file / VerilatedContext::coverageFilename() | machine text (SystemC::Coverage-3) |
| C12 | coverage reports | verilator_coverage --annotate/--report/--write/--write-info | annotated src dir; merged.dat; lcov .info; stdout summary | text/machine |
| C13 | waveforms | simulated model with --trace-vcd/--trace-fst/--trace-saif, testbench tfp->open(path) | testbench-chosen path (.vcd/.fst/.saif) | IEEE/binary |
| C14 | sim stdout/stderr + exit | $display/$write/$error/$fatal/$stop/$finish in model | process stdio; exit code | text + code |
| C15 | profiler files | model built --prof-c/--prof-exec/--prof-pgo | gmon.out; profile_exec.dat; profile.vlt | binary/internal |
| C16 | gantt VCD / profcfunc report | verilator_gantt [profile_exec.dat]; verilator_profcfunc gprof.out | verilator_gantt.vcd (default, --vcd to change; --no-vcd off); stdout text | VCD / text |
| C17 | build-internal | -MMD/--skip-identical/--hierarchical/--make json/--debug/--dump-tree* | __ver.d, __verFiles.dat, __hier*, *.mk/__hierMkJsonArgs, *.tree/*.dot/*.vpp, <prefix>.json | internal/debug |
| C18 | exit code | all | process status | 0 / 1 / make-rc |
| — | in-process API returns, DBs | NONE for the verilator binary (C++-only generated-model API; no server/DB) | — | — |

REMOVED (do not design for): --xml-only/--xml-output removed in 5.046 (docs/guide/exe_verilator.rst:2604-2615); --prof-threads removed 5.020; --trace-threads no-op since 5.048. --cdc has NO option anymore (zero hits in src/V3Options.*) though docs/guide/files.rst:119-120 still lists `<prefix>__cdc.txt (from --cdc)` — stale doc row, file is NOT produced; do not consume.

2. FORMAT GRAMMARS

C1 stderr diagnostics. Prefix writer src/V3Error.cpp:71-82: `%Error: ` (plain/fatal/many), `%Error-<CODE>: ` (promoted), `%Warning-<CODE>: ` (default), `-Info: `, `-arning-suppressed-<CODE>: ` (debug). Location writer src/V3FileLine.cpp:368-370: `filename:lastLineno:firstColumn` (NOTE: LAST lineno, FIRST column). Assembly src/V3FileLine.cpp:403-408: `<ctx><FileLine "path:line:col">: <msg>\n` + primary context. Context (src/V3FileLine.cpp:476-494, --no-context disables): `␣␣12 | source text\n␣␣␣␣␣␣| ␣␣^~~\n` (5-wide line no, `|`, caret+`~` span). Trailer (src/V3Error.cpp:341-352): `%Error: Exiting due to N error(s)[, M warning(s)]\n` or `%Error: Exiting due to N warning(s)\n`; --quiet-exit suppresses (V3Options + exe_verilator.rst:1861). Doc-link line appended once per code: `... For warning description see https://verilator.org/warn/CODE?rev=v5.054...` (V3Error.cpp:215-219 pattern + probe). Dedup: identical first-lines printed once (V3Error.cpp:178). --error-limit default 50, errors only (exe_verilator.rst:713-716).
Real shape (probe-verilator-lint.md:14-16, verified 5.053): `%Warning-WIDTHTRUNC: t.v:16:21: Operator TRUNC ...` + context + doc-link + `%Error: Exiting due to 1 warning(s)`. Adapter regex (probe): `^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):`, skip context/caret/`... note:`/doc-link lines.

C2 stdout Verilation Report (src/V3StatsReport.cpp:258-288, suppressed by --quiet-stats/--preproc-only, Verilator.cpp:929):
```
- V e r i l a t i o n   R e p o r t: Verilator 5.054 ... rev ...
- Verilator: Built from 0.012 MB sources in 3 modules, into 0.500 MB in 12 C++ files needing 0.100 MB
- Verilator: Walltime 1.234 s (elab=0.5, cvt=0.5, bld=0.2); cpu 2.000 s on 4 threads; allocated 123.456 MB
```
fixed 3 sig figs, MB/sec units, `; allocated` omitted if 0. Machine-parseable but informational only. --version stdout: `<PACKAGE_STRING> rev <DTVERSION_rev>` e.g. `Verilator 5.054 ... rev ...` (V3Options.cpp:1118-1122, showVersion :2331-2333).

C4 JSON AST. Emission: Verilator.cpp:137-147 (tree.json), :759-765 (meta, also on --dump-tree-json). Defaults `<Mdir>/<prefix>.tree.json`, `.tree.meta.json`; explicit paths bypass Mdir. Disables aggressive transforms, dumps FINAL AST only (exe_verilator.rst:1285-1296; "format still evolving"). Node (V3AstNodes.cpp:540-558): `{"type":"MODULE","name":"t","addr":"(F)","loc":"d,7:8,7:9", ...dtypep/child-arrays...}`; `loc` = `<fileletters>,<firstLine>:<firstCol>,<lastLine>:<lastCol>` (V3AstNodes.cpp:154-160); letters = base26 a,b..z,ba.. of file index (V3FileLine.cpp:44-56, `a`=index0); `addr`/`dtypep`/all `*p` = `(B)`-style ids via ptrToId base26 in parens, `0`=null (V3Global.cpp:227-242); --no-json-ids restores hex addresses; --no-json-edit-nums drops editNum (VL_DEBUG only). Meta file (V3Ast.cpp:1561-1572): `{"files": {"d":{"filename":"...","realpath":"...","language":"SystemVerilog"}}, "pointers": {"(B)":"0x..."}, "ptrFieldNames": [...]}` (V3FileLine.cpp:80-97; V3Global.cpp:203-225). Real example (test_regress/t/t_json_only_first.out): `{"type":"NETLIST","name":"$root","addr":"(B)","loc":"a,0:0,0:0","timeunit":"1ps","timeprecision":"1ps","typeTablep":"(C)",... "modulesp": [ {"type":"MODULE","name":"t",...,"stmtsp": [ {"type":"VAR","name":"q",...,"direction":"OUTPUT","varType":"WIRE","dtypeName":"logic"}, ...]}]}`. Golden tests: t_json_only_*.py compare byte-identical with --no-json-edit-nums. No .json-schema file in repo — grammar IS the writers + goldens.

C5 SARIF. Written only if --diagnostics-sarif (V3DiagSarif::output, V3DiagSarif.cpp:191-195; called unconditionally at Verilator.cpp:~918 but returns early). Default path makeDir/prefix.sarif (V3Options.h:733-735). Shape (V3DiagSarif.cpp:42-140): standard SARIF 2.1 envelope; rules[] = {id: CODE ascii, helpUri: code.url()}; results[] level ∈ none/error/warning; message {text (context-stripped), markdown (fenced full)}; locations[].physicalLocation {artifactLocation {uri: file:<rel>+uriBaseId %srcroot% | file://<abs>}, region {sourceLanguage: systemverilog, startLine, startColumn, [endLine,] endColumn, snippit {text, markdown}}}; relatedLocations for __WARNRELATED. Consume with any SARIF reader (sarif-tools, MS viewer links in exe_verilator.rst:578-585).

C6 stats (V3StatsReport.cpp:233-256 file; 179-187 layout): `Verilator Statistics Report\n\nInformation:\n  Version: ...\n  Arguments: ...\n  Build jobs: ..\n  Verilate jobs: ..\n` then `Global Statistics:` (2-space indent, left-just name col, `%9.?.3f`-ish right-just values via V3Statistic::dump `setw(9) fixed setprecision(precision)`), `Performance Statistics:` same, `Stage Statistics:` matrix (`  Stat ...` header, `  -------- ...` rule, one row per stat, 10-wide cols per stage). --stats-vars adds per-variable size rows. Numbers: counts as `N.000`, MB/sec plainly labeled in names (e.g. `Peak Memory Usage (MB)`). Human-oriented but section-stable; parse `  <name><pad><value>` lines only.

C7 waiver .vlt (V3Waiver.cpp:73-104): header `// DESCRIPTION: Verilator output: Waivers generated with --waiver-output`, `` `verilator_config ``, then COMMENTED-OUT suggestions `// lint_off -rule CODE -file "*<path>" -match "<glob1stline>*"`, or `// No waivers needed - great!`. Multiline opt --waiver-multiline. Must uncomment to use; order: .vlt before waived files on cmdline.

C8 idmap (src/V3File.cpp:1123-1137): `<?xml ...?>\n<!-- DESCRIPTION: Verilator output: XML representation of netlist -->\n<verilator_id_map>\n<map from="<hashed>" to="<original>"/>\n...</verilator_id_map>`. NOTE from=hashed, to=original (reverse of intuition).

C11 coverage.dat (include/verilated_cov.cpp:353-424): header `# SystemC::Coverage-3\n`, then per-event lines `C '<\x01key\x02val...>' <uint64count>\n` where keys are SHORT codes (include/verilated_cov_key.h:59-77: f filename, l lineno, n column, o comment, t type, h hier, w weight, s thresh, S linescov, P per_instance, B/Bt bins, C/Cb cross, Ff/Ft/Fv/Fg fsm, Gw group weight) joined as \x01<KEY>\x02<escaped val>; `page` key additionally synthesizes `t` from `sp_<type>/...`. Hier collapsing merges instances with `*` wildcards (combineHier :163-198) unless --coverage-per-instance. Real (t_assert_ctl_arg.dat.out, ^A=\x01 ^B=\x02): `C '^Af^Bt/t_assert_ctl_arg.v^Al^B105^An^B31^At^Buser^Apage^Bv_user/t^Ao^Bcover_simple_immediate_105^Ah^Btop.t.cover_simple_immediate_105' 1`. Default filename coverage.dat (verilated.cpp:3179); runtime override `+coverage+file <f>`-family/VerilatedContext::coverageFilename (verilated.cpp:3282-3288,3676).

C12 verilator_coverage (perl wrapper bin/verilator_coverage → compiled backend; docs/guide/exe_verilator_coverage.rst): --annotate <dir> writes annotated sources, each line prefixed `<mark><count6>` where mark ∈ {` `(all≥min), `%`(all<min), `~`(mixed)} and with --annotate-points extra `point: type=<line|branch|expr|...>` lines marked `+`(≥min)/`-`(<min); default min 10 (--annotate-min). --report summary|hier|hierarchy → stdout; --write merged.dat (same Coverage-3 grammar, counts summed); --write-info .info (lcov: TN:/SF:/DA:/BRDA:/LF:/LH:…; loses comments). --filter-type regex over toggle|line|branch|expr|covergroup|user|fsm_state|fsm_arc.

C13 traces: VCD = IEEE 1364 text (`$version Generated by VerilatedVcd $end`, `$timescale N units $end`, `$scope/$var/$upscope`, `$enddefinitions $end`, `#t`/`v<id>`/`b<vec> <id>` records; include/verilated_vcd_c.cpp:117-129,356-449). FST = GTKWave binary (bundled writer include/fstcpp + verilated_fst_c.*). SAIF = IEEE 1801-2018 Annex I text (`(SAIFILE (TIMESCALE ..) (DURATION ..) (INSTANCE path (NET ...))...)`; verilated_saif_c.cpp:301-360). Filename is 100% testbench-chosen via tfp->open("...") — adapter must know the harness convention; --trace-max-array 32 / --trace-max-width 4096 defaults bound size.

C14 sim runtime: `VL_PRINTF`-based (stdout): $display passthrough; fatal `$error`/assert → `%Error: <file>:<line>: <msg>\nAborting...\n` + exit(1) (abort() if Verilated::debug) via vl_fatal (verilated.cpp:200-223); `CODE: msg` prefix form yields `%Error-CODE: file:line: msg` (verilated.cpp:139-160). $stop → `Stopped...` path + gotFinish; testbench main() decides final exit code (gotError()/gotFinish() polling, verilated.h:722-727) — exit code is HARNESS-defined, never trust alone; parse `%Error`.

C15/C16: profile_exec.dat = versioned BINARY for verilator_gantt only (docs "non-human-friendly", simulating.rst:517); gantt default out verilator_gantt.vcd with signals mtasks/CPU/thread#_mtask/predicted_thread#_mtask (exe_verilator_gantt.rst:40-68,88-100). gmon.out = stock gprof; profcfunc prints per-Verilog-block % report on stdout. profile.vlt = PGO feed consumed by a later verilator run (internal; no adapter grammar needed).

C18 exit codes: 0 = clean through end of main (Verilator.cpp:880-936; note main returns void → 0). 1 = any error OR fatal warning via abortIfErrors/abortIfWarnings→v3fatalMany→vlAbortOrExit→vlExit(1) (V3Error.cpp:341-352, V3Error.h:629-632, V3Global.cpp:73-75; `::_exit(1)` from MT workers). --build/--hier failures propagate make's rc with `%Error: '<cmd>' exited with N` (Verilator.cpp:852-878). Internal error under --debug = std::abort/SIGABRT (V3Error.cpp:84-88). Runtime sim: exit(1) on $fatal (above), else harness-defined.

3. PYTHON BINDINGS: audit row CONFIRMED with one correction. Repo has NO Python API: no setup.py/pyproject, no pybind/SWIG, Python used only for tests/docs (install.rst:163-182; test .py drivers). Only Python-adjacent fact: README.rst:141-144 lists Cocotb as the supported Python-testbench route (external lib, drives the compiled model via VPI — not a verilator result binding). pyverilator-stale claim is an upstream-registry fact, not repo-verifiable here; nothing in-repo contradicts "reject". So: bindings = none; verdict KEEP-STRUCTURED stands. CORRECTION to audit row: `--xml-only (docs/xml.rst)` is DEAD — xml-only removed in 5.046, there is no docs xml.rst; `--json-only` (5.x, incl. bundle-era 5.053/5.054) is the structured AST path. Gap note "--xml-only vs --json-only unconfirmed" is now RESOLVED: json-only only.

4. STDIO-ONLY RESIDUE (no file equivalent): (a) C1 diagnostics UNLESS --diagnostics-sarif is passed — SARIF covers file:line:col+message+rule but strips nothing else; waiver text/context lines remain stdio-only. (b) C2 Verilation Report — informational walltime/size summary; --quiet-stats kills it, no file form. (c) Sim-harness stdout ($display text, test PASS/FAIL prints) and runtime %Error context — harness-defined, no canonical file. (d) -E preprocessed output goes to stdout (preprocOnly path skips all file emission; Verilator.cpp:753,929) — verify destination with one run before relying. (e) verilator_coverage --report and verilator_profcfunc reports print to stdout (redirect to capture; --write/--write-info are the file forms for coverage). WHY: Verilator's philosophy is diagnostics-on-stderr + artifacts-in-Mdir; SARIF/JSON/stats exist precisely to shrink this residue, but lint verdicts without --diagnostics-sarif and all sim-console verdicts remain parse-stdio.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text):
No bindings exist, so ranked file-first:
 1. check.syntax (lint): `--lint-only --diagnostics-sarif` → parse `<prefix>.sarif` (machine grammar, rule+loc native); FALLBACK C1 regex `^%((?:Error)|(Warning)-([A-Z0-9_]+)):\s*(.+?):(\d+):(\d+):` (probe-verified). Verdict from parsed errors, never exit code (warnings-only exits 1). Pin: bundle 20261025 (mapping unverified) — evidence verified at clone 1b27515 (post-5.054) + docs 5.054 + probe 5.053; SARIF shape stable across these.
 2. AST consumers: `--json-only` → `.tree.json` + `.tree.meta.json` (+ `--no-json-ids`? no — KEEP ids for stability; add `--no-json-edit-nums` for byte-stable goldens). Note docs warn "format still evolving".
 3. simulate.hdl: `--binary/--exe --build --trace-fst --coverage-*` → parse FST/VCD (pywellen per audit), coverage.dat via verilator_coverage --write-info (lcov) or Coverage-3 grammar, and sim-stdio `%Error` scan; harness exit code untrusted.
 4. stats/size gates: `--stats` → `__stats.txt` Global section.
OUT OF SCOPE for adapters (loud unmapped): C9/C10/C17 build artifacts, C15 profiler binaries, C7 waivers (input-side), C8 idmap (only with --protect-ids), C16 gantt (perf debug), --dump-tree* debug dumps, __cdc.txt (stale doc, never emitted).
Version evidence: verified at clone SHA 1b27515019d75345552b9256f65f3df6e85a1688 @2026-11-01 (=5.055-devel, one commit past 5.054 release), docs snapshot 5.054, engine probe 5.053. Re-verify SARIF/JSON keys when bundle rev moves (JSON explicitly evolving).
```
