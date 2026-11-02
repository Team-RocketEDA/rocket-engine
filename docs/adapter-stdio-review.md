# Adapter stdio-vs-file recap + migration notes

Synthesis of the four group reviews (checks, sims, implementation,
drivers-native) over all 19 adapters in `src/adapters/`.
Review-only inputs; this doc is the only write.

Pins (grounding): slang via oss-cad-suite 20261025 (adapter verified vs 12.0.0);
sby v0.70; magic 707d67e expect 8.3 (adapter verified 8.3.685);
netgen e310f30 expect 1.5 (adapter verified 1.5.316); klayout 0.30.12
(note: `drc_kl/__init__.py:3` docstring still says 0.28.16 — stale);
opensta 807316f-series pin 857316f (tool DEFERRED per audit);
Yosys 0.70 via oss-cad-suite 20261025; LibreLane 3.0.17 (64ef808);
ngspice 47; iverilog/vvp 14.0; sax 0.18.2 / circulax 0.2.5 /
meow-sim 0.15.0 (uv-managed); gdsfactory 9.51.0 (uv-managed,
`GF_PIN` in `src/adapters/gdsfactory/__init__.py:22`).

## (a) Recap: EASY vs STDIO-PARSE adapters

EASY = parse() never scrapes tool stdio text today (native API, report
files, or engine-owned JSON envelope only). 7 adapters.

| class | adapters |
|---|---|
| EASY (no stdio parse) | connectivity, view_sync, digital_flow, sax, circulax, meow, gdsfactory |
| STDIO-PARSE (≥1 stdio regex/marker) | syntax, drc, drc_kl, lvs_netgen, formal_sby, timing_sta, ngspice, postlayout, cosim, hdl_sim, synth_yosys, extract_magic |

Notes:

- digital_flow: `execute()` tails stdout/stderr into `digital_flow.log`,
  but `parse()` (`:721-828`) never reads stdout/stderr/log — verdicts come
  only from exit code + `design/runs/<tag>/` step-dir scan.
- sax / circulax / meow / gdsfactory: stdout carries exactly one
  engine-owned JSON envelope (`ROCKETEDA_ENVELOPE_BEGIN/END`; meow uses
  dash-form markers via its own `_envelope`), produced by our staged
  drivers from in-process native APIs. No tool-text scraping.
- drc_kl synthetic `VIOL`/`TOTAL` lines are printed by OUR pya script
  (`drc_kl/__init__.py:57-58`), not by klayout — zero drift risk.
- lvs_netgen: `execute` raises when `lvs_report.out` is missing
  (`:374-378`), so the stdout fallback (`:408-414`) is near-dead.

## (b) Per-field migration table

Paths under `rocket-engine/src/adapters/`. Verdicts: ALREADY-FILE |
FILE-AVAILABLE | STDIO-ONLY.

### checks group

