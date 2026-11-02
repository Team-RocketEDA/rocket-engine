# mcy — output dissection

Dissector ref: prior result 1 (text `handoff-51a70f5d279b780f96aec90fa675c6151f5aceffa7db4ab2ef85c2484b4b1ad5-8ccca1ed6d6c7c43823e385384ec1aec37e809133d899a822c9845ed15cc5cd3.txt`, summary `handoff-f35c65f8b93be95c2626385fa3cb293629b380c2fbbdb6fc1c453815d3637051-8ccca1ed6d6c7c43823e385384ec1aec37e809133d899a822c9845ed15cc5cd3.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `5a2cad0cbefceb7f23051c08348bd23128fd1046`
- Clone date: `2026-08-04`
- Pin: Pin/version: NO mcy-specific pin. Via oss-cad-suite bundle pin 20261025 (provision_toolchain.sh:55-56 OSS_CAD_SUITE_PIN/TAG; provision asserts only yosys/sby banners). Audit row (tool-bindings-audit.md:34): `mcy | bundle | — | none (PyPI 404) | SQLite database/db.sqlite3 + design.il | KEEP-STRUCTURE
- Doc/source URLs:
  - https://mcy.readthedocs.io/
  - https://yosyshq.readthedocs.io/projects/ap400/en/latest/

### Dissector header (verbatim, whitespace-trimmed)

```text
MCY (Mutation Cover with Yosys) — output dissection
Clone: /tmp/rocket-tool-src/mcy @ SHA 5a2cad0cbefceb7f23051c08348bd23128fd1046, date 2026-08-04 (`git rev-parse HEAD`, `git log -1 --format=%cs`). No /tmp docs fetch for mcy (absent from /tmp/rocket-tool-docs listing) — used in-repo README/docs + upstream web.
Pin/version: NO mcy-specific pin. Via oss-cad-suite bundle pin 20261025 (provision_toolchain.sh:55-56 OSS_CAD_SUITE_PIN/TAG; provision asserts only yosys/sby banners). Audit row (tool-bindings-audit.md:34): `mcy | bundle | — | none (PyPI 404) | SQLite database/db.sqlite3 + design.il | KEEP-STRUCTURED`. mcy has no --version/banner (click CLI, mcy.py:429-435). Evidence verified at clone SHA above.

Docs: README.md:64 https://mcy.readthedocs.io/ (= docs/source/*.rst); AppNote https://yosyshq.readthedocs.io/projects/ap400/en/latest/ (README.md:66).
```

## 1. Result channels

1. RESULT CHANNELS (one table)
| # | Channel | Producing flag/command | Filename/pattern | Stream/return | Notes |
|---|---|---|---|---|---|
| C1 | SQLite results DB | `mcy init [-f] [--nosetup]` creates; `run`/`task`/`reset` update | `database/db.sqlite3` (fixed name, cwd-relative) | file | PRIMARY result store. Schema mcy.py:494-531 (7 tables). Dash download route `/db.sqlite3` serves it (mcy-dash.py:181-186). |
| C2 | Elaborated design (RTLIL) | `mcy init` via generated `database/design.ys` (`write_rtlil`, mcy.py:472-480) | `database/design.il` | file | Yosys RTLIL text; input to all `mutate` steps. Audit's second structured escape. |
| C3 | Mutation list | `mcy init` via `database/mutations.ys` (`mutate -list N -seed … -o …`, mcy.py:482-489); `reset` appends via `mutations2.*` (mcy.py:284-310) | `database/mutations.txt` (+`mutations2.txt` transient append source) | file | One `mutate …` command/line; mirrored into DB `mutations`+`options` (mcy.py:533-544). Seed recorded here per config.rst:17. |
| C4 | Source-tag list | same `mutate -list … -s` step | `database/sources.txt` | file | One `<file>:<line>[.<col>]` srctag/line → DB `sources` (mcy.py:546-549). |
| C5 | Yosys logs/scripts | `init`/`reset` | `database/design.ys/.log`, `mutations.ys/.log`, `mutations2.ys/.log`, `setup.sh`, `setup/` | files | Provenance/debug; setup.sh only if [setup] (mcy.py:462-470). |
| C6 | Task I/O (per task) | `mcy run [-jN]` / `mcy task [-v] [-k] <test> <ids>` (mcy.py:658-762) | `tasks/<uuid>/input.txt`, `output.txt`, `logfile.txt` (+ test's own files: `mutated.v/.sv/.il`, `mutate.ys`, sim/SBY artifacts) | files | `input.txt` in, `output.txt` = per-mutation verdicts parsed at mcy.py:715-734. Dir removed unless `-k` (mcy.py:738-745); stdout→logfile.txt unless `-v` (mcy.py:751-757). |
| C7 | Mutated netlists | test scripts via `$SCRIPTS/create_mutated.sh` (scripts/create_mutated.sh:60-94) | `tasks/<uuid>/mutated.v` (default), or `-o` .v/.sv/.il; `mutate.ys`+`.log` | files | Ephemeral (inside tasks/); regenerated per task. See §2. |
| C8 | stdout: status statistics | `init`/`reset`/`status`/`run` end via `reset_status()` (mcy.py:319-333) + `[report]` exec (mcy.py:335-358) | stdout | stdout | Deterministic `Database contains…/Tagged…/Queued…` lines + USER-DEFINED report prints (arbitrary Python). |
| C9 | stdout/file: mutation list | `mcy list [--details] [id_or_tag..] [-o FILE]` (mcy.py:602-656) | stdout default, `-o -` = stdout | stdout/file | One `<id>: tags… [(queued)]` line/mutation; `--details` adds mutation cmd + cached results. |
| C10 | stdout/file: annotated source | `mcy source [-e enc] <file> [<fsfile>] [-o FILE]` (mcy.py:858-933) | stdout/file | stdout/file | Source reprint with coverage margin; hardcoded COVERED/UNCOVERED tags. |
| C11 | stdout/file: LCOV | `mcy lcov <file> [-o FILE]` (mcy.py:935-1001) | stdout/file | stdout/file | Standard lcov `TN:/SF:/DA:/LF:/LH:/end_of_record`. |
| C12 | stderr: progress/errors | all commands via log_info/log_step/log_warning/log_error (mcy.py:14-50, all `err=True`) | stderr | stderr | `==>`/`->` prefixed; task stderr stays on console (README.md:235). Errors exit 1 via exit_mcy (mcy.py:69-83). |
| C13 | Dashboard (HTTP+HTML) | `mcy dash` → exec `mcy-dash` Flask app (mcy.py:1003-1010; mcy-dash.py:188-189) | http://127.0.0.1:5000/ `index.html`, `mutations.html`, `source.html`, `/db.sqlite3` | HTTP | Renders C1 aggregates (mcy-dash.py:70-87,95-108,143-164); POST actions shell out to `mcy init`/`mcy run -j2` (mcy-dash.py:52-68). No JSON API. |
| C14 | GUI (Qt, interactive) | `mcy gui` → exec `mcy-gui` (mcy.py:1012-1019); or `mcy-gui <db>` directly (cmds.rst:55-57) | window only | n/a | Qt5/6+C++ reads C1 via QtSql (gui/src/database.h:27-47, gui/CMakeLists.txt). No export path — display only. |
| C15 | Exit code | all | — | process | 0 clean (exit_mcy(0)); 1 on any error incl. unexpected test value, bad output.txt line, nonzero task rc (mcy.py:399-402,726-728); signals→1 (mcy.py:85-89,1021-1026). Running-queue cleanup on exit (mcy.py:73-82). |
| — | In-process API returns | NONE | — | — | mcy.py is a click CLI (`if __name__==…: cli()`), installed as bin script (Makefile: `install mcy.py …/bin/mcy`). No package/setup.py/pyproject, no importable API. |

## 2. Format grammars

2. FORMAT GRAMMARS
G1. `database/db.sqlite3` (SQLite3; THE grammar). DDL mcy.py:494-531:
```
mutations(mutation_id INTEGER PK, mutation STRING)      -- full `mutate …` cmdline
options(mutation_id INTEGER, opt_type STRING, opt_value STRING)  -- dash-opts parsed mcy.py:537-544: `-X Y` → (X,Y); consecutive dashes/skips per loop
sources(srctag STRING)                                  -- `<file>:<line>[.<col>]`, one row/source line
results(mutation_id INTEGER, test STRING, result STRING) -- test = "name args…", result = single token (PASS/FAIL/…)
tags(mutation_id INTEGER, tag STRING)
queue(mutation_id INTEGER, test STRING, running BOOL)   -- 0 pending / 1 running
files(filename STRING, data BLOB)                       -- verbatim project sources ([files])
```
Reader SQL (allDermined, copy-paste for adapter): stats mcy.py:320-329; tags() mcy.py:337-351; coverage-per-line mcy.py:899-914 (opt_type='src', LIKE 'file:%', strip `.<col>`, COUNT CASE COVERED/UNCOVERED); dash aggregates mcy-dash.py:71-78 (incl. ROUND pct). Units: counts only; no floats except report-computed %. Numbers: ints.
G2. `database/design.il` — Yosys RTLIL text (`write_rtlil`, mcy.py:476). Grammar = Yosys RTLIL (owned by yosys, not mcy). Adapter: treat as opaque provenance blob / feed to yosys readers.
G3. `database/mutations.txt` — lines (mutate.rst:136, mcy.py:534-544): full yosys `mutate` argv string, e.g. (mutate.rst:45):
```
1 mutate -mode cnot0 -module bitcnt -cell $and$bitcnt.v:53$263 -port Y -portbit 23 -ctrlbit 57 -src bitcnt.v:53
```
(in DB the leading `1 ` index is absent; in input.txt present). Fields: `-mode <mode> -module/-cell/-port/-portbit/-ctrlbit/-wire/-wirebit/-src …` (mutate.rst:141). Delimiter: single spaces; no quoting.
G4. `database/sources.txt` — one srctag/line: `bitcnt.v:53` or `file:line.col` (mcy.py:893-897 strips at `.`).
G5. `tasks/<uuid>/input.txt` — grammar (README.md:207-230, mutate.rst:34-47): `<idx> <mutate command>` per line, idx = 1..batchsize task-local (NOT mutation_id). mcy.py:700-708 writes `%d %s`.
G6. `tasks/<uuid>/output.txt` — grammar (README.md:216-226, testsetup.rst:56-68, mcy.py:715-734): `<idx> <RESULT>` per line, exactly 2 whitespace-separated tokens, idx∈1..batchsize, order free; every idx required else fatal ("Empty mutation checklist", mcy.py:736-737). RESULT = single non-whitespace token, conventionally PASS/FAIL/TIMEOUT/ERROR; must be in test's `expect` list else run aborts (mcy.py:726-728). Real examples: test_sim.sh:15-19 `echo "1 PASS" > output.txt` / `1 FAIL` / `1 ERROR`; test_eq.sh:14 `gawk "{ print 1, $1; }" test_eq/status >> output.txt` (SBY status PASS/FAIL passthrough).
G7. `tasks/<uuid>/logfile.txt` — first lines `task <uuid> (<test>)` + `  <idx> <mutid> <mut…>` (mcy.py:695-707), then appended task stdout (`exec >>logfile.txt`, mcy.py:756). Free-form after header.
G8. Mutated netlists — `create_mutated.sh` (scripts/create_mutated.sh:66-94): reads input.txt, emits `mutate.ys` = `read_rtlil <design>`, per-line `mutate [-ctrl mutsel <w> <idx>] <mut…>` (`${mut#* }` strips idx), then `write_verilog -norename [.sv] | write_rtlil`; runs `yosys -ql mutate.log mutate.ys`. Outputs: `mutated.v` (default, same interface, case 1) / `-c` adds `mutsel` input width 8 default (cases 2-3); `-o` must end .v/.sv/.il. Env in task: TASK, TASKDIR, PRJDIR, KEEPDIR, MUTATIONS, SCRIPTS (mcy.py:749-750, README.md:199-230).
G9. `mcy list` stdout (mcy.py:633-654): `^<mid>:( <TAG>…| no-tags)( \([test]\)|\[[test]\])*…$`, queued=(..), running=[..]; `--details` adds blank line, `  <mutation>`, `  result from "<test>": <res>` per cached result, blank line. `-o FILE` redirects (default `-`).
G10. `mcy source` stdout (mcy.py:916-931): per source line `<margin>|\t<text>`; margin 5-wide: `%5d` covered count | `!%4d` uncovered count (negative shown as `!`) | `    ?` srctag w/o used mutation | blank. Line key = `file:line` minus `.<col>` (mcy.py:909-914).
G11. `mcy lcov` stdout (mcy.py:984-1000): `TN:` / `SF:<file>` / `DA:<line>,<0|covered>` (0 if any uncovered) / `LF:<total> LF` counts only srctag lines / `LH:<covered> LH` counts lines with covered>0 / `end_of_record`. File list from DB `files`, line count from stored blob (mcy.py:955-961).
G12. status/report stdout (mcy.py:319-333,335-358): fixed lines `Database contains <N> cached results.` / `… <N> cached "<res>" results for "<test>".` / `Tagged <N> mutations as "<tag>".` / `Queued <N> "<test>" tests[, <R> running].` then RAW [report] Python stdout (e.g. `Coverage: 87.50%`, config bitcnt:35-38). [report] can print anything — NOT a grammar.
G13. stderr (mcy.py:14-50): `==> …` (info/warn/error, colorized via click.secho) / `  -> …` steps; command echo `print(command)` on Task start goes to STDOUT (mcy.py:381-382). Not machine-stable (colors, human text).
No schema files in repo (schema is inline DDL); no XSD/JSON-schema. Tests dir: none in repo (no tests/; examples/bitcnt + picorv32_primes are the fixtures).

## 3. Python bindings verdict

3. PYTHON BINDINGS — Audit row CONFIRMED (none). Evidence: repo root has no setup.py/pyproject/package (ls: COPYING dash docs examples gui Makefile mcy-dash.py mcy.py README.md scripts); Makefile installs mcy.py/mcy-dash.py as bin scripts, not modules; mcy.py exposes only a click CLI; GUI is Qt C++ (gui/src/*.cc, gui/CMakeLists.txt Qt5/6+Boost); dash is a Flask server (no JSON API, HTML+DB download only). Web search found no `pypi.org/project/mcy` (only unrelated hits + macports `mcy` port version-locked to yosys 0.66) — consistent with audit's "PyPI 404". What results bindings return natively: n/a — read C1 via sqlite3 (stdlib) instead.

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE — Strictly stdio-only: NOTHING of record. Every stdio rendering (C8–C11) is a deterministic projection of C1+C4+config: list↔mutations/tags/queue (mcy.py:633-654), source/lcov↔sources+options+tags+files (mcy.py:891-931,963-1000), status↔results/tags/queue counts (mcy.py:319-333). Only true residue: (a) [report] section output — user-authored Python prints (config.mcy), arbitrary text by design (mcy.py:335-358); capture stdout if you want the project's own summary, but the adapter should recompute coverage from tags instead; (b) stderr progress/log + yosys/task logs — human diagnostics, unstable; (c) `print(command)` task echo on stdout (mcy.py:382) — interleaved noise. WHY: mcy's architecture is DB-first (all verdicts cached in results/tags tables); stdio commands are convenience views over the DB.

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text)
1st: query `database/db.sqlite3` with stdlib sqlite3 (queryable-DB tier — no text parsing). Copy the file first (WAL-free plain sqlite; dash serves live copy at /db.sqlite3). Reuse the exact SQL at mcy.py:320-329 (stats), mcy.py:337-351 (tags()), mcy.py:899-914 (per-line coverage). Golden fixtures: run examples/bitcnt (`mcy init && mcy run -j8`, needs iverilog+sby per README.md:60/quickstart.rst:9-11) and snapshot db.sqlite3 + `mcy list --details` + `mcy lcov` outputs.
2nd: parse `output.txt` (`^(\d+) (\S+)$`, join idx→mutation via sibling input.txt) for streaming per-task verdicts before DB commit.
3rd (avoid): scrape `mcy list/source/status` stdout — same data as (1) with weaker typing; [report] stdout is user-defined and unparseable in general.
Pin/version evidence verified at: clone 5a2cad0cbefceb7f23051c08348bd23128fd1046 (2026-08-04); bundle pin 20261025 from provision_toolchain.sh:55-56; audit row tool-bindings-audit.md:34; no mcy banner/version to assert (recommend asserting bundle VERSION + `mcy --help` presence).

## Weak-evidence gaps (flagged by dissector)

- | C5 | Yosys logs/scripts | `init`/`reset` | `database/design.ys/.log`, `mutations.ys/.log`, `mutations2.ys/.log`, `setup.sh`, `setup/` | files | Provenance/debug; setup.sh only if [setup] (mcy.py:462-470). |
- Pin/version: NO mcy-specific pin. Via oss-cad-suite bundle pin 20261025 (provision_toolchain.sh:55-56 OSS_CAD_SUITE_PIN/TAG; provision asserts only yosys/sby banners). Audit row (tool-bindings-audit.md:34): `mcy | bundle | — | none (PyPI 404) | SQLite database
- G6. `tasks/<uuid>/output.txt` — grammar (README.md:216-226, testsetup.rst:56-68, mcy.py:715-734): `<idx> <RESULT>` per line, exactly 2 whitespace-separated tokens, idx∈1..batchsize, order free; every idx required else fatal ("Empty mutation checklist", mcy.py:

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
MCY (Mutation Cover with Yosys) — output dissection
Clone: /tmp/rocket-tool-src/mcy @ SHA 5a2cad0cbefceb7f23051c08348bd23128fd1046, date 2026-08-04 (`git rev-parse HEAD`, `git log -1 --format=%cs`). No /tmp docs fetch for mcy (absent from /tmp/rocket-tool-docs listing) — used in-repo README/docs + upstream web.
Pin/version: NO mcy-specific pin. Via oss-cad-suite bundle pin 20261025 (provision_toolchain.sh:55-56 OSS_CAD_SUITE_PIN/TAG; provision asserts only yosys/sby banners). Audit row (tool-bindings-audit.md:34): `mcy | bundle | — | none (PyPI 404) | SQLite database/db.sqlite3 + design.il | KEEP-STRUCTURED`. mcy has no --version/banner (click CLI, mcy.py:429-435). Evidence verified at clone SHA above.

Docs: README.md:64 https://mcy.readthedocs.io/ (= docs/source/*.rst); AppNote https://yosyshq.readthedocs.io/projects/ap400/en/latest/ (README.md:66).

1. RESULT CHANNELS (one table)
| # | Channel | Producing flag/command | Filename/pattern | Stream/return | Notes |
|---|---|---|---|---|---|
| C1 | SQLite results DB | `mcy init [-f] [--nosetup]` creates; `run`/`task`/`reset` update | `database/db.sqlite3` (fixed name, cwd-relative) | file | PRIMARY result store. Schema mcy.py:494-531 (7 tables). Dash download route `/db.sqlite3` serves it (mcy-dash.py:181-186). |
| C2 | Elaborated design (RTLIL) | `mcy init` via generated `database/design.ys` (`write_rtlil`, mcy.py:472-480) | `database/design.il` | file | Yosys RTLIL text; input to all `mutate` steps. Audit's second structured escape. |
| C3 | Mutation list | `mcy init` via `database/mutations.ys` (`mutate -list N -seed … -o …`, mcy.py:482-489); `reset` appends via `mutations2.*` (mcy.py:284-310) | `database/mutations.txt` (+`mutations2.txt` transient append source) | file | One `mutate …` command/line; mirrored into DB `mutations`+`options` (mcy.py:533-544). Seed recorded here per config.rst:17. |
| C4 | Source-tag list | same `mutate -list … -s` step | `database/sources.txt` | file | One `<file>:<line>[.<col>]` srctag/line → DB `sources` (mcy.py:546-549). |
| C5 | Yosys logs/scripts | `init`/`reset` | `database/design.ys/.log`, `mutations.ys/.log`, `mutations2.ys/.log`, `setup.sh`, `setup/` | files | Provenance/debug; setup.sh only if [setup] (mcy.py:462-470). |
| C6 | Task I/O (per task) | `mcy run [-jN]` / `mcy task [-v] [-k] <test> <ids>` (mcy.py:658-762) | `tasks/<uuid>/input.txt`, `output.txt`, `logfile.txt` (+ test's own files: `mutated.v/.sv/.il`, `mutate.ys`, sim/SBY artifacts) | files | `input.txt` in, `output.txt` = per-mutation verdicts parsed at mcy.py:715-734. Dir removed unless `-k` (mcy.py:738-745); stdout→logfile.txt unless `-v` (mcy.py:751-757). |
| C7 | Mutated netlists | test scripts via `$SCRIPTS/create_mutated.sh` (scripts/create_mutated.sh:60-94) | `tasks/<uuid>/mutated.v` (default), or `-o` .v/.sv/.il; `mutate.ys`+`.log` | files | Ephemeral (inside tasks/); regenerated per task. See §2. |
| C8 | stdout: status statistics | `init`/`reset`/`status`/`run` end via `reset_status()` (mcy.py:319-333) + `[report]` exec (mcy.py:335-358) | stdout | stdout | Deterministic `Database contains…/Tagged…/Queued…` lines + USER-DEFINED report prints (arbitrary Python). |
| C9 | stdout/file: mutation list | `mcy list [--details] [id_or_tag..] [-o FILE]` (mcy.py:602-656) | stdout default, `-o -` = stdout | stdout/file | One `<id>: tags… [(queued)]` line/mutation; `--details` adds mutation cmd + cached results. |
| C10 | stdout/file: annotated source | `mcy source [-e enc] <file> [<fsfile>] [-o FILE]` (mcy.py:858-933) | stdout/file | stdout/file | Source reprint with coverage margin; hardcoded COVERED/UNCOVERED tags. |
| C11 | stdout/file: LCOV | `mcy lcov <file> [-o FILE]` (mcy.py:935-1001) | stdout/file | stdout/file | Standard lcov `TN:/SF:/DA:/LF:/LH:/end_of_record`. |
| C12 | stderr: progress/errors | all commands via log_info/log_step/log_warning/log_error (mcy.py:14-50, all `err=True`) | stderr | stderr | `==>`/`->` prefixed; task stderr stays on console (README.md:235). Errors exit 1 via exit_mcy (mcy.py:69-83). |
| C13 | Dashboard (HTTP+HTML) | `mcy dash` → exec `mcy-dash` Flask app (mcy.py:1003-1010; mcy-dash.py:188-189) | http://127.0.0.1:5000/ `index.html`, `mutations.html`, `source.html`, `/db.sqlite3` | HTTP | Renders C1 aggregates (mcy-dash.py:70-87,95-108,143-164); POST actions shell out to `mcy init`/`mcy run -j2` (mcy-dash.py:52-68). No JSON API. |
| C14 | GUI (Qt, interactive) | `mcy gui` → exec `mcy-gui` (mcy.py:1012-1019); or `mcy-gui <db>` directly (cmds.rst:55-57) | window only | n/a | Qt5/6+C++ reads C1 via QtSql (gui/src/database.h:27-47, gui/CMakeLists.txt). No export path — display only. |
| C15 | Exit code | all | — | process | 0 clean (exit_mcy(0)); 1 on any error incl. unexpected test value, bad output.txt line, nonzero task rc (mcy.py:399-402,726-728); signals→1 (mcy.py:85-89,1021-1026). Running-queue cleanup on exit (mcy.py:73-82). |
| — | In-process API returns | NONE | — | — | mcy.py is a click CLI (`if __name__==…: cli()`), installed as bin script (Makefile: `install mcy.py …/bin/mcy`). No package/setup.py/pyproject, no importable API. |

2. FORMAT GRAMMARS
G1. `database/db.sqlite3` (SQLite3; THE grammar). DDL mcy.py:494-531:
```
mutations(mutation_id INTEGER PK, mutation STRING)      -- full `mutate …` cmdline
options(mutation_id INTEGER, opt_type STRING, opt_value STRING)  -- dash-opts parsed mcy.py:537-544: `-X Y` → (X,Y); consecutive dashes/skips per loop
sources(srctag STRING)                                  -- `<file>:<line>[.<col>]`, one row/source line
results(mutation_id INTEGER, test STRING, result STRING) -- test = "name args…", result = single token (PASS/FAIL/…)
tags(mutation_id INTEGER, tag STRING)
queue(mutation_id INTEGER, test STRING, running BOOL)   -- 0 pending / 1 running
files(filename STRING, data BLOB)                       -- verbatim project sources ([files])
```
Reader SQL (allDermined, copy-paste for adapter): stats mcy.py:320-329; tags() mcy.py:337-351; coverage-per-line mcy.py:899-914 (opt_type='src', LIKE 'file:%', strip `.<col>`, COUNT CASE COVERED/UNCOVERED); dash aggregates mcy-dash.py:71-78 (incl. ROUND pct). Units: counts only; no floats except report-computed %. Numbers: ints.
G2. `database/design.il` — Yosys RTLIL text (`write_rtlil`, mcy.py:476). Grammar = Yosys RTLIL (owned by yosys, not mcy). Adapter: treat as opaque provenance blob / feed to yosys readers.
G3. `database/mutations.txt` — lines (mutate.rst:136, mcy.py:534-544): full yosys `mutate` argv string, e.g. (mutate.rst:45):
```
1 mutate -mode cnot0 -module bitcnt -cell $and$bitcnt.v:53$263 -port Y -portbit 23 -ctrlbit 57 -src bitcnt.v:53
```
(in DB the leading `1 ` index is absent; in input.txt present). Fields: `-mode <mode> -module/-cell/-port/-portbit/-ctrlbit/-wire/-wirebit/-src …` (mutate.rst:141). Delimiter: single spaces; no quoting.
G4. `database/sources.txt` — one srctag/line: `bitcnt.v:53` or `file:line.col` (mcy.py:893-897 strips at `.`).
G5. `tasks/<uuid>/input.txt` — grammar (README.md:207-230, mutate.rst:34-47): `<idx> <mutate command>` per line, idx = 1..batchsize task-local (NOT mutation_id). mcy.py:700-708 writes `%d %s`.
G6. `tasks/<uuid>/output.txt` — grammar (README.md:216-226, testsetup.rst:56-68, mcy.py:715-734): `<idx> <RESULT>` per line, exactly 2 whitespace-separated tokens, idx∈1..batchsize, order free; every idx required else fatal ("Empty mutation checklist", mcy.py:736-737). RESULT = single non-whitespace token, conventionally PASS/FAIL/TIMEOUT/ERROR; must be in test's `expect` list else run aborts (mcy.py:726-728). Real examples: test_sim.sh:15-19 `echo "1 PASS" > output.txt` / `1 FAIL` / `1 ERROR`; test_eq.sh:14 `gawk "{ print 1, $1; }" test_eq/status >> output.txt` (SBY status PASS/FAIL passthrough).
G7. `tasks/<uuid>/logfile.txt` — first lines `task <uuid> (<test>)` + `  <idx> <mutid> <mut…>` (mcy.py:695-707), then appended task stdout (`exec >>logfile.txt`, mcy.py:756). Free-form after header.
G8. Mutated netlists — `create_mutated.sh` (scripts/create_mutated.sh:66-94): reads input.txt, emits `mutate.ys` = `read_rtlil <design>`, per-line `mutate [-ctrl mutsel <w> <idx>] <mut…>` (`${mut#* }` strips idx), then `write_verilog -norename [.sv] | write_rtlil`; runs `yosys -ql mutate.log mutate.ys`. Outputs: `mutated.v` (default, same interface, case 1) / `-c` adds `mutsel` input width 8 default (cases 2-3); `-o` must end .v/.sv/.il. Env in task: TASK, TASKDIR, PRJDIR, KEEPDIR, MUTATIONS, SCRIPTS (mcy.py:749-750, README.md:199-230).
G9. `mcy list` stdout (mcy.py:633-654): `^<mid>:( <TAG>…| no-tags)( \([test]\)|\[[test]\])*…$`, queued=(..), running=[..]; `--details` adds blank line, `  <mutation>`, `  result from "<test>": <res>` per cached result, blank line. `-o FILE` redirects (default `-`).
G10. `mcy source` stdout (mcy.py:916-931): per source line `<margin>|\t<text>`; margin 5-wide: `%5d` covered count | `!%4d` uncovered count (negative shown as `!`) | `    ?` srctag w/o used mutation | blank. Line key = `file:line` minus `.<col>` (mcy.py:909-914).
G11. `mcy lcov` stdout (mcy.py:984-1000): `TN:` / `SF:<file>` / `DA:<line>,<0|covered>` (0 if any uncovered) / `LF:<total> LF` counts only srctag lines / `LH:<covered> LH` counts lines with covered>0 / `end_of_record`. File list from DB `files`, line count from stored blob (mcy.py:955-961).
G12. status/report stdout (mcy.py:319-333,335-358): fixed lines `Database contains <N> cached results.` / `… <N> cached "<res>" results for "<test>".` / `Tagged <N> mutations as "<tag>".` / `Queued <N> "<test>" tests[, <R> running].` then RAW [report] Python stdout (e.g. `Coverage: 87.50%`, config bitcnt:35-38). [report] can print anything — NOT a grammar.
G13. stderr (mcy.py:14-50): `==> …` (info/warn/error, colorized via click.secho) / `  -> …` steps; command echo `print(command)` on Task start goes to STDOUT (mcy.py:381-382). Not machine-stable (colors, human text).
No schema files in repo (schema is inline DDL); no XSD/JSON-schema. Tests dir: none in repo (no tests/; examples/bitcnt + picorv32_primes are the fixtures).

3. PYTHON BINDINGS — Audit row CONFIRMED (none). Evidence: repo root has no setup.py/pyproject/package (ls: COPYING dash docs examples gui Makefile mcy-dash.py mcy.py README.md scripts); Makefile installs mcy.py/mcy-dash.py as bin scripts, not modules; mcy.py exposes only a click CLI; GUI is Qt C++ (gui/src/*.cc, gui/CMakeLists.txt Qt5/6+Boost); dash is a Flask server (no JSON API, HTML+DB download only). Web search found no `pypi.org/project/mcy` (only unrelated hits + macports `mcy` port version-locked to yosys 0.66) — consistent with audit's "PyPI 404". What results bindings return natively: n/a — read C1 via sqlite3 (stdlib) instead.

4. STDIO-ONLY RESIDUE — Strictly stdio-only: NOTHING of record. Every stdio rendering (C8–C11) is a deterministic projection of C1+C4+config: list↔mutations/tags/queue (mcy.py:633-654), source/lcov↔sources+options+tags+files (mcy.py:891-931,963-1000), status↔results/tags/queue counts (mcy.py:319-333). Only true residue: (a) [report] section output — user-authored Python prints (config.mcy), arbitrary text by design (mcy.py:335-358); capture stdout if you want the project's own summary, but the adapter should recompute coverage from tags instead; (b) stderr progress/log + yosys/task logs — human diagnostics, unstable; (c) `print(command)` task echo on stdout (mcy.py:382) — interleaved noise. WHY: mcy's architecture is DB-first (all verdicts cached in results/tags tables); stdio commands are convenience views over the DB.

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS preference: bindings > structured files > deterministic text)
1st: query `database/db.sqlite3` with stdlib sqlite3 (queryable-DB tier — no text parsing). Copy the file first (WAL-free plain sqlite; dash serves live copy at /db.sqlite3). Reuse the exact SQL at mcy.py:320-329 (stats), mcy.py:337-351 (tags()), mcy.py:899-914 (per-line coverage). Golden fixtures: run examples/bitcnt (`mcy init && mcy run -j8`, needs iverilog+sby per README.md:60/quickstart.rst:9-11) and snapshot db.sqlite3 + `mcy list --details` + `mcy lcov` outputs.
2nd: parse `output.txt` (`^(\d+) (\S+)$`, join idx→mutation via sibling input.txt) for streaming per-task verdicts before DB commit.
3rd (avoid): scrape `mcy list/source/status` stdout — same data as (1) with weaker typing; [report] stdout is user-defined and unparseable in general.
Pin/version evidence verified at: clone 5a2cad0cbefceb7f23051c08348bd23128fd1046 (2026-08-04); bundle pin 20261025 from provision_toolchain.sh:55-56; audit row tool-bindings-audit.md:34; no mcy banner/version to assert (recommend asserting bundle VERSION + `mcy --help` presence).
```
