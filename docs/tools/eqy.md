# eqy — output dissection

Dissector ref: prior result 3 (text `handoff-0459123567390b9296e9a198fb53d39900473e557f16bdd4dd04e0162e3997e1-7c70a18dff15ff874e79d214a2bd796502c005878d3f6ba3ba551c7af7243022.txt`, summary `handoff-81617ed26c0ec9fe70dab6995a61177efa6edd5343b7ab457180fb914c658378-7c70a18dff15ff874e79d214a2bd796502c005878d3f6ba3ba551c7af7243022.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `33015166c47398dff1ac72a699f4212891bb0618`
- Clone date: `2026-10-27`
- Pin: PIN/VERSION: no eqy-specific pin in rocket-engine/scripts/provision_toolchain.sh; eqy ships inside oss-cad-suite bundle pin 20261025 (provision-sources.md §1 lists eqy in bundle). eqy --version prints `EQY $(git describe)` (Makefile); docs require a matching Yosys release + matching SBY (docs/source
- Doc/source URLs:
  - https://github.com/YosysHQ/eqy

### Dissector header (verbatim, whitespace-trimmed)

```text
EQY OUTPUT DISSECTION (review-only; no edits made)

CLONE: /tmp/rocket-tool-src/eqy/ @ SHA 33015166c47398dff1ac72a699f4212891bb0618, date 2026-10-27 (`git rev-parse HEAD`, `git log -1 --format=%cs`).
DOCS HTML: /tmp/rocket-tool-docs/ contains NO eqy file → fell back to in-repo docs (docs/source/*.rst) + repo-cited upstream URLs, per instructions.
PIN/VERSION: no eqy-specific pin in rocket-engine/scripts/provision_toolchain.sh; eqy ships inside oss-cad-suite bundle pin 20261025 (provision-sources.md §1 lists eqy in bundle). eqy --version prints `EQY $(git describe)` (Makefile); docs require a matching Yosys release + matching SBY (docs/source/install.rst:35-47). Verified at clone above (≈ bundle era).
UPSTREAM: https://github.com/YosysHQ/eqy (per docs/source/quickstart.rst:14-15), docs in docs/source/ (index/outdir/config/strategies/quickstart/xprop).
```

## 1. Result channels

1. RESULT CHANNELS (workdir W = <jobname>/, `-d` override, `-t` = tempdir deleted at end)

| # | channel | producer (exact flag/cmd) | filename pattern |
|---|---------|---------------------------|------------------|
| V1 | top-level verdict file (exactly one of PASS/FAIL/UNKNOWN/ERROR) | any full run, EqyJob.final (src/eqy_job.py:707-709) | W/{PASS,FAIL,UNKNOWN,ERROR} |
| V2 | DONE verdict line on stdout (+mirrored in logfile) | final (eqy_job.py:711) | stream |
| V3 | summary: elapsed lines stdout+logfile | final (eqy_job.py:680-694) | stream/file |
| L1 | full log mirror | every run w/ job (eqy_job.py:239,289-297) | W/logfile.txt (append) |
| E1 | fatal errors on stderr, exit 1 | exit_with_error (eqy.py:31-33) | stream only |
| E2 | process exit code | sys.exit(retcode) (eqy.py:1262) | exit |
| D1 | compiled designs (RTLIL) | build_gate_gold/build_combined via yosys write_rtlil (eqy.py:292-309,393-408) | W/{gold,gate,gate_recoded,combined}.il |
| D2 | yosys -ql logs | same + get_ids/recode/partition tasks | W/{gold,gate,get_ids,recode,combine,partition}.log |
| D3 | generated .ys scripts (provenance) | same (eqy.py:292-309,327-338,375-381,397-408,743-748) | W/{gold,gate,get_ids,recode,combine,partition}.ys |
| D4 | entity-id DBs | eqy_combine -gold_ids/-gate_ids (eqy_combine.cc:143-151,200-208; eqy.py:338,407) | W/{gold,gate_recoded}.ids (+gate.ids temp) |
| D5 | matched nets | match_ids (eqy.py:581-614) | W/matched.ids |
| D6 | partition rules | partition_ids (eqy.py:636-736) | W/partition.ids |
| D7 | partition list | eqy_partition (eqy_partition.cc:1903-1962) | W/partition.list |
| D8 | per-partition JSON | eqy_partition (eqy_partition.cc:696-1070) | W/partitions/<part>.json (+modules/*.json) |
| D9 | per-partition RTLIL | backend_call rtlil (:1965) | W/partitions/<part>.il (+modules/, fragments/ w/ -write_fragments only, never passed by eqy.py:748) |
| D10 | per-partition miter SV | (:1072-1214) | W/partitions/<part>.sv |
| D11 | default sby config per partition | (:1232-1268) | W/partitions/<part>.sby |
| S1 | per-strategy status | run.sh: sat grep (eqy.py:872-885), sby awk (958), dummy (853), make cache (1116-1119) | W/strategies/<part>/<strat>/status |
| S2 | strategy logs/inputs | strategy.write (eqy.py:868-981) | W/strategies/<part>/<strat>/{run.sh,run.ys\|<part>.sby,run.log} |
| S3 | sat counterexample VCD | yosys sat -dump_vcd (eqy.py:904) | W/strategies/<part>/<strat>/trace.vcd |
| S4 | nested SBY workdir incl. CEX VCD | sby -f (eqy.py:958) | W/strategies/<part>/<strat>/<part>/{status,logfile.txt,engine_*/trace.vcd,…} |
| O1 | orchestration | make_scripts (eqy.py:1074-1152) | W/{strategies.mk,summary_targets.list} |
| – | in-process API / DB / socket | NONE (CLI driver only) | – |

## 2. Format grammars

2. FORMAT GRAMMARS

V1 verdict file: content = summary lines only (eqy_job.py:708-709). Gating is by FILENAME: examples/simple/Makefile test target = `aliases/PASS combine/PASS …` (file-existence gate). NOTE outdir.rst says FAIL "otherwise", but code writes exactly one file named for status ∈ {PASS,FAIL,UNKNOWN,ERROR}; TIMEOUT unreachable (timeout block commented out, eqy_job.py:273-278). Top-level `status` (no ext) is only ever deleted (eqy.py:287-289), never written (SBY-ism cleanup).

V2 DONE: `EQY HH:MM:SS [W] DONE (STATUS, rc=N)` (dress_message + :711). Regex: `DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=(\d+)\)`. Retcode map (eqy_job.py:698-705, expect default ["PASS"] :224): expected→0; else PASS=1, FAIL=2, UNKNOWN=4, TIMEOUT=8, ERROR=16. `--setup` appends UNKNOWN→`DONE (UNKNOWN, rc=0)` (eqy.py:1259; tests/python/Makefile). Real quotes (docs quickstart + tests): `EQY [nerv_change_fail] DONE (FAIL, rc=2)`; `DONE (PASS, rc=0)`; `DONE (UNKNOWN, rc=0)`.

V3 summary: `summary: Elapsed clock time [H:MM:SS (secs)]: H:MM:SS (secs)` and `summary: Elapsed process time …` (posix; on Windows "Elapsed process time unvailable on Windows" sic, :690). E.g. `summary: Elapsed clock time [H:MM:SS (secs)]: 0:00:18 (18)`.

L1 log line: `EQY HH:MM:SS [W] <msg>` plain when piped (click styles only on tty; eqy_job.py:280-292). Partition verdict lines: `* Successfully proved equivalence of partition P` / `* Failed to prove equivalence of partition P` / `* Successfully proved designs equivalent` (strategies.mk summary target, eqy.py:1140-1152), parsed by output_callback → update_status PASS/FAIL (eqy.py:1161-1174). update_status: UNKNOWN ignored, ERROR sticky, PASS↔FAIL assert-exclusive (eqy_job.py:486-507).

E2 exit codes: 0 expected-verdict; 1 config/usage/midrun-fatal + signals (force_shutdown :13-17); 2 FAIL; 4 UNKNOWN; 16 ERROR. Midrun fatal `A problem occurred during equivalence check.` (eqy.py:1178) exits BEFORE final() → no DONE, no V1 file.

D4 .ids (eqy_combine.cc:79-130), whitespace fields, `#` comments skipped by reader (eqy.py:425): module line: `<mod> . [N=<alias>]… [A:<attr>=<int|"str>]…`; cell line: `<mod> <cell> c=<type> [N=…] [A:…]`; wire line: `<mod> <wire> w=<msb>:<lsb> [N=…] [A:…] [P=[I][O]]`. P=I/O iff port_input/output (:129).

D5 matched.ids: comment `# [<pattern>] <cmd>` + data `<module> <gold_net> <gate_net>` (eqy.py:592,601,614); matches outdir.rst:47-50.

D6 partition.ids: statements per outdir.rst:60-74 (`solo|group|bind|join <mod> <net>…`, `name|merge|path|sticky|final|amend …`); writer emits e.g. `group <mod> <net>` (:656), `merge <mod> <lhs> <rhs…>` (:716,726), `path|amend <mod> <lhs> <rhs>` (:733).

D7 partition.list: `<module> <partname>[ memory][ xbits] : <outbit>…` (:1935-1962); module = gold name minus `\gold_` (:1935); partname = `<mod>.<name|index>` or full-module name (:1916-1918); outbits only, sorted, chunks rendered `w` | `w[i]` | `w[msb:lsb]` (:1954-1960). Full-module parts are NOT listed (:1933).

D8 partition JSON (PrettyJson, :702-1070): top-level `{"partition"|"fragment": {index:int, name:str, inbits:{wire:[offsets asc]}, outbits:{…}, crossbits:{…}}, gold_module:{name, internal:{…}, unused:{…}, cellcount:int, bitcount:int}, gate_module:{…same}}`. Bit-maps: {unescaped wire name: sorted int offsets} (:709-725). NO committed JSON fixture in repo (find: none) — schema reconstructed from writer; eqy.py consumes gold_module/gate_module.unused + attributes (eqy.py:1051-1062). Numbers plain ints; units n/a.

D10 .sv miter: `module miter(…)` with `__pi_*` inputs, `__cp_*/__mp_*/__po_*` gold/gate pairs + ifdef variants (DIRECT_CROSS_POINTS, CHECK_MATCH_POINTS, CHECK_OUTPUTS), `miter_cmp_prop`/`miter_def_prop` assert/assume/cover cells, empty `gold_*`/`gate_*` blackbox shells (:1075-1214).

D11 partitions/<part>.sby: fixed template [tasks] check/prove/cover, depth 20, bmc+prove, engines `abc pdr` + `smtbmc --keep-going bitwuzla` (:1232-1268). Distinct from S1 strategy sby files: [options] mode prove, depth N, `expect pass,fail,unknown,timeout` (eqy.py:916-925).

S1 status: first word ∈ PASS/FAIL/UNKNOWN/ERROR (+TIMEOUT via sby passthrough; outdir.rst:97-100). sat run.sh greps run.log: `SAT temporal induction proof finished - model found for base case: FAIL!`→FAIL; `Reached maximum number of time steps -> proof failed.`→UNKNOWN; `Interrupted SAT solver: TIMEOUT!`→UNKNOWN; `Induction step proven: SUCCESS!`→PASS; else ERROR+exit 1 (eqy.py:872-889). Chained strategies short-circuit: `PASS (cached)`/`FAIL (cached)` (eqy.py:1116-1119) — adapter must grep, not string-compare (mirrors make summary `grep -q "PASS"` :1144).

S3/S4 VCD: sat strategy dumps `trace.vcd` in strategy dir on disproof (yosys sat -dump_vcd); sby strategy CEX at `strategies/<part>/<strat>/<part>/engine_0/trace.vcd` (quickstart.rst:111; examples/nerv/README.md:98). Both standard IEEE VCD (read w/ pywellen per TOOL-OUTPUTS).

## 3. Python bindings verdict

3. PYTHON BINDINGS: NONE — audit row CONFIRMED ("none (src/eqy.py, no importable API)"). Evidence: Makefile `install` copies only `eqy_job.py` to share/yosys/python3 + 3 `.so` Yosys plugins + `bin/eqy` script (sed-installed, no package, no PyPI); eqy.py runs only via `main()` under `__main__` (eqy.py:1264-1265), is exit()-laden (exit_with_error, sys.exit) and click-formatted for terminal use; `from eqy_job import EqyJob` resolves only via install sys.path hack (`##yosys-sys-path##`, eqy.py:24); requirements.txt pins click==8.1.3 (CLI dep, docs env mixed in). tests/python/ drives the `eqy` BINARY exclusively (Makefiles set `EQY := eqy`). EqyJob/EqyTask are reusable in theory but are a job-runner, not a result API — no structured result objects, verdicts only via files/streams above.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (why: final() never runs, so no V1/V2/V3):
(a) Pre-job config/usage fatals → `ERROR: <msg>` on stderr, exit 1 (no workdir or empty workdir): `section [gate] missing`, `duplicated strategy section`, `syntax error in … line 16`, `unknown option …`, `Unknown strategy type …`, `has no 'use' line`, `Directory 'X' already exists`, `No config file given` (all asserted via stderr grep in tests/python/Makefile).
(b) Midrun fatal `A problem occurred during equivalence check.` (make rc≠0) → stderr exit 1, status left unwritten (stale V1 deleted at setup :287-289).
(c) Signal path `EQY ---- Keyboard interrupt or external termination signal ----` + exit 1 (eqy_job.py:13-17).
(d) Everything else apparently-terminal (task start/finish echoes, `* …partition…` lines, DONE, summary, warnings) IS in W/logfile.txt (appended, survives crashes) — parse the file, not the pipe. exit_with_error paths (a,b) are NOT mirrored to logfile.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text; task check.equivalence MVP, presentations table+traces, outputs equivalence_results/counterexamples/mappings/logs):
1st — STRUCTURED FILES (no bindings exist): V1 filename for top verdict; S1 `status` first-word per partition for the table (grep PASS/FAIL to tolerate `(cached)`); D7 partition.list + D8 JSON inbits/outbits/crossbits + cellcount/bitcount for mappings/counts; S3/S4 trace.vcd via VCD reader for counterexamples/traces; L1 logfile.txt tail for logs + DONE.
2nd — PINNED DETERMINISTIC TEXT: `DONE \((STATUS), rc=N\)` + exit-code map (0/1/2/4/16; 8 dead) for verdict incl. --setup UNKNOWN; `ERROR: …` stderr rules for residue (a–c); summary elapsed regex; do NOT parse yosys child logs except the four fixed sat markers (already reduced to S1 by run.sh).
3rd — NEVER: import eqy.py/eqy_job (no API, exit()-unsafe); never trust exit 0 alone in --setup mode (UNKNOWN rc=0 by design); never read `partitions/*.sby` as results (input template).
Version evidence: verified at clone 33015166 (2026-10-27); provision pin = oss-cad-suite 20261025 bundle (no separate eqy rev pin); stable grammars: DONE/V1/S1/D7/D8 shapes are writer-code-fixed; drift risk is in yosys/sby child-log wording (sat markers, nested SBY dir layout) — pin to bundle.

