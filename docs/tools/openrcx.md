# openrcx — output dissection

Dissector ref: prior result 7 (text `handoff-fa4484e8d19ff38d31fe4565d5068c170e7482ec96cfa650055eb40011016085-98c859ad70d5eff0c811e05d9ebb694367a115d4f12a9931fe209dfbf59c2ae6.txt`, summary `handoff-1564c2b75aca23f8a568f9b828ab9b15c36795bc6dd6e576ed35632cfd2881df-98c859ad70d5eff0c811e05d9ebb694367a115d4f12a9931fe209dfbf59c2ae6.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `a0c988ddc591b0b6e18c073d72a112aeb81a4bc3`
- Clone date: `2020-12-16`
- Pin: Clone: /tmp/rocket-tool-src/openrcx @ a0c988ddc591b0b6e18c073d72a112aeb81a4bc3, date 2020-12-16. NOTE: standalone repo, stale; upstream now lives at The-OpenROAD-Project/OpenROAD src/rcx, docs https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html. Docs HTML: no openrcx file under /tmp/r
- Doc/source URLs:
  - https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html

### Dissector header (verbatim, whitespace-trimmed)

```text
OPENRCX OUTPUT DISSECTION
Clone: /tmp/rocket-tool-src/openrcx @ a0c988ddc591b0b6e18c073d72a112aeb81a4bc3, date 2020-12-16. NOTE: standalone repo, stale; upstream now lives at The-OpenROAD-Project/OpenROAD src/rcx, docs https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html. Docs HTML: no openrcx file under /tmp/rocket-tool-docs/ (only amaranth/cace/devsim/elmer/femwell/ghdl/kfactory/meep/nextpnr/…) → fell back to in-repo README/doc + upstream web. Pin: NO openrcx entry in rocket-engine/scripts/provision_toolchain.sh; audit row says "via openroad/LibreLane closure" — effective pin LibreLane 3.0.17 (commit 64ef808). Verified at clone SHA above.
```

## 1. Result channels

1. RESULT CHANNELS (all paths grounded in clone source)
| # | Channel | Producing command (exact) | Filename / destination | Evidence |
|---|---|---|---|---|
| 1 | SPEF parasitics file | `write_spef [-net_id id] [-nets list] <file>` | exact user-given path | src/OpenRCX.tcl:105-128 → rcx::write_spef (src/ext.i:86-97) → Ext::write_spef (src/ext.cpp:788-815) → extSpef::writeBlock |
| 2a | diff report | `diff_spef -file <ref.spef>` (+dead -r_* flags; Tcl passes -over lookups, src/OpenRCX.tcl:177-180) | FIXED `./diff_spef.out` (CWD, mode "w") | src/extSpef.cpp:328; lines via printDiff/printDiffCC src/extSpefIn.cpp:208-320,346-388 |
| 2b | diff invalid-ref log | same command | FIXED `./diff_spef.log` (CWD, "w") | src/extSpef.cpp:323 |
| 3 | Extraction-rules file (custom RC tech) | `write_rules [-file F(default extRules)] [-dir D(default ./)] [-name N(default TYP)] [-pattern p] [-db] [-read_from_solver]` | exactly F as given (GenExtRules(rulesFile) when -db) | src/OpenRCX.tcl:256-293 → src/ext.i:161-174 → src/ext.cpp:171-186 → src/extRCmodel.cpp:5427-5452 |
| 4 | bench Verilog netlist | `bench_verilog <file>` | exact user-given path (fopen "w") | src/ext.cpp:339-357 |
| 5 | bench pattern layout | `bench_wires [-len N][-cnt N][-s_list ..][-w_list ..][-all][-over][-diag][-db_only][-met_cnt N][-under_met m]` | in-DB wires ONLY; .def emitted by OpenDB `write_def`, not rcx | src/OpenRCX.tcl:185-240; test/generate_pattern.tcl calls write_def separately |
| 6 | in-DB parasitics (RSeg/CapNode/CCSeg on odb objects) | `extract_parasitics -ext_model_file F [-corner_cnt n][-max_res Ω][-coupling_threshold fF][-lef_res][-cc_model t][-context_depth d]` (+define_process_corner) | OpenDB block; persisted only via OpenDB `write_odb` | src/OpenRCX.tcl:34-103 → src/ext.i:59-84 → Ext::extract; README:16 "stores … on OpenDB objects" |
| 7 | stdout log | every command | OpenROAD logger `Notice 0:`/`Warning`/`Error` lines | src/ext.cpp, extFlow.cpp, netRC.cpp, extSpef.cpp (see §4) |
| 8 | in-process C++ API | OpenRCX::Ext methods | return values only | include/OpenRCX/ext.h:43-354 |
| — | incremental SPEF (/tmp/orig\|new.<corner>.<n>.spef) | NOT wired to any Tcl cmd (no wrapper in OpenRCX.tcl) → unreachable; out of scope | src/extmain.cpp:215-241,255-323 | — |

## 2. Format grammars

2. FORMAT GRAMMARS
A. SPEF (IEEE 1481-1999; golden test/gcd.spefok; writer src/extSpef.cpp:2021-2036 + writeBlock).
Header (byte-fixed except DESIGN): `*SPEF "ieee 1481-1999"`, `*DESIGN "<block>"`, `*DATE "11:11:11 Fri 11 11, 1111"` (HARDCODED constant → byte-stable), `*VENDOR "OpenRCX"`, `*PROGRAM "Parallel Extraction"`, `*VERSION "1.0"`, `*DESIGN_FLOW "NAME_SCOPE LOCAL" "PIN_CAP NONE"`, `*DIVIDER /`, `*DELIMITER :`, `*BUS_DELIMITER []`, `*T_UNIT 1 NS`, `*C_UNIT 1 PF`, `*R_UNIT 1 OHM`, `*L_UNIT 1 HENRY`. Cap/res units hardcoded "PF"/"OHM" at all writeBlock call sites (e.g. src/extmain.cpp:261-276,366-381); SpefOptions defaults agree (include/OpenRCX/ext.h:227-228).
Body: `*NAME_MAP` + `*<id> <name>` lines; per net `*D_NET *<id> <totalCap>` then `*CONN` (`*P <pin> <dir>` / `*I *<id>:<pin> <dir> *D <cell>`), `*CAP` (gnd: `<idx> <node> <cap>`; coupling: `<idx> <node1> <node2> <cap>`; NOTE writer emits literal `0` ccaps), `*RES` (`<idx> <node1> <node2> <ohms> `), `*END`. Node syntax `*<netid>:<capid>` or pin names. Floats %g-style. Real sample (gcd.spefok:8201+): `*D_NET *1 0.026586` / `1 clk 0.000715859` / `12 *1:8 *7:8 0.00075713` / `*RES` / `1 clk *1:5 21.5503`.
B. diff_spef.out (ad-hoc; ONLY out-of-threshold nets printed — guards `(_upperThres,_lowerThres)`, src/extSpefIn.cpp:236-237,373): netRes: `%4.1f %10.4f D %s %4.1f ref %10.4f R %s %4.1f bounds: %10.4f %10.4f VR %g V %d L %d WC %d %s corner %d %s` + optional `capId %d` + net name (src/extSpefIn.cpp:259-282,314-316). netCap/netGndCap: same head, tail `bounds: %10.4f %10.4f L %8d WC %3d V %3d %s corner %d %s` (src/extSpefIn.cpp:304-313). Coupling: `%4.1f - %s %g ref %g corner %d capNodes %d %d` + two net names (src/extSpefIn.cpp:374-385). Fields: pct-diff, db val, D/db-vs-bounds tag, bounds-pct, ref val, R/ref-vs-bounds tag, bounds-pct-ref, min/max bounds, via_res, via_cnt, wire_len, wire_cnt, ctype(netRes|netCap|netGndCap|…), corner idx. diff_spef.log: `Invalid ref %s for net <name>` / `Invalid ref %s for nodeIds %d %d` (src/extSpefIn.cpp:222-224,359-362).
C. Rules file (custom; golden test/ext_pattern.rules; writer src/extRCmodel.cpp:299-345,1091-1310; reader ~L4270): magic line `Extraction Rules for OpenRCX`; `DIAGMODEL ON`; `LayerCount <n>`; `DensityRate 1 0`; `DensityModel 0`; per layer `Metal <m> OVER|UNDER`, `WIDTH Table <n> entries: <w…>` (microns), `Metal <m> OVER|UNDER <depth>`, `DIST count <n> width <w>`, n rows of 4 doubles `<dist_um> <v1> <v2> <v3>` (%g/%e), `END DIST`. Sample: `0.17 7.80814e-05 1.75053e-05 0.0340853`. Triple semantics per reader (cap/res columns) — adapter must confirm against src/extRCmodel.cpp parser before relying beyond round-trip.
D. bench Verilog (golden test/generate_pattern.vok): Verilog-2001 `module blk ( <pattern ports> );` one port per pattern wire, names encode layer/geometry/spacing/index (e.g. `O6_M1oM0_W170W170_S170S170_1`) + `_BL` companions. bench DEF golden (test/generate_pattern.defok) is OpenDB `write_def` output (DEF 5.8), not rcx grammar.
E. stdout notices (exact formats): `extracting %s ...`(ext.cpp:492), `Reading extraction model file %s ...`(netRC.cpp:2397), `dbFactor= %g dbunit= %d`(netRC.cpp:2404), `RC segment generation %s ...`(extFlow.cpp:4933), `Final %d rc segments`(extFlow.cpp:4974), `Coupling threshhold is %f FF, coupling capacitance less than %f FF will be grounded.`(netRC.cpp:2997, sic "threshhold"), `%d wires to be extracted`(extFlow.cpp:2519), `%c%d completion -- %d wires have been extracted`(extFlow.cpp:2747,3332), `Extract %d nets, %d rsegs, %d caps, %d ccs`(netRC.cpp:3158), `Finished extracting %s.`(ext.cpp:727), `Writing SPEF ...`/`%d nets finished`/`Finished writing SPEF ...`(ext.cpp:788,815; extSpef.cpp:1936-1992), `diffing spef %s`(ext.cpp:~903), `Defined process_corner %s with ext_model_index %d`(netRC.cpp:2046), `Defined Extraction corner %s`(ext.cpp:370), bench `Finished %d (bench )?measurements for pattern %s`(golden test/generate_pattern.ok). Golden full-log example test/gcd.ok (322 nets, 3136 rsegs/caps, 2061 ccs).

## 3. Python bindings verdict

3. PYTHON BINDINGS — audit row CONFIRMED ("NONE of its own (Tcl cmds inside openroad)"). `src/ext.i` `%module openrcx` is SWIG-for-Tcl ONLY: src/CMakeLists.txt:47-53 `LANGUAGE tcl`, `-namespace -prefix rcx`; all rcx::* Tcl procs return void (src/ext.i:52-184). No Python module, no PyPI, no `openroad -python` rcx object in this tree (Ext::init takes Tcl_Interp*, include/OpenRCX/ext.h:52). C++ API returns bool/TCL_OK status only, no result structs. Structured read path for adapters: `openroad -python` + `import odb` (dbRSeg/dbCapNode/dbCCSeg + .odb checkpoints) per the audit's openroad/opendb KEEP-BINDINGS rows — execution stays subprocess, bindings only READ.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (why: logger notices by design, never persisted): completion summary `Extract N nets, N rsegs, N caps, N ccs`; progress `%N completion`; `Final N rc segments`; `N nets finished`; bench `Finished N measurements for pattern X`; `diffing spef …`; corner-definition confirmations; all warnings/errors (`Cannot open file …`, `Can not open file … to write spef.`). No result data is stdio-exclusive EXCEPT these counts/health markers — all parasitics land in DB/SPEF. Parse stdio only for completion + count cross-checks (e.g. `Extract 322 nets…` vs `*D_NET` count in SPEF).

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1st: SPEF file (ch.1) — IEEE-grammar-stable, hardcoded units/date, golden-covered; parse with a 1481 reader. 2nd (tie): query in-DB parasitics via `openroad -python import odb` after a `write_odb` checkpoint — dump-first, no text. 3rd: rules file grammar — only for calibration flows. 4th: diff_spef.out/.log — ad-hoc, FIXED CWD filenames (parallel-unsafe), threshold-filtered (absence ≠ equality; check .log for invalid refs). 5th: stdio regex — progress/health only (`Extract …` as completion marker).
Version evidence: dissected at clone a0c988d/2020-12-16; effective provision pin LibreLane 3.0.17 (64ef808) closure. DRIFT WARNING: upstream src/rcx has since added flags absent here (rcx_rules.json ext-model, 3D multi-die `design.<chip>.spef` + `design.bonds.spef`); re-verify SPEF/diff grammars against the LibreLane-closure OpenROAD before freezing goldens.

## Weak-evidence gaps (flagged by dissector)

- Clone: /tmp/rocket-tool-src/openrcx @ a0c988ddc591b0b6e18c073d72a112aeb81a4bc3, date 2020-12-16. NOTE: standalone repo, stale; upstream now lives at The-OpenROAD-Project/OpenROAD src/rcx, docs https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html.

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
OPENRCX OUTPUT DISSECTION
Clone: /tmp/rocket-tool-src/openrcx @ a0c988ddc591b0b6e18c073d72a112aeb81a4bc3, date 2020-12-16. NOTE: standalone repo, stale; upstream now lives at The-OpenROAD-Project/OpenROAD src/rcx, docs https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html. Docs HTML: no openrcx file under /tmp/rocket-tool-docs/ (only amaranth/cace/devsim/elmer/femwell/ghdl/kfactory/meep/nextpnr/…) → fell back to in-repo README/doc + upstream web. Pin: NO openrcx entry in rocket-engine/scripts/provision_toolchain.sh; audit row says "via openroad/LibreLane closure" — effective pin LibreLane 3.0.17 (commit 64ef808). Verified at clone SHA above.

1. RESULT CHANNELS (all paths grounded in clone source)
| # | Channel | Producing command (exact) | Filename / destination | Evidence |
|---|---|---|---|---|
| 1 | SPEF parasitics file | `write_spef [-net_id id] [-nets list] <file>` | exact user-given path | src/OpenRCX.tcl:105-128 → rcx::write_spef (src/ext.i:86-97) → Ext::write_spef (src/ext.cpp:788-815) → extSpef::writeBlock |
| 2a | diff report | `diff_spef -file <ref.spef>` (+dead -r_* flags; Tcl passes -over lookups, src/OpenRCX.tcl:177-180) | FIXED `./diff_spef.out` (CWD, mode "w") | src/extSpef.cpp:328; lines via printDiff/printDiffCC src/extSpefIn.cpp:208-320,346-388 |
| 2b | diff invalid-ref log | same command | FIXED `./diff_spef.log` (CWD, "w") | src/extSpef.cpp:323 |
| 3 | Extraction-rules file (custom RC tech) | `write_rules [-file F(default extRules)] [-dir D(default ./)] [-name N(default TYP)] [-pattern p] [-db] [-read_from_solver]` | exactly F as given (GenExtRules(rulesFile) when -db) | src/OpenRCX.tcl:256-293 → src/ext.i:161-174 → src/ext.cpp:171-186 → src/extRCmodel.cpp:5427-5452 |
| 4 | bench Verilog netlist | `bench_verilog <file>` | exact user-given path (fopen "w") | src/ext.cpp:339-357 |
| 5 | bench pattern layout | `bench_wires [-len N][-cnt N][-s_list ..][-w_list ..][-all][-over][-diag][-db_only][-met_cnt N][-under_met m]` | in-DB wires ONLY; .def emitted by OpenDB `write_def`, not rcx | src/OpenRCX.tcl:185-240; test/generate_pattern.tcl calls write_def separately |
| 6 | in-DB parasitics (RSeg/CapNode/CCSeg on odb objects) | `extract_parasitics -ext_model_file F [-corner_cnt n][-max_res Ω][-coupling_threshold fF][-lef_res][-cc_model t][-context_depth d]` (+define_process_corner) | OpenDB block; persisted only via OpenDB `write_odb` | src/OpenRCX.tcl:34-103 → src/ext.i:59-84 → Ext::extract; README:16 "stores … on OpenDB objects" |
| 7 | stdout log | every command | OpenROAD logger `Notice 0:`/`Warning`/`Error` lines | src/ext.cpp, extFlow.cpp, netRC.cpp, extSpef.cpp (see §4) |
| 8 | in-process C++ API | OpenRCX::Ext methods | return values only | include/OpenRCX/ext.h:43-354 |
| — | incremental SPEF (/tmp/orig\|new.<corner>.<n>.spef) | NOT wired to any Tcl cmd (no wrapper in OpenRCX.tcl) → unreachable; out of scope | src/extmain.cpp:215-241,255-323 | — |

2. FORMAT GRAMMARS
A. SPEF (IEEE 1481-1999; golden test/gcd.spefok; writer src/extSpef.cpp:2021-2036 + writeBlock).
Header (byte-fixed except DESIGN): `*SPEF "ieee 1481-1999"`, `*DESIGN "<block>"`, `*DATE "11:11:11 Fri 11 11, 1111"` (HARDCODED constant → byte-stable), `*VENDOR "OpenRCX"`, `*PROGRAM "Parallel Extraction"`, `*VERSION "1.0"`, `*DESIGN_FLOW "NAME_SCOPE LOCAL" "PIN_CAP NONE"`, `*DIVIDER /`, `*DELIMITER :`, `*BUS_DELIMITER []`, `*T_UNIT 1 NS`, `*C_UNIT 1 PF`, `*R_UNIT 1 OHM`, `*L_UNIT 1 HENRY`. Cap/res units hardcoded "PF"/"OHM" at all writeBlock call sites (e.g. src/extmain.cpp:261-276,366-381); SpefOptions defaults agree (include/OpenRCX/ext.h:227-228).
Body: `*NAME_MAP` + `*<id> <name>` lines; per net `*D_NET *<id> <totalCap>` then `*CONN` (`*P <pin> <dir>` / `*I *<id>:<pin> <dir> *D <cell>`), `*CAP` (gnd: `<idx> <node> <cap>`; coupling: `<idx> <node1> <node2> <cap>`; NOTE writer emits literal `0` ccaps), `*RES` (`<idx> <node1> <node2> <ohms> `), `*END`. Node syntax `*<netid>:<capid>` or pin names. Floats %g-style. Real sample (gcd.spefok:8201+): `*D_NET *1 0.026586` / `1 clk 0.000715859` / `12 *1:8 *7:8 0.00075713` / `*RES` / `1 clk *1:5 21.5503`.
B. diff_spef.out (ad-hoc; ONLY out-of-threshold nets printed — guards `(_upperThres,_lowerThres)`, src/extSpefIn.cpp:236-237,373): netRes: `%4.1f %10.4f D %s %4.1f ref %10.4f R %s %4.1f bounds: %10.4f %10.4f VR %g V %d L %d WC %d %s corner %d %s` + optional `capId %d` + net name (src/extSpefIn.cpp:259-282,314-316). netCap/netGndCap: same head, tail `bounds: %10.4f %10.4f L %8d WC %3d V %3d %s corner %d %s` (src/extSpefIn.cpp:304-313). Coupling: `%4.1f - %s %g ref %g corner %d capNodes %d %d` + two net names (src/extSpefIn.cpp:374-385). Fields: pct-diff, db val, D/db-vs-bounds tag, bounds-pct, ref val, R/ref-vs-bounds tag, bounds-pct-ref, min/max bounds, via_res, via_cnt, wire_len, wire_cnt, ctype(netRes|netCap|netGndCap|…), corner idx. diff_spef.log: `Invalid ref %s for net <name>` / `Invalid ref %s for nodeIds %d %d` (src/extSpefIn.cpp:222-224,359-362).
C. Rules file (custom; golden test/ext_pattern.rules; writer src/extRCmodel.cpp:299-345,1091-1310; reader ~L4270): magic line `Extraction Rules for OpenRCX`; `DIAGMODEL ON`; `LayerCount <n>`; `DensityRate 1 0`; `DensityModel 0`; per layer `Metal <m> OVER|UNDER`, `WIDTH Table <n> entries: <w…>` (microns), `Metal <m> OVER|UNDER <depth>`, `DIST count <n> width <w>`, n rows of 4 doubles `<dist_um> <v1> <v2> <v3>` (%g/%e), `END DIST`. Sample: `0.17 7.80814e-05 1.75053e-05 0.0340853`. Triple semantics per reader (cap/res columns) — adapter must confirm against src/extRCmodel.cpp parser before relying beyond round-trip.
D. bench Verilog (golden test/generate_pattern.vok): Verilog-2001 `module blk ( <pattern ports> );` one port per pattern wire, names encode layer/geometry/spacing/index (e.g. `O6_M1oM0_W170W170_S170S170_1`) + `_BL` companions. bench DEF golden (test/generate_pattern.defok) is OpenDB `write_def` output (DEF 5.8), not rcx grammar.
E. stdout notices (exact formats): `extracting %s ...`(ext.cpp:492), `Reading extraction model file %s ...`(netRC.cpp:2397), `dbFactor= %g dbunit= %d`(netRC.cpp:2404), `RC segment generation %s ...`(extFlow.cpp:4933), `Final %d rc segments`(extFlow.cpp:4974), `Coupling threshhold is %f FF, coupling capacitance less than %f FF will be grounded.`(netRC.cpp:2997, sic "threshhold"), `%d wires to be extracted`(extFlow.cpp:2519), `%c%d completion -- %d wires have been extracted`(extFlow.cpp:2747,3332), `Extract %d nets, %d rsegs, %d caps, %d ccs`(netRC.cpp:3158), `Finished extracting %s.`(ext.cpp:727), `Writing SPEF ...`/`%d nets finished`/`Finished writing SPEF ...`(ext.cpp:788,815; extSpef.cpp:1936-1992), `diffing spef %s`(ext.cpp:~903), `Defined process_corner %s with ext_model_index %d`(netRC.cpp:2046), `Defined Extraction corner %s`(ext.cpp:370), bench `Finished %d (bench )?measurements for pattern %s`(golden test/generate_pattern.ok). Golden full-log example test/gcd.ok (322 nets, 3136 rsegs/caps, 2061 ccs).

3. PYTHON BINDINGS — audit row CONFIRMED ("NONE of its own (Tcl cmds inside openroad)"). `src/ext.i` `%module openrcx` is SWIG-for-Tcl ONLY: src/CMakeLists.txt:47-53 `LANGUAGE tcl`, `-namespace -prefix rcx`; all rcx::* Tcl procs return void (src/ext.i:52-184). No Python module, no PyPI, no `openroad -python` rcx object in this tree (Ext::init takes Tcl_Interp*, include/OpenRCX/ext.h:52). C++ API returns bool/TCL_OK status only, no result structs. Structured read path for adapters: `openroad -python` + `import odb` (dbRSeg/dbCapNode/dbCCSeg + .odb checkpoints) per the audit's openroad/opendb KEEP-BINDINGS rows — execution stays subprocess, bindings only READ.

4. STDIO-ONLY RESIDUE (why: logger notices by design, never persisted): completion summary `Extract N nets, N rsegs, N caps, N ccs`; progress `%N completion`; `Final N rc segments`; `N nets finished`; bench `Finished N measurements for pattern X`; `diffing spef …`; corner-definition confirmations; all warnings/errors (`Cannot open file …`, `Can not open file … to write spef.`). No result data is stdio-exclusive EXCEPT these counts/health markers — all parasitics land in DB/SPEF. Parse stdio only for completion + count cross-checks (e.g. `Extract 322 nets…` vs `*D_NET` count in SPEF).

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1st: SPEF file (ch.1) — IEEE-grammar-stable, hardcoded units/date, golden-covered; parse with a 1481 reader. 2nd (tie): query in-DB parasitics via `openroad -python import odb` after a `write_odb` checkpoint — dump-first, no text. 3rd: rules file grammar — only for calibration flows. 4th: diff_spef.out/.log — ad-hoc, FIXED CWD filenames (parallel-unsafe), threshold-filtered (absence ≠ equality; check .log for invalid refs). 5th: stdio regex — progress/health only (`Extract …` as completion marker).
Version evidence: dissected at clone a0c988d/2020-12-16; effective provision pin LibreLane 3.0.17 (64ef808) closure. DRIFT WARNING: upstream src/rcx has since added flags absent here (rcx_rules.json ext-model, 3D multi-die `design.<chip>.spef` + `design.bonds.spef`); re-verify SPEF/diff grammars against the LibreLane-closure OpenROAD before freezing goldens.
```
