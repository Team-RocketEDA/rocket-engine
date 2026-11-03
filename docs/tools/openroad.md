# openroad — output dissection

Dissector ref: prior result 8 (text `handoff-60c2ca0ca909f4938097785d5fcb9e1a28f465784e37e797f507ebf8810172d1-d0c80a501c895c32bd6d44094a42cc335baf1f98fddb407c164de8e452684bee.txt`, summary `handoff-a6ada813e24487724cca8793065f3fb0ed6bf131952abcbf54bf8d99e6a5618e-d0c80a501c895c32bd6d44094a42cc335baf1f98fddb407c164de8e452684bee.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `f3d27840b65a9571a808a19b06dc0b93b9d4423d`
- Clone date: `2026-11-02`
- Pin: Pin/version: audit row "2.x via LibreLane nix-eda 6.11.0 closure" is loose. provision_toolchain.sh pins LIBRELANE 3.0.17 @64ef80802d3d189b476636d2a6b17888c03304ee and OPENSTA 857316ff001b2a8dbbdc5996944d08a6d38c87ab; NO standalone openroad rev pin (arrives via LibreLane closure). Verified at clone H
- Doc/source URLs: none in header (see dissector header below)

### Dissector header (verbatim, whitespace-trimmed)

```text
OPENROAD OUTPUT DISSECTION (review-only)
Clone SHA: f3d27840b65a9571a808a19b06dc0b93b9d4423d, date 2026-11-02 (`git rev-parse HEAD`, `git log -1 --format=%cs` in /tmp/rocket-tool-src/openroad). Shallow clone; NOTE src/sta/ (OpenSTA submodule, .gitmodules) is EMPTY, so STA-owned writers were not inspected — flagged below.
Docs: /tmp/rocket-tool-docs/openroad-index.html present (Sphinx index, "Welcome to OpenROAD's documentation"); substantive pages e.g. main/src/<tool>/README.html, main/src/odb/doc/{LEF,DEF}_Grammar.html, main/src/sta/README.html.
Pin/version: audit row "2.x via LibreLane nix-eda 6.11.0 closure" is loose. provision_toolchain.sh pins LIBRELANE 3.0.17 @64ef80802d3d189b476636d2a6b17888c03304ee and OPENSTA 857316ff001b2a8dbbdc5996944d08a6d38c87ab; NO standalone openroad rev pin (arrives via LibreLane closure). Verified at clone HEAD above (dev post-2.x; e.g. SPEF fixture stamps `*VERSION "26Q1-2613-g4d2ee4c0f7"`, src/rcx/test/coordinates.spefok:6). Build is Bazel-only now (CMakeLists.txt:10-16, CMake removed 2026-11-01).
```

## 1. Result channels

1. RESULT CHANNELS (one table; producing command → artifact)
| # | Channel | Producer | Artifact/pattern |
|---|---------|----------|------------------|
| 1 | ODB checkpoint (binary, queryable) | `write_db [-compression 0-9] file` (src/OpenRoad.tcl:256-278) / `Design.writeDb()` (include/ord/Design.h:149) | `*.odb[*.gz]`; only CLI input is `-db file` (src/Main.cc:498) |
| 2 | Metrics JSON | CLI `-metrics file.json` (src/Main.cc:156,496) + `utl::metric*` / `report_*_metric` (src/Metrics.tcl) | flat `{"key": value}` JSON |
| 3 | Log file (stdout dup) | CLI `-log file` (src/Main.cc:150) | free text, `[LEVEL TOOL-NNNN]` lines |
| 4 | stdout/stderr log stream | `logger_->report/info/warn/error` everywhere | same line grammar as #3 |
| 5 | DEF | `write_def [-version 5.3..5.8, dflt 5.8] file` (src/OpenRoad.tcl:92-115) | `*.def` |
| 6 | LEF | `write_lef file`; `write_abstract_lef [-bloat_factor N \| -bloat_occupied_layers] file` (src/OpenRoad.tcl:117-146) | `*.lef` |
| 7 | CDL netlist | `write_cdl [-include_fillers] -masters {...} file` (src/OpenRoad.tcl:148-164) | `*.cdl` (src/odb/src/cdl/cdl.cpp) |
| 8 | Verilog | `write_verilog [-sort(IGNORED, warns STA-2065)] [-include_pwr_gnd] [-remove_cells c] file` (src/dbSta/src/dbReadVerilog.tcl:29-50) | `*.v` |
| 9 | SPEF | `write_spef [-net_id id] [-nets list] [-coordinates] file` (src/rcx/src/OpenRCX.tcl:182-209; writer src/rcx/src/extSpef.cpp) | `*.spef`, IEEE 1481-1999 |
| 10 | SDC | `write_sdc ...` (OpenSTA submodule — UNINSPECTED, empty clone; usage src/dbSta/test/write_sdc1.tcl:9) | `*.sdc` |
| 11 | SDF | `write_sdf` (OpenSTA submodule — UNINSPECTED; zero hits in openroad src proper) | `*.sdf` |
| 12 | STA timing reports | `report_checks/report_tns/report_wns/...` (OpenSTA — UNINSPECTED; audit keeps STA-text grammar as residue) | stdout or Tcl-redirected files |
| 13 | DRC markers (in-DB) | `detailed_route` auto-exports to `dbMarkerCategory`/`dbMarker` (src/drt/src/TritonRoute.cpp:1376-1478, source "DRT") | inside .odb; readable via odb API |
| 14 | DRC TR text report | `detailed_route [-output_drc file] [-drc_report_iter_step n] ...` (src/drt/src/TritonRoute.tcl:4-70) → `dbMarkerCategory::writeTR` (src/odb/src/db/dbMarker.cpp:235) | `violation type:` blocks (grammar §2) |
| 15 | Antenna report | `check_antennas [-verbose] [-report_file f] [-net n]` (src/ant/src/AntennaChecker.tcl:4-38; returns violating-net count; metrics `antenna__violating__nets/pins`, AntennaChecker.cc:1168-1170) | `Net:/Pin:/Layer:` blocks (grammar §2); golden src/ant/test/check_grt1.ok |
| 16 | CTS metrics | `report_cts [-out_file file]` (src/cts/src/TritonCTS.tcl:605-619; src/cts/src/TritonCTS.cpp:606-657) | `Total number of ...` + `  master: count` lines |
| 17 | Guides | `write_guides file` (src/odb/src/swig/tcl/odb.tcl:583-596; src/odb/src/db/dbBlock.cpp:3188-3219) | `netname\n(\nxMin yMin xMax yMax layer\n)\n...` (DBU ints, nets strcmp-sorted) |
| 18 | Global-route segments | `write_global_route_segments file` (src/grt/src/GlobalRouter.tcl:412-420) | tool-internal text (round-trips with read_*) |
| 19 | Macro placement | `write_macro_placement file` (odb.tcl:598-615) | `generateMacroPlacementString` text |
| 20 | Pin placement | `write_pin_placement file [-placed_status]` / `place_pins ... -write_pin_placement f` (src/ppl/src/IOPlacer.tcl:199-207; src/ppl/src/IOPlacer.cpp:913-946) | Tcl script: `#Edge: top` + `place_pin -pin_name {n} -layer L -location {x y} -force_to_die_boundary` (microns) |
| 21 | PG SPICE | `write_pg_spice -net n [-vsrc f] [-corner c] [-source_type FULL|BUMPS|STRAPS] file` (src/psm/src/pdnsim.tcl:164-197) | SPICE netlist |
| 22 | PDN analysis files | `analyze_power_grid -net n [-error_file f] [-voltage_file f] [-enable_em -em_outfile f] ...` (src/psm/src/pdnsim.tcl:36-101) | voltage/error/EM text dumps |
| 23 | RCX model/rules | `write_rcx_model` (src/rcx/src/OpenRCX_process.tcl:4), `write_rules` (src/rcx/src/OpenRCX.tcl:411) | extraction rule tables |
| 24 | Wire/detour/congestion | `report_wire_length -net ... [-file f] [-summary]`, `report_net_detours [-file f] [-top_n n]`, `report_congestion` (stdout only), `has_congestion`→bool (src/grt/src/GlobalRouter.tcl:484-611) | stdout or -file |
| 25 | Cell/timing histograms | `report_cell_usage [-verbose] [inst] [-file f] [-stage s]`, `report_timing_histogram`, `report_logic_depth_histogram` (src/dbSta/src/dbSta.tcl:5-100+) | stdout or -file |
| 26 | Misc stdout reports | `report_design_area`, `report_floating_nets [> f]`, `report_long_wires n [> f]`, `check_placement [-verbose]`, `report_dft_plan`, `report_layer_rc`, `report_physical_clusters`, `report_3dic_summary`, ... (many accept Tcl `>` redirect) | stdout |
| 27 | GDSII | C++ ONLY: `odb::write_gds(dbGDSLib*, path)` (src/odb/include/odb/gdsout.h:31; round-trip test src/odb/test/cpp/TestGDSIn.cpp:96,174). NO Tcl command, NO SWIG hit found | `*.gds` |
| 28 | OASIS | NONE found (no writer in src/) | — |
| 29 | 3D / misc | `write_3dbv file` (src/OpenRoad.tcl:181), `write_upf file` (src/upf/src/upf.tcl:15), `write_partition_verilog`, `write_artnet_spec` (src/par/src/partitionmgr.tcl:967-1008) | various |
| 30 | GUI images | `save_animated_gif/save_clocktree_image/save_histogram_image` (src/gui/src/gui.tcl:72-179) | GUI-only, out of scope |
| 31 | In-process Python returns | wheel API (see §3): floats/ints/bools/strings/vectors of db objects + Timing structs | attribution-safe: read-only use after subprocess run |
| 32 | Exit status | `openroad [-exit] cmd.tcl`: TCL_OK→0 else 1 (src/Main.cc:386); usage/`-python`/bad `-web_*`→1; `utl::error` throws → Tcl error (src/utl/include/utl/Logger.h:170-178). WITHOUT `-exit`, falls into REPL (src/Main.cc:428-431) — adapter must pass `-exit` | rc 0/1 only; verdict never in rc alone |

## 2. Format grammars

2. FORMAT GRAMMARS (parser-author detail)
- metrics JSON: `MetricsEntry::assembleJSON` (src/utl/src/Metrics.cpp:19-29) emits `{\n\t"key": value,\n...}` — FLAT object, values float|int|string (strings pre-quoted by caller). DUPLICATE keys occur (flow re-emits per stage; see test/aes_nangate45.metrics: `gpl__convergence__iteration` twice, lines 3/9; JSON parsers keep last). Policies KeepFirst/KeepLast/Remove exist (Metrics.cpp:44-86). Key families: `timing__setup|hold__{tns,ws,wns}`, `timing__fmax[__clock:NAME]`, `timing__drv__*`, `power__{internal,switching,leakage,total}`, `design__instance__count__*`, `dpl__*`, `gpl__*`, `route__wirelength__estimated`, `antenna__violating__{nets,pins}`, stage-scoped `run__flow__platform__{}_units` (Metrics.tcl:176-188) with values like `1ns`,`1pF`. Limits-file sibling `*.metrics_limits` (test/aes_nangate45.metrics_limits) is `{"TOOL::metric" : "value"}` with SPACES around colon — different emitter, parse leniently.
- log line: `[LEVEL TOOL-NNNN] message` — e.g. `[INFO ODB-0227] LEF file: sky130hs/sky130hs.tlef, created 13 layers, 25 vias`, `[WARNING STA-1171] ... line 32, default_max_transition is 0.0.` (src/ant/test/check_grt1.ok:1-3). Levels TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL (Logger.h:384). `-log` duplicates stdout stream.
- .odb: binary; magic u32 `0x41544845 0x4E414442` ("ATHE""NADB"), schema_major 0 (unused), schema_minor u32, current rev 141, min readable 57 (src/odb/src/db/dbDatabase.h:50-53, dbDatabase.cpp:84-85,286-313). Forward-incompatible across revs — adapter must read with the SAME build's odb (wheel or `read_db`), never parse bytes. Optional gzip via `-compression` (warns ORD-78 if name lacks .gz).
- SPEF (IEEE 1481-1999): header writer src/rcx/src/extSpef.cpp:1685-1712. Real example (src/rcx/test/coordinates.spefok:1-14): `*SPEF "ieee 1481-1999" / *DESIGN "gcd" / *DATE "02:21:44 Saturday March 28, 2026" / *VENDOR "The OpenROAD Project" / *PROGRAM "OpenROAD" / *VERSION "26Q1-..." / *DESIGN_FLOW "NAME_SCOPE LOCAL" "PIN_CAP NONE" / *DIVIDER / / *DELIMITER : / *BUS_DELIMITER [] / *T_UNIT 1 NS / *C_UNIT 1 PF / *R_UNIT 1 OHM / *L_UNIT 1 HENRY`, then `*NAME_MAP` (`*57 _000_`), `*D_NET`/`*R_`/`*C_` sections. NOTE `*DATE` embeds wall-clock → byte-nondeterministic; normalize before golden-compare. `-coordinates` adds `*XY` coords.
- DRC TR (writeTR, dbMarker.cpp:235-280): per marker: `violation type: <ViolName>\n\tsrcs:[ net:<n> | inst:<i> | iterm:<inst/term> | bterm:<n> | obstruction: ]*\n[\tcomment: <c>\n]\tbbox = (<x1>, <y1>) - (<x2>, <y2>) on Layer <layer>\n` — coords MICRONS, `%.4f`. Markers pre-sorted by (layer,xMin,yMin,xMax,yMax,viol,sources) (TritonRoute.cpp:1396-1444) → deterministic order.
- Antenna (AntennaReport.cc:18-58): `Net: <n>\n  Pin:   <inst>/<mterm> (<master>)\n    Layer: <l>\n      {Partial|Cumulative} area ratio: %7.2f\n      Required ratio: %7.2f (<Gate area|Cumulative area|Side area|Cumulative side area>) [(VIOLATED)]\n` (blank line between layers/pins). Only violating nets unless -verbose.
- CTS (TritonCTS.cpp:618-635): `Total number of Clock Roots: N.\nTotal number of Buffers Inserted: N.\nTotal number of Clock Subnets: N.\nTotal number of Sinks: N.\n{Buffers|Cells} used:\n  <master>: <count>\n[Dummys used:\n  ...]` (note "Dummys" typo is literal).
- Guides: above (§1#17); boxes in DBU integers. DEF/LEF grammars: in-repo specs at src/odb/doc (docs: main/src/odb/doc/{LEF,DEF}_Grammar.html). CDL: src/odb/src/cdl/cdl.cpp. Verilog: OpenSTA `sta::write_verilog_cmd`.
- SDC/SDF/STA reports: UNINSPECTED (empty submodule); grammar authority is https://opensta.readthedocs.io + audit's STA-text residue (report_checks Startpoint:/Endpoint:/slack (MET|VIOLATED), report_wns/tns scalars).

## 3. Python bindings verdict

3. PYTHON BINDINGS — AUDIT ROW NEEDS CORRECTION
Audit claims "`openroad -python` exposes ord/odb/sta/... (SWIG Tcl+Python, test/python/)". STALE on all three counts: (a) `openroad -python` is now a HARD ERROR — src/Main.cc:143-148: "Error: -python is not supported. For the Python API, install the openroad wheel: see docs/user/Bazel.md." → rc 1. (b) There is no test/python/ dir (tests are test/*.py run against the wheel). (c) Tcl+Python hybrid is gone; API is a Bazel-built wheel: `bazelisk build //python/openroad:openroad_wheel; pip install bazel-bin/python/openroad/openroad-*.whl` (docs/user/Bazel.md:190-211). The PyPI-squat warning STANDS (never `pip install openroad` from PyPI — wheel is built from this source; wheel_test.py proves install+import: python/openroad/wheel_test.py:21-36).
What exists (import path → native result reads):
- `from openroad import Tech, Design, Timing` + `import odb` (+ per-tool modules auto-loaded: ant,cgt,cts,dpl,drt,exa,fin,fsv,gpl,grt,ifp,par,pdn,ppl,psm,rcx,rmp,rsz,stt,tap,utl,wmk — python/openroad/__init__.py:7-13; all served from one _openroad.so via _openroad_loader.py: EXTENSIONS).
- `Tech()`: readLef/readLiberty, getDB()/getTech(), unit scales (test/timing_api.py:1-44 shows canonical session: Tech→readLiberty→readLef→Design→readDef→Timing).
- `Design(tech)`: readVerilog/readDef/link/readDb/writeDb/writeDef, getBlock(), per-tool handles getAntennaChecker/getTritonRoute/getGlobalRouter/... (include/ord/Design.h:140-201), `evalTclString()` escape hatch (Design.h:160). Keep Tech alive while Design lives.
- `Timing(design)`: getWorstSlack/getTotalNegativeSlack(MinMax), getEndpointSlacks→list[EndpointSlack{iterm,bterm,slack}], getTimingPaths→list[TimingPathInfo{slack,path_delay,arrival,required,skew,logic_delay,logic_depth,fanout,start/end iterm|bterm,clocks,path_group,arcs[]}], getClockInfo, getNetCap, static/dynamicPower (include/ord/Timing.h:92-169; structs :42-88). Units: Liberty/DBU floats; time in Liberty time-unit scale (tech.timeScale()).
- `odb` (python/openroad/odb.py → src.odb.odb_py): full queryable DB — dbDatabase/dbBlock/getNets/getInsts/getMarkers/getMarkerCategories, LEF/DEF/GDS readers where wrapped. This is the .odb/result reader the audit meant.
Verdict: KEEP-BINDINGS still correct, but via wheel-import + dump-first (subprocess run writes .odb/metrics/SPEF/reports; a separate `python -c "import openroad..."` reads them), never `openroad -python`.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (no file/API escape)
- `report_congestion` (GlobalRouter.tcl:585-591), `report_timing_histogram`, `report_logic_depth_histogram` (dbSta.tcl:39+), `report_design_area`, `check_placement` detail, `report_dft_plan/config`, `report_layer_rc`, `report_physical_clusters`, per-iteration DRT `drc_report_iter_step` progress, final `DRT::drv`/violation counts (also mirrored as metrics — prefer metrics), and all `[INFO/WARNING/ERROR TOOL-NNNN]` diagnostics incl. `utl::error` text. Why: these call `logger_->report/info` with no filename parameter and return void/bool; C++ never opens a side file. Escapes where they exist: (i) `-file`/`-out_file`/`-report_file` variants (wire_length, detours, cell_usage, cts, antennas); (ii) generic Tcl redirect `cmd > file` (explicitly in rsz report_floating_nets/long_wires signatures); (iii) `-log` capture + TOOL-NNNN-anchored regex. GDS-out has the opposite gap: C++-only, no Tcl/CLI at all (§1#27). STA text reports: only stdout unless Tcl-redirected (per audit residue note).

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text)
1. BINDINGS (primary): `-metrics out.json` for all scalars (timing/power/area/drv/antenna/congestion counts); wheel `openroad`/`odb` dump-first reads of `write_db` checkpoints for geometry/netlist/markers (`block.getMarkers()`, categories with source "DRT"), `Timing(design).getEndpointSlacks/getTimingPaths` instead of scraping report_checks. 2. STRUCTURED FILES: SPEF (IEEE 1481; strip `*DATE` before compare), DEF 5.8/LEF (in-repo grammars), TR DRC report (`-output_drc`), antenna `-report_file`, CTS `-out_file`, guides/pin-placement/macro-placement, SDC/SDF via OpenSTA commands. 3. DETERMINISTIC TEXT (last): `-log` + `[LEVEL TOOL-NNNN]` regexes only for the §4 residue; pin on message IDs (e.g. ODB-0227/0128-0133, ANT counts) not prose.
Version evidence: all file:line refs verified at clone f3d27840 (2026-11-02); STA-owned items unverifiable here (empty submodule) — re-verify against OpenSTA 857316f / LibreLane 3.0.17 closure at integration; GDS/OASIS Tcl absence verified by repo-wide grep (only C++ write_gds + read test).

## Weak-evidence gaps (flagged by dissector)

- | 10 | SDC | `write_sdc ...` (OpenSTA submodule — UNINSPECTED, empty clone; usage src/dbSta/test/write_sdc1.tcl:9) | `*.sdc` |
- | 11 | SDF | `write_sdf` (OpenSTA submodule — UNINSPECTED; zero hits in openroad src proper) | `*.sdf` |
- | 12 | STA timing reports | `report_checks/report_tns/report_wns/...` (OpenSTA — UNINSPECTED; audit keeps STA-text grammar as residue) | stdout or Tcl-redirected files |
- - log line: `[LEVEL TOOL-NNNN] message` — e.g. `[INFO ODB-0227] LEF file: sky130hs/sky130hs.tlef, created 13 layers, 25 vias`, `[WARNING STA-1171] ... line 32, default_max_transition is 0.0.` (src/ant/test/check_grt1.ok:1-3). Levels TRACE/DEBUG/INFO/WARNING/ER
- - SDC/SDF/STA reports: UNINSPECTED (empty submodule); grammar authority is https://opensta.readthedocs.io + audit's STA-text residue (report_checks Startpoint:/Endpoint:/slack (MET|VIOLATED), report_wns/tns scalars).
- - `report_congestion` (GlobalRouter.tcl:585-591), `report_timing_histogram`, `report_logic_depth_histogram` (dbSta.tcl:39+), `report_design_area`, `check_placement` detail, `report_dft_plan/config`, `report_layer_rc`, `report_physical_clusters`, per-iteration

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
OPENROAD OUTPUT DISSECTION (review-only)
Clone SHA: f3d27840b65a9571a808a19b06dc0b93b9d4423d, date 2026-11-02 (`git rev-parse HEAD`, `git log -1 --format=%cs` in /tmp/rocket-tool-src/openroad). Shallow clone; NOTE src/sta/ (OpenSTA submodule, .gitmodules) is EMPTY, so STA-owned writers were not inspected — flagged below.
Docs: /tmp/rocket-tool-docs/openroad-index.html present (Sphinx index, "Welcome to OpenROAD's documentation"); substantive pages e.g. main/src/<tool>/README.html, main/src/odb/doc/{LEF,DEF}_Grammar.html, main/src/sta/README.html.
Pin/version: audit row "2.x via LibreLane nix-eda 6.11.0 closure" is loose. provision_toolchain.sh pins LIBRELANE 3.0.17 @64ef80802d3d189b476636d2a6b17888c03304ee and OPENSTA 857316ff001b2a8dbbdc5996944d08a6d38c87ab; NO standalone openroad rev pin (arrives via LibreLane closure). Verified at clone HEAD above (dev post-2.x; e.g. SPEF fixture stamps `*VERSION "26Q1-2613-g4d2ee4c0f7"`, src/rcx/test/coordinates.spefok:6). Build is Bazel-only now (CMakeLists.txt:10-16, CMake removed 2026-11-01).

1. RESULT CHANNELS (one table; producing command → artifact)
| # | Channel | Producer | Artifact/pattern |
|---|---------|----------|------------------|
| 1 | ODB checkpoint (binary, queryable) | `write_db [-compression 0-9] file` (src/OpenRoad.tcl:256-278) / `Design.writeDb()` (include/ord/Design.h:149) | `*.odb[*.gz]`; only CLI input is `-db file` (src/Main.cc:498) |
| 2 | Metrics JSON | CLI `-metrics file.json` (src/Main.cc:156,496) + `utl::metric*` / `report_*_metric` (src/Metrics.tcl) | flat `{"key": value}` JSON |
| 3 | Log file (stdout dup) | CLI `-log file` (src/Main.cc:150) | free text, `[LEVEL TOOL-NNNN]` lines |
| 4 | stdout/stderr log stream | `logger_->report/info/warn/error` everywhere | same line grammar as #3 |
| 5 | DEF | `write_def [-version 5.3..5.8, dflt 5.8] file` (src/OpenRoad.tcl:92-115) | `*.def` |
| 6 | LEF | `write_lef file`; `write_abstract_lef [-bloat_factor N \| -bloat_occupied_layers] file` (src/OpenRoad.tcl:117-146) | `*.lef` |
| 7 | CDL netlist | `write_cdl [-include_fillers] -masters {...} file` (src/OpenRoad.tcl:148-164) | `*.cdl` (src/odb/src/cdl/cdl.cpp) |
| 8 | Verilog | `write_verilog [-sort(IGNORED, warns STA-2065)] [-include_pwr_gnd] [-remove_cells c] file` (src/dbSta/src/dbReadVerilog.tcl:29-50) | `*.v` |
| 9 | SPEF | `write_spef [-net_id id] [-nets list] [-coordinates] file` (src/rcx/src/OpenRCX.tcl:182-209; writer src/rcx/src/extSpef.cpp) | `*.spef`, IEEE 1481-1999 |
| 10 | SDC | `write_sdc ...` (OpenSTA submodule — UNINSPECTED, empty clone; usage src/dbSta/test/write_sdc1.tcl:9) | `*.sdc` |
| 11 | SDF | `write_sdf` (OpenSTA submodule — UNINSPECTED; zero hits in openroad src proper) | `*.sdf` |
| 12 | STA timing reports | `report_checks/report_tns/report_wns/...` (OpenSTA — UNINSPECTED; audit keeps STA-text grammar as residue) | stdout or Tcl-redirected files |
| 13 | DRC markers (in-DB) | `detailed_route` auto-exports to `dbMarkerCategory`/`dbMarker` (src/drt/src/TritonRoute.cpp:1376-1478, source "DRT") | inside .odb; readable via odb API |
| 14 | DRC TR text report | `detailed_route [-output_drc file] [-drc_report_iter_step n] ...` (src/drt/src/TritonRoute.tcl:4-70) → `dbMarkerCategory::writeTR` (src/odb/src/db/dbMarker.cpp:235) | `violation type:` blocks (grammar §2) |
| 15 | Antenna report | `check_antennas [-verbose] [-report_file f] [-net n]` (src/ant/src/AntennaChecker.tcl:4-38; returns violating-net count; metrics `antenna__violating__nets/pins`, AntennaChecker.cc:1168-1170) | `Net:/Pin:/Layer:` blocks (grammar §2); golden src/ant/test/check_grt1.ok |
| 16 | CTS metrics | `report_cts [-out_file file]` (src/cts/src/TritonCTS.tcl:605-619; src/cts/src/TritonCTS.cpp:606-657) | `Total number of ...` + `  master: count` lines |
| 17 | Guides | `write_guides file` (src/odb/src/swig/tcl/odb.tcl:583-596; src/odb/src/db/dbBlock.cpp:3188-3219) | `netname\n(\nxMin yMin xMax yMax layer\n)\n...` (DBU ints, nets strcmp-sorted) |
| 18 | Global-route segments | `write_global_route_segments file` (src/grt/src/GlobalRouter.tcl:412-420) | tool-internal text (round-trips with read_*) |
| 19 | Macro placement | `write_macro_placement file` (odb.tcl:598-615) | `generateMacroPlacementString` text |
| 20 | Pin placement | `write_pin_placement file [-placed_status]` / `place_pins ... -write_pin_placement f` (src/ppl/src/IOPlacer.tcl:199-207; src/ppl/src/IOPlacer.cpp:913-946) | Tcl script: `#Edge: top` + `place_pin -pin_name {n} -layer L -location {x y} -force_to_die_boundary` (microns) |
| 21 | PG SPICE | `write_pg_spice -net n [-vsrc f] [-corner c] [-source_type FULL|BUMPS|STRAPS] file` (src/psm/src/pdnsim.tcl:164-197) | SPICE netlist |
| 22 | PDN analysis files | `analyze_power_grid -net n [-error_file f] [-voltage_file f] [-enable_em -em_outfile f] ...` (src/psm/src/pdnsim.tcl:36-101) | voltage/error/EM text dumps |
| 23 | RCX model/rules | `write_rcx_model` (src/rcx/src/OpenRCX_process.tcl:4), `write_rules` (src/rcx/src/OpenRCX.tcl:411) | extraction rule tables |
| 24 | Wire/detour/congestion | `report_wire_length -net ... [-file f] [-summary]`, `report_net_detours [-file f] [-top_n n]`, `report_congestion` (stdout only), `has_congestion`→bool (src/grt/src/GlobalRouter.tcl:484-611) | stdout or -file |
| 25 | Cell/timing histograms | `report_cell_usage [-verbose] [inst] [-file f] [-stage s]`, `report_timing_histogram`, `report_logic_depth_histogram` (src/dbSta/src/dbSta.tcl:5-100+) | stdout or -file |
| 26 | Misc stdout reports | `report_design_area`, `report_floating_nets [> f]`, `report_long_wires n [> f]`, `check_placement [-verbose]`, `report_dft_plan`, `report_layer_rc`, `report_physical_clusters`, `report_3dic_summary`, ... (many accept Tcl `>` redirect) | stdout |
| 27 | GDSII | C++ ONLY: `odb::write_gds(dbGDSLib*, path)` (src/odb/include/odb/gdsout.h:31; round-trip test src/odb/test/cpp/TestGDSIn.cpp:96,174). NO Tcl command, NO SWIG hit found | `*.gds` |
| 28 | OASIS | NONE found (no writer in src/) | — |
| 29 | 3D / misc | `write_3dbv file` (src/OpenRoad.tcl:181), `write_upf file` (src/upf/src/upf.tcl:15), `write_partition_verilog`, `write_artnet_spec` (src/par/src/partitionmgr.tcl:967-1008) | various |
| 30 | GUI images | `save_animated_gif/save_clocktree_image/save_histogram_image` (src/gui/src/gui.tcl:72-179) | GUI-only, out of scope |
| 31 | In-process Python returns | wheel API (see §3): floats/ints/bools/strings/vectors of db objects + Timing structs | attribution-safe: read-only use after subprocess run |
| 32 | Exit status | `openroad [-exit] cmd.tcl`: TCL_OK→0 else 1 (src/Main.cc:386); usage/`-python`/bad `-web_*`→1; `utl::error` throws → Tcl error (src/utl/include/utl/Logger.h:170-178). WITHOUT `-exit`, falls into REPL (src/Main.cc:428-431) — adapter must pass `-exit` | rc 0/1 only; verdict never in rc alone |

2. FORMAT GRAMMARS (parser-author detail)
- metrics JSON: `MetricsEntry::assembleJSON` (src/utl/src/Metrics.cpp:19-29) emits `{\n\t"key": value,\n...}` — FLAT object, values float|int|string (strings pre-quoted by caller). DUPLICATE keys occur (flow re-emits per stage; see test/aes_nangate45.metrics: `gpl__convergence__iteration` twice, lines 3/9; JSON parsers keep last). Policies KeepFirst/KeepLast/Remove exist (Metrics.cpp:44-86). Key families: `timing__setup|hold__{tns,ws,wns}`, `timing__fmax[__clock:NAME]`, `timing__drv__*`, `power__{internal,switching,leakage,total}`, `design__instance__count__*`, `dpl__*`, `gpl__*`, `route__wirelength__estimated`, `antenna__violating__{nets,pins}`, stage-scoped `run__flow__platform__{}_units` (Metrics.tcl:176-188) with values like `1ns`,`1pF`. Limits-file sibling `*.metrics_limits` (test/aes_nangate45.metrics_limits) is `{"TOOL::metric" : "value"}` with SPACES around colon — different emitter, parse leniently.
- log line: `[LEVEL TOOL-NNNN] message` — e.g. `[INFO ODB-0227] LEF file: sky130hs/sky130hs.tlef, created 13 layers, 25 vias`, `[WARNING STA-1171] ... line 32, default_max_transition is 0.0.` (src/ant/test/check_grt1.ok:1-3). Levels TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL (Logger.h:384). `-log` duplicates stdout stream.
- .odb: binary; magic u32 `0x41544845 0x4E414442` ("ATHE""NADB"), schema_major 0 (unused), schema_minor u32, current rev 141, min readable 57 (src/odb/src/db/dbDatabase.h:50-53, dbDatabase.cpp:84-85,286-313). Forward-incompatible across revs — adapter must read with the SAME build's odb (wheel or `read_db`), never parse bytes. Optional gzip via `-compression` (warns ORD-78 if name lacks .gz).
- SPEF (IEEE 1481-1999): header writer src/rcx/src/extSpef.cpp:1685-1712. Real example (src/rcx/test/coordinates.spefok:1-14): `*SPEF "ieee 1481-1999" / *DESIGN "gcd" / *DATE "02:21:44 Saturday March 28, 2026" / *VENDOR "The OpenROAD Project" / *PROGRAM "OpenROAD" / *VERSION "26Q1-..." / *DESIGN_FLOW "NAME_SCOPE LOCAL" "PIN_CAP NONE" / *DIVIDER / / *DELIMITER : / *BUS_DELIMITER [] / *T_UNIT 1 NS / *C_UNIT 1 PF / *R_UNIT 1 OHM / *L_UNIT 1 HENRY`, then `*NAME_MAP` (`*57 _000_`), `*D_NET`/`*R_`/`*C_` sections. NOTE `*DATE` embeds wall-clock → byte-nondeterministic; normalize before golden-compare. `-coordinates` adds `*XY` coords.
- DRC TR (writeTR, dbMarker.cpp:235-280): per marker: `violation type: <ViolName>\n\tsrcs:[ net:<n> | inst:<i> | iterm:<inst/term> | bterm:<n> | obstruction: ]*\n[\tcomment: <c>\n]\tbbox = (<x1>, <y1>) - (<x2>, <y2>) on Layer <layer>\n` — coords MICRONS, `%.4f`. Markers pre-sorted by (layer,xMin,yMin,xMax,yMax,viol,sources) (TritonRoute.cpp:1396-1444) → deterministic order.
- Antenna (AntennaReport.cc:18-58): `Net: <n>\n  Pin:   <inst>/<mterm> (<master>)\n    Layer: <l>\n      {Partial|Cumulative} area ratio: %7.2f\n      Required ratio: %7.2f (<Gate area|Cumulative area|Side area|Cumulative side area>) [(VIOLATED)]\n` (blank line between layers/pins). Only violating nets unless -verbose.
- CTS (TritonCTS.cpp:618-635): `Total number of Clock Roots: N.\nTotal number of Buffers Inserted: N.\nTotal number of Clock Subnets: N.\nTotal number of Sinks: N.\n{Buffers|Cells} used:\n  <master>: <count>\n[Dummys used:\n  ...]` (note "Dummys" typo is literal).
- Guides: above (§1#17); boxes in DBU integers. DEF/LEF grammars: in-repo specs at src/odb/doc (docs: main/src/odb/doc/{LEF,DEF}_Grammar.html). CDL: src/odb/src/cdl/cdl.cpp. Verilog: OpenSTA `sta::write_verilog_cmd`.
- SDC/SDF/STA reports: UNINSPECTED (empty submodule); grammar authority is https://opensta.readthedocs.io + audit's STA-text residue (report_checks Startpoint:/Endpoint:/slack (MET|VIOLATED), report_wns/tns scalars).

3. PYTHON BINDINGS — AUDIT ROW NEEDS CORRECTION
Audit claims "`openroad -python` exposes ord/odb/sta/... (SWIG Tcl+Python, test/python/)". STALE on all three counts: (a) `openroad -python` is now a HARD ERROR — src/Main.cc:143-148: "Error: -python is not supported. For the Python API, install the openroad wheel: see docs/user/Bazel.md." → rc 1. (b) There is no test/python/ dir (tests are test/*.py run against the wheel). (c) Tcl+Python hybrid is gone; API is a Bazel-built wheel: `bazelisk build //python/openroad:openroad_wheel; pip install bazel-bin/python/openroad/openroad-*.whl` (docs/user/Bazel.md:190-211). The PyPI-squat warning STANDS (never `pip install openroad` from PyPI — wheel is built from this source; wheel_test.py proves install+import: python/openroad/wheel_test.py:21-36).
What exists (import path → native result reads):
- `from openroad import Tech, Design, Timing` + `import odb` (+ per-tool modules auto-loaded: ant,cgt,cts,dpl,drt,exa,fin,fsv,gpl,grt,ifp,par,pdn,ppl,psm,rcx,rmp,rsz,stt,tap,utl,wmk — python/openroad/__init__.py:7-13; all served from one _openroad.so via _openroad_loader.py: EXTENSIONS).
- `Tech()`: readLef/readLiberty, getDB()/getTech(), unit scales (test/timing_api.py:1-44 shows canonical session: Tech→readLiberty→readLef→Design→readDef→Timing).
- `Design(tech)`: readVerilog/readDef/link/readDb/writeDb/writeDef, getBlock(), per-tool handles getAntennaChecker/getTritonRoute/getGlobalRouter/... (include/ord/Design.h:140-201), `evalTclString()` escape hatch (Design.h:160). Keep Tech alive while Design lives.
- `Timing(design)`: getWorstSlack/getTotalNegativeSlack(MinMax), getEndpointSlacks→list[EndpointSlack{iterm,bterm,slack}], getTimingPaths→list[TimingPathInfo{slack,path_delay,arrival,required,skew,logic_delay,logic_depth,fanout,start/end iterm|bterm,clocks,path_group,arcs[]}], getClockInfo, getNetCap, static/dynamicPower (include/ord/Timing.h:92-169; structs :42-88). Units: Liberty/DBU floats; time in Liberty time-unit scale (tech.timeScale()).
- `odb` (python/openroad/odb.py → src.odb.odb_py): full queryable DB — dbDatabase/dbBlock/getNets/getInsts/getMarkers/getMarkerCategories, LEF/DEF/GDS readers where wrapped. This is the .odb/result reader the audit meant.
Verdict: KEEP-BINDINGS still correct, but via wheel-import + dump-first (subprocess run writes .odb/metrics/SPEF/reports; a separate `python -c "import openroad..."` reads them), never `openroad -python`.

4. STDIO-ONLY RESIDUE (no file/API escape)
- `report_congestion` (GlobalRouter.tcl:585-591), `report_timing_histogram`, `report_logic_depth_histogram` (dbSta.tcl:39+), `report_design_area`, `check_placement` detail, `report_dft_plan/config`, `report_layer_rc`, `report_physical_clusters`, per-iteration DRT `drc_report_iter_step` progress, final `DRT::drv`/violation counts (also mirrored as metrics — prefer metrics), and all `[INFO/WARNING/ERROR TOOL-NNNN]` diagnostics incl. `utl::error` text. Why: these call `logger_->report/info` with no filename parameter and return void/bool; C++ never opens a side file. Escapes where they exist: (i) `-file`/`-out_file`/`-report_file` variants (wire_length, detours, cell_usage, cts, antennas); (ii) generic Tcl redirect `cmd > file` (explicitly in rsz report_floating_nets/long_wires signatures); (iii) `-log` capture + TOOL-NNNN-anchored regex. GDS-out has the opposite gap: C++-only, no Tcl/CLI at all (§1#27). STA text reports: only stdout unless Tcl-redirected (per audit residue note).

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text)
1. BINDINGS (primary): `-metrics out.json` for all scalars (timing/power/area/drv/antenna/congestion counts); wheel `openroad`/`odb` dump-first reads of `write_db` checkpoints for geometry/netlist/markers (`block.getMarkers()`, categories with source "DRT"), `Timing(design).getEndpointSlacks/getTimingPaths` instead of scraping report_checks. 2. STRUCTURED FILES: SPEF (IEEE 1481; strip `*DATE` before compare), DEF 5.8/LEF (in-repo grammars), TR DRC report (`-output_drc`), antenna `-report_file`, CTS `-out_file`, guides/pin-placement/macro-placement, SDC/SDF via OpenSTA commands. 3. DETERMINISTIC TEXT (last): `-log` + `[LEVEL TOOL-NNNN]` regexes only for the §4 residue; pin on message IDs (e.g. ODB-0227/0128-0133, ANT counts) not prose.
Version evidence: all file:line refs verified at clone f3d27840 (2026-11-02); STA-owned items unverifiable here (empty submodule) — re-verify against OpenSTA 857316f / LibreLane 3.0.17 closure at integration; GDS/OASIS Tcl absence verified by repo-wide grep (only C++ write_gds + read test).
```