## Weak-evidence gaps (flagged by dissector)

- V1 verdict file: content = summary lines only (eqy_job.py:708-709). Gating is by FILENAME: examples/simple/Makefile test target = `aliases/PASS combine/PASS …` (file-existence gate). NOTE outdir.rst says FAIL "otherwise", but code writes exactly one file named
- D7 partition.list: `<module> <partname>[ memory][ xbits] : <outbit>…` (:1935-1962); module = gold name minus `\gold_` (:1935); partname = `<mod>.<name|index>` or full-module name (:1916-1918); outbits only, sorted, chunks rendered `w` | `w[i]` | `w[msb:lsb]` (
- PIN/VERSION: no eqy-specific pin in rocket-engine/scripts/provision_toolchain.sh; eqy ships inside oss-cad-suite bundle pin 20261025 (provision-sources.md §1 lists eqy in bundle). eqy --version prints `EQY $(git describe)` (Makefile); docs require a matching Y
- D10 .sv miter: `module miter(…)` with `__pi_*` inputs, `__cp_*/__mp_*/__po_*` gold/gate pairs + ifdef variants (DIRECT_CROSS_POINTS, CHECK_MATCH_POINTS, CHECK_OUTPUTS), `miter_cmp_prop`/`miter_def_prop` assert/assume/cover cells, empty `gold_*`/`gate_*` blackb
- 3. PYTHON BINDINGS: NONE — audit row CONFIRMED ("none (src/eqy.py, no importable API)"). Evidence: Makefile `install` copies only `eqy_job.py` to share/yosys/python3 + 3 `.so` Yosys plugins + `bin/eqy` script (sed-installed, no package, no PyPI); eqy.py runs o
- (a) Pre-job config/usage fatals → `ERROR: <msg>` on stderr, exit 1 (no workdir or empty workdir): `section [gate] missing`, `duplicated strategy section`, `syntax error in … line 16`, `unknown option …`, `Unknown strategy type …`, `has no 'use' line`, `Directo

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
EQY OUTPUT DISSECTION (review-only; no edits made)

CLONE: /tmp/rocket-tool-src/eqy/ @ SHA 33015166c47398dff1ac72a699f4212891bb0618, date 2026-10-27 (`git rev-parse HEAD`, `git log -1 --format=%cs`).
DOCS HTML: /tmp/rocket-tool-docs/ contains NO eqy file → fell back to in-repo docs (docs/source/*.rst) + repo-cited upstream URLs, per instructions.
PIN/VERSION: no eqy-specific pin in rocket-engine/scripts/provision_toolchain.sh; eqy ships inside oss-cad-suite bundle pin 20261025 (provision-sources.md §1 lists eqy in bundle). eqy --version prints `EQY $(git describe)` (Makefile); docs require a matching Yosys release + matching SBY (docs/source/install.rst:35-47). Verified at clone above (≈ bundle era).
UPSTREAM: https://github.com/YosysHQ/eqy (per docs/source/quickstart.rst:14-15), docs in docs/source/ (index/outdir/config/strategies/quickstart/xprop).

1. RESULT CHANNELS (workdir W = <jobname>/, `-d` override, `-t` = tempdir deleted at end)

| # | channel | producer (exact flag/cmd) | filename pattern |
|---|---------|---------------------------|------------------|
| V1 | top-level verdict file (exactly one of PASS/FAIL/UNKNOWN/ERROR) | any full run, EqyJob.final (src/eqy_job.py:707-709) | W/{PASS,FAIL,UNKNOWN,ERROR} |
| V2 | DONE verdict line on stdout (+mirrored in logfile) | final (eqy_job.py:711) | stream |
| V3 | summary: elapsed lines stdout+logfile | final (eqy_job.py:680-694) | stream/file |
| L1 | full log mirror | every run w/ job (eqy_job.py:239,289-297) | W/logfile.txt (append) |
| E1 | fatal errors on stderr, exit 1 | exit_with_error (eqy.py:31-33) | stream only |
| E2 | process exit code | sys.exit(retcode) (eqy.py:1262) | exit |
| D1 | compiled designs (RTLIL) | build_gate_gold/build_combined via yosys write_rtlil (eqy.py:292-309,393-408) | W/{gold,gate,gate_recoded,combined}.il |
| D2 | yosys -ql logs | same + get_ids/recode/partition tasks | W/{gold,gate,get_ids,recode,combine,partition}.log |
| D3 | generated .ys scripts (provenance) | same (eqy.py:292-309,327-338,375-381,397-408,743-748) | W/{gold,gate,get_ids,recode,combine,partition}.ys |
| D4 | entity-id DBs | eqy_combine -gold_ids/-gate_ids (eqy_combine.cc:143-151,200-208; eqy.py:338,407) | W/{gold,gate_recoded}.ids (+gate.ids temp) |
| D5 | matched nets | match_ids (eqy.py:581-614) | W/matched.ids |
| D6 | partition rules | partition_ids (eqy.py:636-736) | W/partition.ids |
| D7 | partition list | eqy_partition (eqy_partition.cc:1903-1962) | W/partition.list |
| D8 | per-partition JSON | eqy_partition (eqy_partition.cc:696-1070) | W/partitions/<part>.json (+modules/*.json) |
| D9 | per-partition RTLIL | backend_call rtlil (:1965) | W/partitions/<part>.il (+modules/, fragments/ w/ -write_fragments only, never passed by eqy.py:748) |
| D10 | per-partition miter SV | (:1072-1214) | W/partitions/<part>.sv |
| D11 | default sby config per partition | (:1232-1268) | W/partitions/<part>.sby |
| S1 | per-strategy status | run.sh: sat grep (eqy.py:872-885), sby awk (958), dummy (853), make cache (1116-1119) | W/strategies/<part>/<strat>/status |
| S2 | strategy logs/inputs | strategy.write (eqy.py:868-981) | W/strategies/<part>/<strat>/{run.sh,run.ys\|<part>.sby,run.log} |
| S3 | sat counterexample VCD | yosys sat -dump_vcd (eqy.py:904) | W/strategies/<part>/<strat>/trace.vcd |
| S4 | nested SBY workdir incl. CEX VCD | sby -f (eqy.py:958) | W/strategies/<part>/<strat>/<part>/{status,logfile.txt,engine_*/trace.vcd,…} |
| O1 | orchestration | make_scripts (eqy.py:1074-1152) | W/{strategies.mk,summary_targets.list} |
| – | in-process API / DB / socket | NONE (CLI driver only) | – |

2. FORMAT GRAMMARS

V1 verdict file: content = summary lines only (eqy_job.py:708-709). Gating is by FILENAME: examples/simple/Makefile test target = `aliases/PASS combine/PASS …` (file-existence gate). NOTE outdir.rst says FAIL "otherwise", but code writes exactly one file named for status ∈ {PASS,FAIL,UNKNOWN,ERROR}; TIMEOUT unreachable (timeout block commented out, eqy_job.py:273-278). Top-level `status` (no ext) is only ever deleted (eqy.py:287-289), never written (SBY-ism cleanup).

V2 DONE: `EQY HH:MM:SS [W] DONE (STATUS, rc=N)` (dress_message + :711). Regex: `DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=(\d+)\)`. Retcode map (eqy_job.py:698-705, expect default ["PASS"] :224): expected→0; else PASS=1, FAIL=2, UNKNOWN=4, TIMEOUT=8, ERROR=16. `--setup` appends UNKNOWN→`DONE (UNKNOWN, rc=0)` (eqy.py:1259; tests/python/Makefile). Real quotes (docs quickstart + tests): `EQY [nerv_change_fail] DONE (FAIL, rc=2)`; `DONE (PASS, rc=0)`; `DONE (UNKNOWN, rc=0)`.

V3 summary: `summary: Elapsed clock time [H:MM:SS (secs)]: H:MM:SS (secs)` and `summary: Elapsed process time …` (posix; on Windows "Elapsed process time unvailable on Windows" sic, :690). E.g. `summary: Elapsed clock time [H:MM:SS (secs)]: 0:00:18 (18)`.

L1 log line: `EQY HH:MM:SS [W] <msg>` plain when piped (click styles only on tty; eqy_job.py:280-292). Partition verdict lines: `* Successfully proved equivalence of partition P` / `* Failed to prove equivalence of partition P` / `* Successfully proved designs equivalent` (strategies.mk summary target, eqy.py:1140-1152), parsed by output_callback → update_status PASS/FAIL (eqy.py:1161-1174). update_status: UNKNOWN ignored, ERROR sticky, PASS↔FAIL assert-exclusive (eqy_job.py:486-507).

E2 exit codes: 0 expected-verdict; 1 config/usage/midrun-fatal + signals (force_shutdown :13-17); 2 FAIL; 4 UNKNOWN; 16 ERROR. Midrun fatal `A problem occurred during equivalence check.` (eqy.py:1178) exits BEFORE final() → no DONE, no V1 file.

D4 .ids (eqy_combine.cc:79-130), whitespace fields, `#` comments skipped by reader (eqy.py:425): module line: `<mod> . [N=<alias>]… [A:<attr>=<int|"str>]…`; cell line: `<mod> <cell> c=<type> [N=…] [A:…]`; wire line: `<mod> <wire> w=<msb>:<lsb> [N=…] [A:…] [P=[I][O]]`. P=I/O iff port_input/output (:129).