| adapter | field | stdio marker today | file alternative + flag + evidence | verdict |
|---|---|---|---|---|
| syntax | diagnostics (`_DIAG_RE :28`, rule `_RULE_RE :29`) | yes: `file:line:col: error\|warning: msg` over stdout+stderr (`:172`) | `--diag-json <file>` ("Dump all diagnostics in JSON format"; `Driver::Options.diagJson`, [slang driver options](https://sv-lang.com/structslang_1_1driver_1_1_driver_1_1_options.html)); added v10.0, present at pin v12 | FILE-AVAILABLE |
| syntax | summary (`_SUMMARY_RE :30`, N errors/M warnings) | yes | same `--diag-json` (counts from array lengths); also `--ast-json` | FILE-AVAILABLE |
| drc | total (`_TOTAL_RE :26`) | yes: `Total DRC errors found: N` | none — DRC verbs print to terminal; only `drc printrules [file]` takes a file and dumps the rule set, not violations ([magic manpage](http://opencircuitdesign.com/magic/manpages/magic_manpage.html)); audit KEEP-PARSE-ONLY case 1 | STDIO-ONLY |
| drc | areas (`_AREA_RE :27`, rule+bbox) | yes: `drc find` + `puts [box values]` + `drc why` | none at pin | STDIO-ONLY |
| drc | tech probe (`Using technology` / `Failed to load technology`, `:116`/`:152`) | yes (probe, not results) | n/a | STDIO-ONLY |
| drc_kl | deck violations (`_parse_lyrdb :113-152`) | no — reads `.lyrdb` RDB XML via `-rd report=` (`:260-287`) | n/a | ALREADY-FILE |
| drc_kl | synthetic `VIOL`/`TOTAL` (`:29-34`) | yes, self-emitted by our pya script | trivial: script could write JSON/RDB instead of `print()` | FILE-AVAILABLE (trivial; lowest value — defensible to keep) |
| lvs_netgen | verdict (`_MATCH_RE :37`, `_MISMATCH_RES :38-41`) | no — `lvs_report.out` file (`:361-384`) | n/a; logfile arg "is the file to dump all output" ([netgen reference](http://opencircuitdesign.com/netgen/reference.html)) | ALREADY-FILE |
| lvs_netgen | nets/instances (`_NET_RE :42`, `_INSTANCE_RE :43`, `:193-236`) | no — same report file | structured sidecar `-json` ("Provide output in JSON format as well as the usual", same reference page); sidecar grammar vs our fields UNVERIFIED | ALREADY-FILE; `-json` FILE-AVAILABLE-PARTIAL |
| formal_sby | status verdict (`_read_status :97-108`) | no — `formal/status` file | n/a | ALREADY-FILE |
| formal_sby | DONE/engine/traces/asserts/cover/errors (`_DONE_RE :47` … `_BARE_ERR_RE :68`, over stdout `:502-520`) | yes | `<task>/logfile.txt` = complete sby log incl. `summary:` lines ([SBY quickstart](https://yosyshq.readthedocs.io/projects/sby/en/latest/quickstart.html)); change: `logtext = formal/logfile.txt if exists else stdout`, same regexes, no flag changes | FILE-AVAILABLE (all fields) |
| timing_sta | errors/warnings (`_ERROR_RE :48`, `_WARNING_RE :49`) | yes (log mirrors stdout) | native redirection: `report_checks … > path.log` (OpenSTA.pdf doc) — append `> <section>.rpt` to the 7 report commands in `_script (:588-600)` | FILE-AVAILABLE |
| timing_sta | margins/paths/CONSTRAINTS/CHECK_SETUP (`:51-63`, `:186-194`, `:435`) | yes | same per-command redirection | FILE-AVAILABLE |
| timing_sta | section markers (`_MARKER_RE :50`) | yes, self-emitted via `puts` (`:601-602`) | n/a (own grammar) | ALREADY-FILE-equivalent |

### sims group

| adapter | field | stdio marker today | file alternative + flag + evidence | verdict |
|---|---|---|---|---|
| ngspice | meas values (`_MEAS_RE :44-48`, over stdout+stderr+log `:431-440`) | yes (3-stream concat) | Tier 1: `-o ngspice.log` already a file — parse log only. Tier 2: `wrdata meas.dat meas_*` + `set wr_singlescale` ([control tutorial](https://ngspice.sourceforge.io/ngspice-control-language-tutorial.html)); alt: `write` rawfile + `set filetype=ascii` (manual ch.16) | FILE-AVAILABLE |
| ngspice | sim_fail detail (`_ERROR_RE :52`) | yes | none — ngspice 47 has no structured error file; quote from the persisted log | STDIO-ONLY |
| postlayout | meas values (`_MEAS_RE :71-75`, `:805-811`) | yes (same concat) | same tier 1/2 as ngspice (`-o postlayout.log`; `wrdata`; `write`+ascii) | FILE-AVAILABLE |
| postlayout | waveforms (`_parse_waveforms_file :340-376`) | no — `wrdata postlayout_waveforms.dat` file (`:485-487`, read `:813`) | n/a | ALREADY-FILE |
| postlayout | sim_fail detail (`_ERROR_RE :80`) | yes | none (same as ngspice) | STDIO-ONLY |
| cosim | analog waveform→bits/SNDR (`_parse_wrdata :567-587`) | no — `wrdata cosim_out.csv` file (`:430-434`, read `:880-882`) | n/a | ALREADY-FILE |
| cosim | analog no-value detail (`_ERROR_RE :76`, `:908-917`) | yes | none (persisted in `-o cosim_ngspice.log :804`) | STDIO-ONLY |
| cosim | digital `COSIM_BITS/COUNT_*/DATA_*` (`:81-83`, `:1039-1060`; bench `$display`) | yes, over vvp stdout+stderr | `vvp -l<logfile>` ("$display and friends send their output both to <stdout> and <stdlog>", [vvp flags](https://steveicarus.github.io/iverilog/usage/vvp_flags.html)); LIVE-VERIFIED byte-identical on vvp 14.0 | FILE-AVAILABLE |
| cosim | digital FATAL/ERROR (via `HdlSimAdapter().parse :1132`) | yes | same `vvp -l` (verified incl. `Time:` lines); one change in `hdl_sim.execute :217-219` covers both | FILE-AVAILABLE |
| hdl_sim | compile diags (`_COMPILE_RE :27`, `:35-49`) | yes, iverilog stderr | NONE: full upstream flag inventory has no diagnostics-file flag ([flags](https://steveicarus.github.io/iverilog/usage/command_line_flags.html)); LIVE-VERIFIED stderr-only | STDIO-ONLY |
| hdl_sim | sim `FATAL:/ERROR:` + `Time:` (`_SIM_RE :28`, `_TIME_RE :29`) | yes, vvp stdout+stderr | `vvp -l<logfile>`; LIVE-VERIFIED byte-identical incl. `Time:` lines | FILE-AVAILABLE |
| sax | `wavelength_nm`, `transmission`, `ports`, `sax_version`, `error{}` (`:395-423`) | envelope only (`extract_envelope(stdout) :366`) | optional: driver also writes `result.json`; not needed | EASY (ALREADY-FILE-equivalent) |
| circulax | `t_s`, `v_V`, `circulax_version` (`:429-443`) | envelope only (`:400`) | same optional `result.json` | EASY (ALREADY-FILE-equivalent) |
| meow | `base/refined/convergence`, `meow_version` (`:381-394`) | envelope only (`:342`) | same optional `result.json` | EASY (ALREADY-FILE-equivalent) |

Note: cosim `_MEAS_RE :75` is defined but never referenced (dead
tripwire, not an output parse) — delete or leave, no behavior.

### implementation group

| adapter | field | stdio marker today | file alternative + flag + evidence | verdict |
|---|---|---|---|---|
| synth_yosys | violations synth_error (`_ERROR_RE :48`, join `:395-399`) | partial: `synth.log` file + stdout/stderr copies (`yosys -q -s synth.ys -l synth.log :349-360`) | same data already in `synth.log` via `-l/--logfile` ([cmd_ref](https://yosyshq.readthedocs.io/projects/yosys/en/stable/cmd_ref.html)); no JSON-diagnostics file at pin | ALREADY-FILE |
| synth_yosys | latch/undriven/warnings (`_WARNING_RE :49`, join `:395-399`) | same partial | same `synth.log` | ALREADY-FILE |
| synth_yosys | cells/wires (`_CELLS_RE :50`, `_WIRES_RE :52`, `_parse_stat :131-182`) | no — `synth_stat.txt` file (`tee -o … stat :483/487`) | structured upgrade: `tee -q -o synth_stat.json stat -json` ([stat.cc](https://raw.githubusercontent.com/YosysHQ/yosys/main/passes/cmds/stat.cc), [tee.cc](https://raw.githubusercontent.com/YosysHQ/yosys/main/passes/cmds/tee.cc)); exact JSON keys unverified | ALREADY-FILE (JSON upgrade FILE-AVAILABLE) |
| synth_yosys | area (`_AREA_TOP_RE :54`, `_AREA_MODULE_RE :55`) | no — same stat file | same `stat -json` (statdata_t carries area; keys unverified) | ALREADY-FILE (JSON upgrade FILE-AVAILABLE) |
| synth_yosys | netlist artifact (`write_verilog :488`, gate `:431`) | no — file | optional `write_json` only if a consumer needs it ([json.cc](https://raw.githubusercontent.com/YosysHQ/yosys/main/backends/json/json.cc)) | ALREADY-FILE |
| synth_yosys | `yosys_version` (`yosys -V :527-546`) | yes (probe, not result data) | none — no version file exists | STDIO-ONLY |
| digital_flow | D12 synth gate (`_ERROR_RE :59`, `:286-289`) | no — synthesis step files | n/a | ALREADY-FILE |
| digital_flow | D22 STA gate (`_STA_FAIL_RE :63`, `:293-298`) | no — STA report files | file→file upgrade: `final/metrics.json` (METRICS2.1) or `or_metrics_out.json` ([migrants doc](https://librelane.readthedocs.io/en/stable/getting_started/migrants/index.html)); confirm keys at 3.0.17 | ALREADY-FILE |
| digital_flow | D25 drc_total (`:60-62`, `:307-315`) | no — DRC report files | same metrics.json upgrade; `.lyrdb` is structured XML | ALREADY-FILE |
| digital_flow | D26 lvs_match (`:65-69`, `:316-324`) | no — LVS report files | netgen text is audit KEEP-PARSE-ONLY — no better grammar | ALREADY-FILE |
| digital_flow | D27 equiv gate (`_EQUIV_FAIL_RE :64`, `:325-330`) | no — equiv report files | same metrics.json upgrade | ALREADY-FILE |
| digital_flow | GDS/netlist/SPEF (`:299-306`, `:753-776`) | no — binary/file artifacts | n/a | ALREADY-FILE |
| digital_flow | exit_code/timed_out (`:701-707`) | process metadata, not a stream parse | no file carries exit status | STDIO-ONLY (trivial) |
| extract_magic | completion marker `exttospice finished` (`:23`, `:233-237`) | yes, on proc.stdout — but redundant: `.ext`/`.spice` pair gate (`:201-206`) + `.subckt` gate (`:246-249`) already prove completion | no verified console-to-file flag at pin (`logfile` verified only for irsim docs — does not transfer) | STDIO-ONLY string; evidence ALREADY-FILE |
| extract_magic | tech-load probe (`:146-154`, `:192-196`) | yes (preflight probe) | none — `-T` banner is console-only per magic(1) | STDIO-ONLY |
| extract_magic | devices[]/device_count (`:24-29`) | no — `.spice` file (`:215`, `:238-245`) | n/a (ext2spice SPICE grammar, audit case #1) | ALREADY-FILE |
| extract_magic | ext_file/spice_file artifacts (`:201-206`) | no — files | n/a | ALREADY-FILE |

### drivers-native group

| adapter | field | stdio marker today | file alternative + flag + evidence | verdict |
|---|---|---|---|---|
| connectivity | findings[] (`:156-196`) | no — native dicts from in-process `erc_findings()` | n/a | ALREADY-FILE (native) |
| connectivity | netlists/nets/counts (`:135-149`, `:189-195`) | no — native dicts | n/a | ALREADY-FILE (native) |
| view_sync | findings[] (`:162-177`) | no — native dicts from in-process `compare_views()` | n/a | ALREADY-FILE (native) |
| view_sync | coverage{}, report (`:181-184`) | no — native | n/a | ALREADY-FILE (native) |
| gdsfactory | `ok`, version, `error{}` (`:462-485`) | envelope only — our driver prints JSON from native `gf.__version__` | trivial: driver `json.dump`s the identical dict to `gf_views_result.json`; adapter prefers file, envelope fallback | FILE-AVAILABLE (trivial; we own both ends) |
| gdsfactory | mappings[] (`:486-551`) | same envelope | same result file; values already native API (`get_polygons`, `bbox`, `ports`) | FILE-AVAILABLE (same change) |
| gdsfactory | artifacts[] (`:552-561`) | envelope carries PATHS only | payloads already files (`write_gds`/`write_oas`, `<cell>.pins.json`) | ALREADY-FILE |
| gdsfactory | diagnostics/recipe/PDK (`:567-573`) | same envelope | same result file | FILE-AVAILABLE (same change) |

## (c) Honest STDIO-ONLY residue list

Fields with no file alternative at the pinned versions:

| # | adapter · field | reason |
|---|---|---|
| 1 | drc · total | magic DRC verbs print violations to the terminal only; `drc printrules [file]` dumps the rule set, not violations. Audit KEEP-PARSE-ONLY case 1. Keep pinned scrape + golden fixtures. |
| 2 | drc · areas (rule+bbox) | same — no violation file writer at pin 8.3. |
| 3 | drc · tech probe | probe, not results; console-only. |
| 4 | ngspice · sim_fail detail | ngspice 47 has no structured error file; errors exist only in the log stream (already persisted via `-o`). Quote from the log file. |
| 5 | postlayout · sim_fail detail | same as ngspice. |
| 6 | cosim · analog no-value detail | same as ngspice (persisted in `-o cosim_ngspice.log`). |
| 7 | hdl_sim · compile diags | iverilog has no diagnostics-file flag (full upstream inventory checked); stderr-only, stable `file:line: msg` grammar. Keep regex. |
| 8 | synth_yosys · `yosys_version` | `yosys -V` probe; no version file exists. Trivial, keep. |
| 9 | digital_flow · exit_code/timed_out | process metadata, not a stream parse; no file carries exit status. Trivial, keep. |
| 10 | extract_magic · `exttospice finished` marker | no verified console-to-file flag for magic at pin; BUT redundant — verdict already file-gated (`.ext`/`.spice` pair + `.subckt`). Optional: demote to warn-not-raise. |
| 11 | extract_magic · tech-load probe | preflight probe; `-T` banner console-only. Trivial, keep. |

Net: the only material STDIO-ONLY residue is magic drc
(3 fields), the ngspice-family error-detail quotes (3 fields, sourced
from persisted log files), and iverilog compile diagnostics (1 field).
Everything else is a probe, process metadata, or redundant.

## (d) Recommended migration order (easiest wins first)

1. ngspice + postlayout tier 1 — parse the `-o` log file only, drop the
   stdout/stderr chunks. Zero-risk, no flag change, no grammar change.
2. formal_sby summaries — `logtext = formal/logfile.txt if exists else
   stdout`, run existing regexes unchanged. One-line source swap; keep
   stdout fallback for the timeout path.
3. hdl_sim + cosim digital — add `-l<log>.log` to the vvp argv in
   `hdl_sim.execute :217-219` (one change covers cosim via `:842`);
   parse `_SIM_RE/_TIME_RE` and `COSIM_*` from the logfile. Live-verified
   byte-identical on vvp 14.0.
4. synth_yosys log dedup (optional) — parse `synth.log` only; with `-q`
   the join can double-report lines present in both streams.
5. syntax `--diag-json` — add `--diag-json <workdir>/diag.json` to argv,
   parse JSON, derive counts; keep `_DIAG_RE` fallback until the schema
   is fixture-pinned at v12.
6. timing_sta `>` redirection — append `> <section>.rpt` to the 7 report
   commands; keep marker-split parse as fallback. Wave 4: tool is
   DEFERRED and the redirect doc needs a probe run at pin 857316f.
7. ngspice + postlayout tier 2 — append `wrdata meas.dat meas_*` (+ `set
   wr_singlescale`) in `build_deck`, parse the ASCII table; fixture-check
   (scale+value pairs). Needs a live ngspice run (not installed here).
8. synth_yosys `stat -json` — `tee -q -o synth_stat.json stat -json`;
   inspect stat.cc JSON writer for exact keys first; keep `_parse_stat`
   fallback. File→better-file, aligns with TOOL-OUTPUTS wave 3.
9. digital_flow `metrics.json` (optional) — read D22/D25/D27 verdicts
   from `final/metrics.json`; confirm keys at LibreLane 3.0.17 first.
   File→better-file; zero stdio urgency.
10. gdsfactory / sax / circulax / meow `result.json` (optional hygiene)
    — drivers write the envelope dict to a result file; adapters read
    file first, envelope fallback. ~10 lines each; no tool interaction.
11. netgen `-json` sidecar (lowest urgency) — primary path is already a
    file; sidecar grammar vs our `Net:`/`Instance:` fields unverified.
12. drc_kl synthetic JSON (skip unless free) — self-emitted prints; zero
    drift risk either way.
13. extract_magic marker demotion (optional) — demote the redundant
    `exttospice finished` check to warn-not-raise so transcript drift
    can't fail a good extraction.

## (e) Gaps where evidence was weak

- netgen `-json` sidecar grammar vs consumed `Net:`/`Instance:`/device
  fields: flag exists at 1.5, sidecar contents unverified. (checks)
- OpenSTA `>` redirection doc from an OpenSTA.pdf mirror, not
  byte-verified at pin 857316f; needs a probe run. Tool is DEFERRED, so
  wave 4. (checks)
- slang `--diag-json` schema at v12: flag documented, JSON shape needs
  fixture-pinning. (checks)
- ngspice `wrdata`-for-meas: upstream docs only (tutorial `let`-scalar
  example + manual ch.16); no live run — ngspice not installed here.
  `wrdata` emits scale+value pairs; tier-2 parser needs `wr_singlescale`
  + fixtures. `.meas` is NOT a file escape (same stream). (sims)
- oss-cad-suite 20261025 contents not enumerable (future-dated bundle);
  Yosys flags checked against stable ≈0.69 + main source (all cited
  flags long-standing; `stat -json` since ≤2017). Exact `stat -json`
  keys unverified — inspect stat.cc before implementing. (sims, impl)
- LibreLane `metrics.json` keys at 3.0.17 unconfirmed. (impl)
- drc_kl docstring stale: says verified vs 0.28.16, pin is 0.30.12.
  (checks)
- cosim `_MEAS_RE :75` dead (never referenced) — cleanup, not evidence.
