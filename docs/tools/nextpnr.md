# nextpnr — output dissection

Dissector ref: prior result 18 (text `handoff-7373b0bfa718d40d6bd97d1947aaadcbcf0a09927bfccded9126eb176b51e1dd-c41e97900b86bf3f939fa595365efdb6422b66004b4d807a481de55efee55182.txt`, summary `handoff-bf83d1a1a72d21a55df18eab99f69d3ef7b1d1c6e7b9d5219ed5c03e83f79e52-c41e97900b86bf3f939fa595365efdb6422b66004b4d807a481de55efee55182.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `a2c6479977d64d312686d853a93941744fdbeacf`
- Clone date: `2026-10-31`
- Pin: PIN/VERSION: no per-tool pin in rocket-engine/scripts/provision_toolchain.sh; nextpnr rides oss-cad-suite bundle pin OSS_CAD_SUITE_PIN="20261025". Local bundle binary probed: `nextpnr-ice40 --version` = nextpnr-0.11.1-79-g22c5adf4. DOCS HTML: /tmp/rocket-tool-docs/nextpnr-index.html is a ReadTheDocs
- Doc/source URLs:
  - https://github.com/YosysHQ/nextpnr
  - https://nextpnr.readthedocs.io

### Dissector header (verbatim, whitespace-trimmed)

```text
nextpnr output dissection (REVIEW ONLY, no edits)

CLONE: /tmp/rocket-tool-src/nextpnr/ SHA a2c6479977d64d312686d853a93941744fdbeacf, date 2026-10-31.
PIN/VERSION: no per-tool pin in rocket-engine/scripts/provision_toolchain.sh; nextpnr rides oss-cad-suite bundle pin OSS_CAD_SUITE_PIN="20261025". Local bundle binary probed: `nextpnr-ice40 --version` = nextpnr-0.11.1-79-g22c5adf4. DOCS HTML: /tmp/rocket-tool-docs/nextpnr-index.html is a ReadTheDocs 404 page — fell back to in-repo docs/ + source (upstream: https://nextpnr.readthedocs.io, https://github.com/YosysHQ/nextpnr).
```

## 1. Result channels

1. RESULT CHANNELS (all paths: flag value is literal filename unless noted)
| # | Channel | Producing flag / call | Filename pattern | Arch / scope |
|---|---|---|---|---|
| C1 | Post-PnR JSON netlist | `--write <file>` (common/kernel/command.cc:682-687) | user-given, conventionally `*-routed.json`/`pnr*.json` | all; content stage depends on --pack-only/--no-place/--no-route |
| C2 | Timing+util JSON report | `--report <file>` + opt `--detailed-timing-report` (command.cc:400-403,696-699) | user-given | all |
| C3 | SDF back-annotation | `--sdf <file>` + opt `--sdf-cvc` (command.cc:369-370,690-694 → Context::writeSDF, common/kernel/sdf.cc) | user-given `*.sdf` | all |
| C4 | Placement render | `--placed-svg <file>` (command.cc:405,660-662 → Context::writeSVG, common/kernel/svg.cc) | user-given `*.svg` | all, only if placed |
| C5 | Routing render | `--routed-svg <file>` (command.cc:406,672-674) | user-given `*.svg` | all, only if routed |
| C6 | Router2 congestion CSVs ×4/iter | `--router2-heatmap <prefix>` (command.cc:392-393,526-527; common/route/router2.cc:1746-1769) | `<prefix>_congestion_by_wiretype_<iter>.csv`, `<prefix>_utilisation_by_wiretype_<iter>.csv`, `<prefix>_congestion_by_coordinate_<iter>.csv`, `<prefix>_congestion_by_net_<iter>.csv` | all (router2) |
| C7 | Placer-static density CSVs | `--static-dump-density` (command.cc:386; common/place/placer_static.cc:808-863) | CWD-fixed `out_conc_density_<i>_<j>.csv`, `out_bin_density_*.csv`, `out_bin_phi/ex/ey_*.csv` | static placer only |
| C8 | iCE40 ASC bitstream | `--asc <file>` (ice40/main.cc:77,108-115 → write_asc, ice40/bitstream.cc) | user-given `*.asc` | ice40 (nextpnr-ice40) |
| C9 | ECP5 text config | `--textcfg <file>` (ecp5/main.cc:78,115-118 → write_bitstream, ecp5/bitstream.cc:1609-1619) | user-given, fed to ecppack | ecp5; refused in OOC mode (ecp5/main.cc:111-113) |
| C10 | MachXO2 text config | `--textcfg <file>` (machxo2/main.cc:51,61-68 → machxo2/bitstream.cc:793-803) | user-given | machxo2 |
| C11 | Nexus FASM | `--fasm <file>` (nexus/main.cc:50,61-68 → Context::write_fasm, nexus/fasm.cc) | user-given `*.fasm` | nexus |
| C12 | Xilinx FASM | `-o fasm=<file>` vopt (himbaechel/uarch/xilinx/xilinx.cc:71,477-478 → xilinx/fasm.cc:1864-1869) | user-given `*.fasm` | himbaechel-xilinx |
| C13 | GateMate text bitstream | `-o out=<file>` vopt (himbaechel/uarch/gatemate/gatemate.cc:40,952 → bitstream.cc:520-525) | user-given | himbaechel-gatemate |
| C14 | NG-Ultra JSON bitstream | `-o bit=<file>` vopt (himbaechel/uarch/ng-ultra/ng_ultra.cc:49,447 → bitstream.cc:695-700) | user-given `*.json` | himbaechel-ng-ultra |
| C15 | Mistral RBF bitstream | `--rbf <file>` + opt `--compress-rbf` (mistral/main.cc:51-52,57-69 → rbf_save, binary) | user-given `*.rbf` | mistral (Cyclone V) |
| C16 | Gowin routed JSON | `--write` only; NO bitstream writer in-tree (himbaechel/uarch/gowin/gowin.cc:139-148 lists no output vopt; gowin.cc:184-192 sets `packer.arch/chipdb/partno` header for external `gowin_pack`/Apicula) | user-given `*.json` | himbaechel-gowin |
| C17 | Log mirror file | `--log <file>` (command.cc:310,293-298; appended to log_streams) | user-given; duplicates all stderr log traffic incl. C18–C21 | all |
| C18 | stderr info log | always (default stream; command.cc:284-286; quiet→warnings-only) | — | all |
| C19 | Python in-process results | `--run/--pre-pack/--pre-place/--pre-route/--post-route/--on-failure <script>` (command.cc:323-331); embedded pybind11, ctx global; BUILD_PYTHON default ON (CMakeLists.txt:30,219-229) | scripts write whatever they want (examples: python/dump_design.py, svg_*.py) | all, if built with Python |
| C20 | GUI-only state | `--gui` (command.cc:582-611) | none (interactive) | n/a headless |
| C21 | Exit status | rc: 0 ok, 1 nonfatal timing/error w/ --timing-allow-fail path (had_nonfatal_error, command.cc:706), 125 fatal/log_error/parse fail (command.cc:726-760); "Program finished normally." on success | — | all |

No database channel. No .rpt files: "reports" = C2 JSON only (focus-hint "rpt" does not exist in-tree).

## 2. Format grammars

2. FORMAT GRAMMARS
C1 --write JSON (json/jsonwrite.cc:226-248; schema = Yosys write_json dialect, frontend/json_frontend.cc):
`{"creator":"Next Generation Place and Route (Version <GIT_DESCRIBE>)","modules":{"<top|attrs.module>":{"settings":{k:"str"},"attributes":{...},"ports":{P:{"direction":"input|output|inout","offset"?:"%d","bits":[ ints ]}},"cells":{C:{"hide_name":0|1,"type":"T","parameters":{...},"attributes":{...},"port_directions":{P:"..."},"connections":{P:[ints]}}},"netnames":{N:{"hide_name":0|1,"bits":[<net IdString index>],"attributes":{...}}}}}}`
Ports grouped by basename + `[N]` suffix (jsonwrite.cc:61-103); disconnected bits get dummy ids ≥ idpool+1000. Values: params/attrs all JSON strings via Property::to_string; input side ints parse as 32-bit (json_frontend.cc:103-111). Stage = whatever ran (pack-only → packed; full → placed+routed attrs in cell attrs e.g. BEL locs per-arch). Units: none (structural).
C2 --report JSON (common/kernel/report.cc:244-278; doc docs/report.md; schema comment report.cc:171-241):
`{"utilization":{BELbucket:{"used":int,"available":int}}, "fmax":{clock:{"achieved":MHz float,"constraint":MHz float}}, "critical_paths":[{from:"posedge|negedge <clk>|<async>", to:..., path:[{delay:ns float, from:{cell,port,loc:[x,y]}, to:{...}, type:"clk-to-q|source|logic|routing|setup", net?:str, sources?:[str]}]}], "detailed_net_timings"?:[{net,driver,port,event,endpoints:[{cell,port,event,delay:[minNs,maxNs]}]}]}`
Units: MHz (fmax), ns (delays), grid ints (loc). Fmax formula timing.cc:1105-1112 (1000 or 500/delay_ns by edge). docs/report.md shows only utilization+fmax but writer always adds critical_paths; detailed_net_timings only with --detailed-timing-report.
C3 SDF (common/kernel/sdf.cc:152-215): IEEE-1497-ish `(DELAYFILE (SDFVERSION "3.0")? (DESIGN "…") (VENDOR …) (PROGRAM …) (DIVIDER /|.) (TIMESCALE 1ps) (CELL (CELLTYPE …)(INSTANCE )(DELAY (ABSOLUTE (INTERCONNECT cell/port cell/port (min:typ:max)(min:typ:max))))) (CELL (CELLTYPE T)(INSTANCE inst)(DELAY (ABSOLUTE (IOPATH a b delays))) (TIMINGCHECK ((SETUPHOLD|SETUP|HOLD|PERIOD|WIDTH) …))))`. --sdf-cvc flips divider `/`→`.` and port separator. Delays in ps timescale, min:typ:max triples (sdf.cc:123-135).
C4/C5 SVG (common/kernel/svg.cc:127): `<svg viewBox="0 0 W H" width height xmlns=…>` + rect/line per bel/wire; placed uses flags "scale=50 hide_routing", routed "scale=500" (command.cc:661,673). No schema; visual only.
C6 CSVs (router2.cc:1417-1480): (a) wiretype: header `type,bound=0,bound=1,…` rows `<wiretype>,<counts…>`; (b) utilisation: `<wiretype>,<int>` no header; (c) coordinate: (gridX+1)×(gridY+1) int matrix, `v,` per cell, newline per x; (d) by-net: `<net>,<int>` (over-congestion sum; code continues past line 1480 same pattern). Integers, comma-delimited, LF.
C7: same int-matrix CSV convention via write_csv (placer_static.cc:808-863), fixed CWD names.
C8 ASC (ice40/bitstream.cc:301-928): line grammar: `.comment …`, `.device 384|1k|5k|8k|u4k`, `<TileType> <x> <y>` + rows of `0/1` bits + blank line, `.ram_data <x> <y>` + lowercase hex nibbles, `.extra_bit <x> <y> <bit>`, `.sym <wireidx> <netname>`. Consumed by icepack (icestorm) → .bin. Real header example shape: `.comment from next-pnr` / `.device 8k`.
C9/C10 textcfg: Trellis `ChipConfig` text (`operator<< bitgen.cc`, ecp5/bitstream.cc:1617): `TILE:KEY VALUE` / `.MODE`/enum lines e.g. `EBR_….MODE PDPW16KD` (ecp5/bitstream.cc:999-1026); input to ecppack. No in-repo schema file; grammar owned by prjtrellis.
C11/C12 FASM (nexus/fasm.cc:60-94; xilinx/fasm.cc:1850-1869): standard FASM (https://fasm.readthedocs.io): `TILE.FEATURE` enables, `TILE.PIP.DST.SRC` (nexus/fasm.cc:218), `FEATURE = N'b101…`, `{ key="value" }` annotations, `#` comments. Nexus emits via push/pop dotted context (fasm.cc:44-75).
C13 GateMate: ad-hoc textual `ChipConfig` (key/value per tile/cell; bitstream.cc:281-300ff), vendor assembly downstream. C14 NG-Ultra: JSON bitstream via BitstreamJsonBackend::write_json (ng-ultra/bitstream.cc:695-700). C15 RBF: raw binary Altera RBF (byte stream; mistral/main.cc:63-69, optional compress).
C17/C18 log grammar (common/kernel/log.cc:166-187, command.cc:284-298): prefixes `Info: `, `Warning: `, `Error: ` (fatal via logv_error), blank separators; all to stderr (+ --log file). Key machine-ish lines:
- `Device utilisation:` (design_utils.cc:29-47) then `%20s: %7d/%7d %5d%%` per BEL bucket. Mirrors C2.utilization (same getBelBucket* source).
- `Max frequency for clock '<clk>': %.02f MHz (PASS|FAIL at %.02f MHz)` (timing_log.cc:228-234); xclock variant `Max frequency for <ev> -> <ev>: …` (:313-319); `No Fmax available; no interior timing paths found…` when empty.
- `Critical path report for clock '<c>' (<edge> -> <edge>):` + header `type curr  total name` then `%10s %5.2f %5.2f Source <cell>.<port>` (logic) or `… Net <net> (x1,y1) -> (x2,y2)` + `Sink <cell>.<port>` (timing_log.cc:72-146); trailer `%.2f ns logic, %.2f ns routing`. Units ns, 2dp. Delays float ns; verbose adds per-pip breakdown + `prediction:/estimate:` lines.
- `%zu Hold/min time violations (showing 10 worst paths):` + per-path `Hold/min time violation for …` as nonfatal-error unless timing/allowFail (timing_log.cc:174-201).
- `Found %d combinational loops:` + `loop %d:` + `cell.port (…)` (timing.cc:213-218).
- `Generated random seed: %u` with --randomize-seed; `Program finished normally.` on success; footer warning/error counts (command.cc:718-724).

## 3. Python bindings verdict

3. PYTHON BINDINGS (audit row: "build-time pybind11 API, bundle availability unverified" — now PARTLY CORRECTED)
Exists: yes, embedded pybind11 (`nextpnrpy_<arch>` module per arch via MODULE_NAME macro, common/kernel/pybindings.cc:38-42; arch impls e.g. ice40/ecp5/machxo2/generic arch_pybindings.cc). Import path: NOT pip-installable; embedded interpreter inside each nextpnr-<arch> binary; scripts get global `ctx` (docs/python.md). Returns natively: full live Context — ctx.cells/nets (CellInfo/NetInfo wrappers), wires→pip routing maps, bel/wire/pip query+bind API, timing_result incl. ClockFmaxMap {achieved, constraint} (pybindings.cc:248-300; arch_pybindings_shared.h whole file; docs/python.md "Binding Overview"/"Netlist Access"). Can write any file itself (C19) incl. ctx.writeSVG; example scripts in python/ (dump_design.py, report_hierarchy.py, svg_placement.py). Bundle availability: VERIFIED present in local oss-cad-suite binary — `nextpnr-ice40 --help` lists --run/--pre-pack/--pre-place/--pre-route/--post-route/--on-failure and --report (binary nextpnr-0.11.1-79-g22c5adf4). Caveat: in-process execution only (violates TOOL-OUTPUTS "bindings for READING" unless used as post-route dumper writing a file for the adapter to read — same pattern as generic/examples/*bitstream.py*).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE (never written to a file channel)
- Utilisation table text (same numbers as C2 but % formatting + bucket list) — convenience duplicate; file form exists (C2), text adds nothing.
- Fmax PASS/FAIL verdict lines + xclock fmax lines — verdict (`PASS|FAIL`) is TEXT-ONLY: C2 carries achieved/constraint numbers but no verdict string; adapter must recompute (target<fmax per timing_log.cc:225).
- Critical-path segment tables (per-segment curr/total, Source/Net/Sink lines, logic/routing split, Defined in: src lists) — partially in C2 (critical_paths has from/to/loc/delay/type/net/sources) but curr/total accumulations, `logic X ns, routing Y ns` split, and hold-violation paths (min_delay_violations, top-10) are TEXT-ONLY (report.cc has no min-delay section).
- Slack histogram (build_slack_histogram_report, timing.cc:1175+) — printed via log_timing_results only; NOT in C2 (report.cc never reads slack_histogram).
- Combinational-loop listings, per-pip verbose breakdown, prediction/estimate lines — diagnostics, text-only by design (verbose-gated).
- Footer error/warning counts + "Program finished normally." + exit code — text+rc only; no file.
Why: report.cc was built for build-system integration (docs/report.md: utilisation+fmax only, later +critical paths) while timing_log.cc is the human console; min-delay/histogram/loops were never ported to the JSON writer.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
Tool is DEFER/off_mvp FPGA per audit — if staffed later: (1) C2 --report JSON (util+fmax+critical paths; add --detailed-timing-report for per-net) — first choice, json11 dump, stable keys, docs/report.md + report.cc:171-241 schema. (2) C1 --write JSON (Yosys-JSON dialect; placement/routing in attrs; Gowin C16 is the ONLY channel, header packer.arch/chipdb/partno). (3) C3 SDF for delays (IEEE-ish, 1ps). (4) Bitstream/config outputs C8–C15 pass-through opaque (arch-vendor grammars; validate by downstream tool, not regex). (5) Python C19 only as --post-route dumper script emitting JSON (never in-process execution per TOOL-OUTPUTS rule); bundle embeds it (verified). (6) Text scrape last resort, pinned: Fmax verdict regex `Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)`, hold-violation header, exit rc (0/1/125). Version evidence: source SHA+date above; adapter pin = oss-cad-suite 20261025 (bundle); observed binary nextpnr-0.11.1-79-g22c5adf4.

## Weak-evidence gaps (flagged by dissector)

- 4. STDIO-ONLY RESIDUE (never written to a file channel)
- PIN/VERSION: no per-tool pin in rocket-engine/scripts/provision_toolchain.sh; nextpnr rides oss-cad-suite bundle pin OSS_CAD_SUITE_PIN="20261025". Local bundle binary probed: `nextpnr-ice40 --version` = nextpnr-0.11.1-79-g22c5adf4. DOCS HTML: /tmp/rocket-tool-
- - `Max frequency for clock '<clk>': %.02f MHz (PASS|FAIL at %.02f MHz)` (timing_log.cc:228-234); xclock variant `Max frequency for <ev> -> <ev>: …` (:313-319); `No Fmax available; no interior timing paths found…` when empty.

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
nextpnr output dissection (REVIEW ONLY, no edits)

CLONE: /tmp/rocket-tool-src/nextpnr/ SHA a2c6479977d64d312686d853a93941744fdbeacf, date 2026-10-31.
PIN/VERSION: no per-tool pin in rocket-engine/scripts/provision_toolchain.sh; nextpnr rides oss-cad-suite bundle pin OSS_CAD_SUITE_PIN="20261025". Local bundle binary probed: `nextpnr-ice40 --version` = nextpnr-0.11.1-79-g22c5adf4. DOCS HTML: /tmp/rocket-tool-docs/nextpnr-index.html is a ReadTheDocs 404 page — fell back to in-repo docs/ + source (upstream: https://nextpnr.readthedocs.io, https://github.com/YosysHQ/nextpnr).

1. RESULT CHANNELS (all paths: flag value is literal filename unless noted)
| # | Channel | Producing flag / call | Filename pattern | Arch / scope |
|---|---|---|---|---|
| C1 | Post-PnR JSON netlist | `--write <file>` (common/kernel/command.cc:682-687) | user-given, conventionally `*-routed.json`/`pnr*.json` | all; content stage depends on --pack-only/--no-place/--no-route |
| C2 | Timing+util JSON report | `--report <file>` + opt `--detailed-timing-report` (command.cc:400-403,696-699) | user-given | all |
| C3 | SDF back-annotation | `--sdf <file>` + opt `--sdf-cvc` (command.cc:369-370,690-694 → Context::writeSDF, common/kernel/sdf.cc) | user-given `*.sdf` | all |
| C4 | Placement render | `--placed-svg <file>` (command.cc:405,660-662 → Context::writeSVG, common/kernel/svg.cc) | user-given `*.svg` | all, only if placed |
| C5 | Routing render | `--routed-svg <file>` (command.cc:406,672-674) | user-given `*.svg` | all, only if routed |
| C6 | Router2 congestion CSVs ×4/iter | `--router2-heatmap <prefix>` (command.cc:392-393,526-527; common/route/router2.cc:1746-1769) | `<prefix>_congestion_by_wiretype_<iter>.csv`, `<prefix>_utilisation_by_wiretype_<iter>.csv`, `<prefix>_congestion_by_coordinate_<iter>.csv`, `<prefix>_congestion_by_net_<iter>.csv` | all (router2) |
| C7 | Placer-static density CSVs | `--static-dump-density` (command.cc:386; common/place/placer_static.cc:808-863) | CWD-fixed `out_conc_density_<i>_<j>.csv`, `out_bin_density_*.csv`, `out_bin_phi/ex/ey_*.csv` | static placer only |
| C8 | iCE40 ASC bitstream | `--asc <file>` (ice40/main.cc:77,108-115 → write_asc, ice40/bitstream.cc) | user-given `*.asc` | ice40 (nextpnr-ice40) |
| C9 | ECP5 text config | `--textcfg <file>` (ecp5/main.cc:78,115-118 → write_bitstream, ecp5/bitstream.cc:1609-1619) | user-given, fed to ecppack | ecp5; refused in OOC mode (ecp5/main.cc:111-113) |
| C10 | MachXO2 text config | `--textcfg <file>` (machxo2/main.cc:51,61-68 → machxo2/bitstream.cc:793-803) | user-given | machxo2 |
| C11 | Nexus FASM | `--fasm <file>` (nexus/main.cc:50,61-68 → Context::write_fasm, nexus/fasm.cc) | user-given `*.fasm` | nexus |
| C12 | Xilinx FASM | `-o fasm=<file>` vopt (himbaechel/uarch/xilinx/xilinx.cc:71,477-478 → xilinx/fasm.cc:1864-1869) | user-given `*.fasm` | himbaechel-xilinx |
| C13 | GateMate text bitstream | `-o out=<file>` vopt (himbaechel/uarch/gatemate/gatemate.cc:40,952 → bitstream.cc:520-525) | user-given | himbaechel-gatemate |
| C14 | NG-Ultra JSON bitstream | `-o bit=<file>` vopt (himbaechel/uarch/ng-ultra/ng_ultra.cc:49,447 → bitstream.cc:695-700) | user-given `*.json` | himbaechel-ng-ultra |
| C15 | Mistral RBF bitstream | `--rbf <file>` + opt `--compress-rbf` (mistral/main.cc:51-52,57-69 → rbf_save, binary) | user-given `*.rbf` | mistral (Cyclone V) |
| C16 | Gowin routed JSON | `--write` only; NO bitstream writer in-tree (himbaechel/uarch/gowin/gowin.cc:139-148 lists no output vopt; gowin.cc:184-192 sets `packer.arch/chipdb/partno` header for external `gowin_pack`/Apicula) | user-given `*.json` | himbaechel-gowin |
| C17 | Log mirror file | `--log <file>` (command.cc:310,293-298; appended to log_streams) | user-given; duplicates all stderr log traffic incl. C18–C21 | all |
| C18 | stderr info log | always (default stream; command.cc:284-286; quiet→warnings-only) | — | all |
| C19 | Python in-process results | `--run/--pre-pack/--pre-place/--pre-route/--post-route/--on-failure <script>` (command.cc:323-331); embedded pybind11, ctx global; BUILD_PYTHON default ON (CMakeLists.txt:30,219-229) | scripts write whatever they want (examples: python/dump_design.py, svg_*.py) | all, if built with Python |
| C20 | GUI-only state | `--gui` (command.cc:582-611) | none (interactive) | n/a headless |
| C21 | Exit status | rc: 0 ok, 1 nonfatal timing/error w/ --timing-allow-fail path (had_nonfatal_error, command.cc:706), 125 fatal/log_error/parse fail (command.cc:726-760); "Program finished normally." on success | — | all |

No database channel. No .rpt files: "reports" = C2 JSON only (focus-hint "rpt" does not exist in-tree).

2. FORMAT GRAMMARS
C1 --write JSON (json/jsonwrite.cc:226-248; schema = Yosys write_json dialect, frontend/json_frontend.cc):
`{"creator":"Next Generation Place and Route (Version <GIT_DESCRIBE>)","modules":{"<top|attrs.module>":{"settings":{k:"str"},"attributes":{...},"ports":{P:{"direction":"input|output|inout","offset"?:"%d","bits":[ ints ]}},"cells":{C:{"hide_name":0|1,"type":"T","parameters":{...},"attributes":{...},"port_directions":{P:"..."},"connections":{P:[ints]}}},"netnames":{N:{"hide_name":0|1,"bits":[<net IdString index>],"attributes":{...}}}}}}`
Ports grouped by basename + `[N]` suffix (jsonwrite.cc:61-103); disconnected bits get dummy ids ≥ idpool+1000. Values: params/attrs all JSON strings via Property::to_string; input side ints parse as 32-bit (json_frontend.cc:103-111). Stage = whatever ran (pack-only → packed; full → placed+routed attrs in cell attrs e.g. BEL locs per-arch). Units: none (structural).
C2 --report JSON (common/kernel/report.cc:244-278; doc docs/report.md; schema comment report.cc:171-241):
`{"utilization":{BELbucket:{"used":int,"available":int}}, "fmax":{clock:{"achieved":MHz float,"constraint":MHz float}}, "critical_paths":[{from:"posedge|negedge <clk>|<async>", to:..., path:[{delay:ns float, from:{cell,port,loc:[x,y]}, to:{...}, type:"clk-to-q|source|logic|routing|setup", net?:str, sources?:[str]}]}], "detailed_net_timings"?:[{net,driver,port,event,endpoints:[{cell,port,event,delay:[minNs,maxNs]}]}]}`
Units: MHz (fmax), ns (delays), grid ints (loc). Fmax formula timing.cc:1105-1112 (1000 or 500/delay_ns by edge). docs/report.md shows only utilization+fmax but writer always adds critical_paths; detailed_net_timings only with --detailed-timing-report.
C3 SDF (common/kernel/sdf.cc:152-215): IEEE-1497-ish `(DELAYFILE (SDFVERSION "3.0")? (DESIGN "…") (VENDOR …) (PROGRAM …) (DIVIDER /|.) (TIMESCALE 1ps) (CELL (CELLTYPE …)(INSTANCE )(DELAY (ABSOLUTE (INTERCONNECT cell/port cell/port (min:typ:max)(min:typ:max))))) (CELL (CELLTYPE T)(INSTANCE inst)(DELAY (ABSOLUTE (IOPATH a b delays))) (TIMINGCHECK ((SETUPHOLD|SETUP|HOLD|PERIOD|WIDTH) …))))`. --sdf-cvc flips divider `/`→`.` and port separator. Delays in ps timescale, min:typ:max triples (sdf.cc:123-135).
C4/C5 SVG (common/kernel/svg.cc:127): `<svg viewBox="0 0 W H" width height xmlns=…>` + rect/line per bel/wire; placed uses flags "scale=50 hide_routing", routed "scale=500" (command.cc:661,673). No schema; visual only.
C6 CSVs (router2.cc:1417-1480): (a) wiretype: header `type,bound=0,bound=1,…` rows `<wiretype>,<counts…>`; (b) utilisation: `<wiretype>,<int>` no header; (c) coordinate: (gridX+1)×(gridY+1) int matrix, `v,` per cell, newline per x; (d) by-net: `<net>,<int>` (over-congestion sum; code continues past line 1480 same pattern). Integers, comma-delimited, LF.
C7: same int-matrix CSV convention via write_csv (placer_static.cc:808-863), fixed CWD names.
C8 ASC (ice40/bitstream.cc:301-928): line grammar: `.comment …`, `.device 384|1k|5k|8k|u4k`, `<TileType> <x> <y>` + rows of `0/1` bits + blank line, `.ram_data <x> <y>` + lowercase hex nibbles, `.extra_bit <x> <y> <bit>`, `.sym <wireidx> <netname>`. Consumed by icepack (icestorm) → .bin. Real header example shape: `.comment from next-pnr` / `.device 8k`.
C9/C10 textcfg: Trellis `ChipConfig` text (`operator<< bitgen.cc`, ecp5/bitstream.cc:1617): `TILE:KEY VALUE` / `.MODE`/enum lines e.g. `EBR_….MODE PDPW16KD` (ecp5/bitstream.cc:999-1026); input to ecppack. No in-repo schema file; grammar owned by prjtrellis.
C11/C12 FASM (nexus/fasm.cc:60-94; xilinx/fasm.cc:1850-1869): standard FASM (https://fasm.readthedocs.io): `TILE.FEATURE` enables, `TILE.PIP.DST.SRC` (nexus/fasm.cc:218), `FEATURE = N'b101…`, `{ key="value" }` annotations, `#` comments. Nexus emits via push/pop dotted context (fasm.cc:44-75).
C13 GateMate: ad-hoc textual `ChipConfig` (key/value per tile/cell; bitstream.cc:281-300ff), vendor assembly downstream. C14 NG-Ultra: JSON bitstream via BitstreamJsonBackend::write_json (ng-ultra/bitstream.cc:695-700). C15 RBF: raw binary Altera RBF (byte stream; mistral/main.cc:63-69, optional compress).
C17/C18 log grammar (common/kernel/log.cc:166-187, command.cc:284-298): prefixes `Info: `, `Warning: `, `Error: ` (fatal via logv_error), blank separators; all to stderr (+ --log file). Key machine-ish lines:
- `Device utilisation:` (design_utils.cc:29-47) then `%20s: %7d/%7d %5d%%` per BEL bucket. Mirrors C2.utilization (same getBelBucket* source).
- `Max frequency for clock '<clk>': %.02f MHz (PASS|FAIL at %.02f MHz)` (timing_log.cc:228-234); xclock variant `Max frequency for <ev> -> <ev>: …` (:313-319); `No Fmax available; no interior timing paths found…` when empty.
- `Critical path report for clock '<c>' (<edge> -> <edge>):` + header `type curr  total name` then `%10s %5.2f %5.2f Source <cell>.<port>` (logic) or `… Net <net> (x1,y1) -> (x2,y2)` + `Sink <cell>.<port>` (timing_log.cc:72-146); trailer `%.2f ns logic, %.2f ns routing`. Units ns, 2dp. Delays float ns; verbose adds per-pip breakdown + `prediction:/estimate:` lines.
- `%zu Hold/min time violations (showing 10 worst paths):` + per-path `Hold/min time violation for …` as nonfatal-error unless timing/allowFail (timing_log.cc:174-201).
- `Found %d combinational loops:` + `loop %d:` + `cell.port (…)` (timing.cc:213-218).
- `Generated random seed: %u` with --randomize-seed; `Program finished normally.` on success; footer warning/error counts (command.cc:718-724).

3. PYTHON BINDINGS (audit row: "build-time pybind11 API, bundle availability unverified" — now PARTLY CORRECTED)
Exists: yes, embedded pybind11 (`nextpnrpy_<arch>` module per arch via MODULE_NAME macro, common/kernel/pybindings.cc:38-42; arch impls e.g. ice40/ecp5/machxo2/generic arch_pybindings.cc). Import path: NOT pip-installable; embedded interpreter inside each nextpnr-<arch> binary; scripts get global `ctx` (docs/python.md). Returns natively: full live Context — ctx.cells/nets (CellInfo/NetInfo wrappers), wires→pip routing maps, bel/wire/pip query+bind API, timing_result incl. ClockFmaxMap {achieved, constraint} (pybindings.cc:248-300; arch_pybindings_shared.h whole file; docs/python.md "Binding Overview"/"Netlist Access"). Can write any file itself (C19) incl. ctx.writeSVG; example scripts in python/ (dump_design.py, report_hierarchy.py, svg_placement.py). Bundle availability: VERIFIED present in local oss-cad-suite binary — `nextpnr-ice40 --help` lists --run/--pre-pack/--pre-place/--pre-route/--post-route/--on-failure and --report (binary nextpnr-0.11.1-79-g22c5adf4). Caveat: in-process execution only (violates TOOL-OUTPUTS "bindings for READING" unless used as post-route dumper writing a file for the adapter to read — same pattern as generic/examples/*bitstream.py*).

4. STDIO-ONLY RESIDUE (never written to a file channel)
- Utilisation table text (same numbers as C2 but % formatting + bucket list) — convenience duplicate; file form exists (C2), text adds nothing.
- Fmax PASS/FAIL verdict lines + xclock fmax lines — verdict (`PASS|FAIL`) is TEXT-ONLY: C2 carries achieved/constraint numbers but no verdict string; adapter must recompute (target<fmax per timing_log.cc:225).
- Critical-path segment tables (per-segment curr/total, Source/Net/Sink lines, logic/routing split, Defined in: src lists) — partially in C2 (critical_paths has from/to/loc/delay/type/net/sources) but curr/total accumulations, `logic X ns, routing Y ns` split, and hold-violation paths (min_delay_violations, top-10) are TEXT-ONLY (report.cc has no min-delay section).
- Slack histogram (build_slack_histogram_report, timing.cc:1175+) — printed via log_timing_results only; NOT in C2 (report.cc never reads slack_histogram).
- Combinational-loop listings, per-pip verbose breakdown, prediction/estimate lines — diagnostics, text-only by design (verbose-gated).
- Footer error/warning counts + "Program finished normally." + exit code — text+rc only; no file.
Why: report.cc was built for build-system integration (docs/report.md: utilisation+fmax only, later +critical paths) while timing_log.cc is the human console; min-delay/histogram/loops were never ported to the JSON writer.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
Tool is DEFER/off_mvp FPGA per audit — if staffed later: (1) C2 --report JSON (util+fmax+critical paths; add --detailed-timing-report for per-net) — first choice, json11 dump, stable keys, docs/report.md + report.cc:171-241 schema. (2) C1 --write JSON (Yosys-JSON dialect; placement/routing in attrs; Gowin C16 is the ONLY channel, header packer.arch/chipdb/partno). (3) C3 SDF for delays (IEEE-ish, 1ps). (4) Bitstream/config outputs C8–C15 pass-through opaque (arch-vendor grammars; validate by downstream tool, not regex). (5) Python C19 only as --post-route dumper script emitting JSON (never in-process execution per TOOL-OUTPUTS rule); bundle embeds it (verified). (6) Text scrape last resort, pinned: Fmax verdict regex `Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz \((PASS|FAIL) at ([\d.]+) MHz\)`, hold-violation header, exit rc (0/1/125). Version evidence: source SHA+date above; adapter pin = oss-cad-suite 20261025 (bundle); observed binary nextpnr-0.11.1-79-g22c5adf4.
```