D5 matched.ids: comment `# [<pattern>] <cmd>` + data `<module> <gold_net> <gate_net>` (eqy.py:592,601,614); matches outdir.rst:47-50.

D6 partition.ids: statements per outdir.rst:60-74 (`solo|group|bind|join <mod> <net>…`, `name|merge|path|sticky|final|amend …`); writer emits e.g. `group <mod> <net>` (:656), `merge <mod> <lhs> <rhs…>` (:716,726), `path|amend <mod> <lhs> <rhs>` (:733).

D7 partition.list: `<module> <partname>[ memory][ xbits] : <outbit>…` (:1935-1962); module = gold name minus `\gold_` (:1935); partname = `<mod>.<name|index>` or full-module name (:1916-1918); outbits only, sorted, chunks rendered `w` | `w[i]` | `w[msb:lsb]` (:1954-1960). Full-module parts are NOT listed (:1933).

D8 partition JSON (PrettyJson, :702-1070): top-level `{"partition"|"fragment": {index:int, name:str, inbits:{wire:[offsets asc]}, outbits:{…}, crossbits:{…}}, gold_module:{name, internal:{…}, unused:{…}, cellcount:int, bitcount:int}, gate_module:{…same}}`. Bit-maps: {unescaped wire name: sorted int offsets} (:709-725). NO committed JSON fixture in repo (find: none) — schema reconstructed from writer; eqy.py consumes gold_module/gate_module.unused + attributes (eqy.py:1051-1062). Numbers plain ints; units n/a.

D10 .sv miter: `module miter(…)` with `__pi_*` inputs, `__cp_*/__mp_*/__po_*` gold/gate pairs + ifdef variants (DIRECT_CROSS_POINTS, CHECK_MATCH_POINTS, CHECK_OUTPUTS), `miter_cmp_prop`/`miter_def_prop` assert/assume/cover cells, empty `gold_*`/`gate_*` blackbox shells (:1075-1214).

D11 partitions/<part>.sby: fixed template [tasks] check/prove/cover, depth 20, bmc+prove, engines `abc pdr` + `smtbmc --keep-going bitwuzla` (:1232-1268). Distinct from S1 strategy sby files: [options] mode prove, depth N, `expect pass,fail,unknown,timeout` (eqy.py:916-925).

S1 status: first word ∈ PASS/FAIL/UNKNOWN/ERROR (+TIMEOUT via sby passthrough; outdir.rst:97-100). sat run.sh greps run.log: `SAT temporal induction proof finished - model found for base case: FAIL!`→FAIL; `Reached maximum number of time steps -> proof failed.`→UNKNOWN; `Interrupted SAT solver: TIMEOUT!`→UNKNOWN; `Induction step proven: SUCCESS!`→PASS; else ERROR+exit 1 (eqy.py:872-889). Chained strategies short-circuit: `PASS (cached)`/`FAIL (cached)` (eqy.py:1116-1119) — adapter must grep, not string-compare (mirrors make summary `grep -q "PASS"` :1144).

S3/S4 VCD: sat strategy dumps `trace.vcd` in strategy dir on disproof (yosys sat -dump_vcd); sby strategy CEX at `strategies/<part>/<strat>/<part>/engine_0/trace.vcd` (quickstart.rst:111; examples/nerv/README.md:98). Both standard IEEE VCD (read w/ pywellen per TOOL-OUTPUTS).

3. PYTHON BINDINGS: NONE — audit row CONFIRMED ("none (src/eqy.py, no importable API)"). Evidence: Makefile `install` copies only `eqy_job.py` to share/yosys/python3 + 3 `.so` Yosys plugins + `bin/eqy` script (sed-installed, no package, no PyPI); eqy.py runs only via `main()` under `__main__` (eqy.py:1264-1265), is exit()-laden (exit_with_error, sys.exit) and click-formatted for terminal use; `from eqy_job import EqyJob` resolves only via install sys.path hack (`##yosys-sys-path##`, eqy.py:24); requirements.txt pins click==8.1.3 (CLI dep, docs env mixed in). tests/python/ drives the `eqy` BINARY exclusively (Makefiles set `EQY := eqy`). EqyJob/EqyTask are reusable in theory but are a job-runner, not a result API — no structured result objects, verdicts only via files/streams above.

4. STDIO-ONLY RESIDUE (why: final() never runs, so no V1/V2/V3):
(a) Pre-job config/usage fatals → `ERROR: <msg>` on stderr, exit 1 (no workdir or empty workdir): `section [gate] missing`, `duplicated strategy section`, `syntax error in … line 16`, `unknown option …`, `Unknown strategy type …`, `has no 'use' line`, `Directory 'X' already exists`, `No config file given` (all asserted via stderr grep in tests/python/Makefile).
(b) Midrun fatal `A problem occurred during equivalence check.` (make rc≠0) → stderr exit 1, status left unwritten (stale V1 deleted at setup :287-289).
(c) Signal path `EQY ---- Keyboard interrupt or external termination signal ----` + exit 1 (eqy_job.py:13-17).
(d) Everything else apparently-terminal (task start/finish echoes, `* …partition…` lines, DONE, summary, warnings) IS in W/logfile.txt (appended, survives crashes) — parse the file, not the pipe. exit_with_error paths (a,b) are NOT mirrored to logfile.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text; task check.equivalence MVP, presentations table+traces, outputs equivalence_results/counterexamples/mappings/logs):
1st — STRUCTURED FILES (no bindings exist): V1 filename for top verdict; S1 `status` first-word per partition for the table (grep PASS/FAIL to tolerate `(cached)`); D7 partition.list + D8 JSON inbits/outbits/crossbits + cellcount/bitcount for mappings/counts; S3/S4 trace.vcd via VCD reader for counterexamples/traces; L1 logfile.txt tail for logs + DONE.
2nd — PINNED DETERMINISTIC TEXT: `DONE \((STATUS), rc=N\)` + exit-code map (0/1/2/4/16; 8 dead) for verdict incl. --setup UNKNOWN; `ERROR: …` stderr rules for residue (a–c); summary elapsed regex; do NOT parse yosys child logs except the four fixed sat markers (already reduced to S1 by run.sh).
3rd — NEVER: import eqy.py/eqy_job (no API, exit()-unsafe); never trust exit 0 alone in --setup mode (UNKNOWN rc=0 by design); never read `partitions/*.sby` as results (input template).
Version evidence: verified at clone 33015166 (2026-10-27); provision pin = oss-cad-suite 20261025 bundle (no separate eqy rev pin); stable grammars: DONE/V1/S1/D7/D8 shapes are writer-code-fixed; drift risk is in yosys/sby child-log wording (sat markers, nested SBY dir layout) — pin to bundle.
```
