# yosys_slang — output dissection

Dissector ref: prior result 17 (text `handoff-92755922e42e6959c48c317d7a33206d05daafbe33d33698db504a7afcd2355d-20f7bbef1f541ad573f4a7378c946fe15c47295f4d23587e83c432f740b8cdfe.txt`, summary `handoff-70c16971b2a0fd8f2ef443247919c6fde7ccd0dc9f77792651c4cc6a5f9a8f53-20f7bbef1f541ad573f4a7378c946fe15c47295f4d23587e83c432f740b8cdfe.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `4a77e391c2a66bf1caec5e076b7e29609123985b`
- Clone date: `2026-10-29`
- Pin: PIN: oss-cad-suite 20261025 / "Yosys 0.70" (rocket-engine/scripts/provision_toolchain.sh:55,57). NOTE: README.md:15,45 says sv-elab is integrated into Yosys >=0.67 and the .so plugin build supports only 0.59-0.66, so at the pinned Yosys 0.70 the code path is Yosys-internal `read_slang`; this clone r
- Doc/source URLs:
  - https://github.com/povik/sv-elab
  - https://www.sv-lang.com/command-line-ref.html

### Dissector header (verbatim, whitespace-trimmed)

```text
yosys_slang (= sv-elab, formerly yosys-slang) output-capability dissection

CLONE: /tmp/rocket-tool-src/yosys_slang/ @ 4a77e391c2a66bf1caec5e076b7e29609123985b, date 2026-10-29 (`git rev-parse HEAD`, `git log -1 --format=%cs`).
PIN: oss-cad-suite 20261025 / "Yosys 0.70" (rocket-engine/scripts/provision_toolchain.sh:55,57). NOTE: README.md:15,45 says sv-elab is integrated into Yosys >=0.67 and the .so plugin build supports only 0.59-0.66, so at the pinned Yosys 0.70 the code path is Yosys-internal `read_slang`; this clone remains authoritative for the frontend logic. Docs: no /tmp/rocket-tool-docs page (fallback per instructions); grounded in in-repo README.md + upstream https://github.com/povik/sv-elab, wiki Feature-support, https://www.sv-lang.com/command-line-ref.html (cited README.md:76).
```

## 1. Result channels

1. RESULT CHANNELS (the plugin itself writes NO files, NO db, has NO API returns to a caller; its product is in-memory RTLIL + log/stdio text)

| # | Channel | Producing flag/command | Destination | Content |
|---|---|---|---|---|
| C1 | In-memory RTLIL design (PRIMARY) | `read_slang [opts] files...` (Frontend "slang", driver.cc:352) | `RTLIL::Design`: `design->addModule(...)` per top instance (driver.cc:626), `populate_netlist` (driver.cc:638); post-passes `proc_clean/rmdead/prune/init/rom/mux`, `opt_expr -keepdc` (driver.cc:678-685) | Elaborated word-level netlist; downstream `write_json`/`write_rtlil`/`stat` serialize it |
| C2 | Yosys log diagnostics | any `read_slang` run; `driver.reportCompilation/reportDiagnostics` (driver.cc:594,657) | yosys log = stdout (or `-l file`); severity-routed | Errors/warnings/notes + source snippets (grammar below) |
| C3 | Raw-stdout AST JSON (dev/debug) | `read_slang --dump-ast ...` (option slang_frontend.cc:127; emit driver.cc:584-590; test-expr path driver.cc:846-851) | real stdout via `std::cout` (NOT yosys log) | Pretty-printed slang ASTSerializer JSON of compilation root |
| C4 | Raw-stdout crash dump | internal assert path `error_on_node__` (abort_helpers.cc:48-77) | stdout (`std::cout`) + yosys fatal | Node AST JSON (abort_helpers.cc:51-55) + `Source line f:l:c: text` (abort_helpers.cc:67-71), then `log_error("Feature unimplemented at...")` |
| C5 | Log version lines | `slang_version` pass (driver.cc:234-258) | yosys log | `sv-elab revision %s` / `slang revision %s` (driver.cc:255-256, from version.h.in macros) |
| C6 | Test-only log line | `test_slangdiag -expect "msg"` + `read_slang` (driver.cc:749-775, check driver.cc:458-476) | yosys log | ``Expected diagnostic `%s' found`` (driver.cc:467) |
| C7 | Fatal markers | parse/elaboration failure | yosys log + nonzero exit | `Parsing failed; see full log for details` (driver.cc:577), `Design elaboration failed; see full log for details` (driver.cc:604,659) via log_cmd_error/log_error |

## 2. Format grammars

2. FORMAT GRAMMARS
(a) C1 RTLIL: grammar owned by Yosys, not this repo (serialize with `write_json`/Manual C.236). This repo contributes: `(* src *)` attributes on every RTLIL object via `format_src` (driver.cc:66-82): `file:line.col` single-point or `file:line.col-line.col` range, e.g. `top.sv:12.3-12.9`; flows into write_json `attributes.src`. SV attributes transferred verbatim (`convert_attr_value`, driver.cc:162-177; string attrs keep CONST_FLAG_STRING).
(b) C2 diagnostics, new-logging path (Yosys >0.69 incl. pinned 0.70): `YosysDiagnosticClient::formatDiag` (driver.cc:318-347): line = `<message>[ -W<option>]` (driver.cc:325-326), routed `log_file_warning` / `log_file_nonfatal_error` / `log_file_info` by severity (driver.cc:327-334) with file:line location; then source snippet line `log("%s")` + highlight line `log_highlight("%s")` (driver.cc:343-344), lines >4096 chars suppressed. Legacy path (older Yosys): slang's own TextDiagnosticClient piped through `slang::OS::captureOutput(...log...)` (driver.cc:485-486,812-813) -- exact legacy text grammar lives in third_party/slang, EMPTY submodule in this clone: UNRESOLVED, do not rely on it (pinned 0.70 uses the new path).
(c) Internal diag inventory (message templates + severities, all in src/diag.cc:148-377; codes DiagSubsystem::Netlist 1000-1089, diag.cc:55-141). Real examples: `unsynthesizable timing control (ignore with '--ignore-timing')` (Error); `unroll limit of {} exhausted [--unroll-limit=]` (Error); `@(edge) will not be synthesized (override with '--allow-dual-edge-ff')` (Error); `high-impedance state (Z) will be treated as undefined state (X) in this context` (Warning); `mixing of implicit and edge sensitivity` (Error, sanity group); `latch not inferred for variable '{}' driven from always_latch procedure` (Warning). `{}` = fmt placeholders filled positionally.
(d) C3/C4 AST JSON: `slang::JsonWriter` pretty-print + `ast::ASTSerializer` (driver.cc:585-589). Schema owned by slang (ASTSerializer.h in the empty submodule): UNRESOLVED from this clone; treat as version-sensitive debug output, not an adapter contract. No repo test golden-captures it (tests/*.ys assert via `select -assert-count`, `sat -verify`, `dump =*` display checks, e.g. tests/various/meminit.ys, stringattrs.ys).
(e) Exit states: `log_error`/`log_cmd_error` = yosys fatal (nonzero exit, C7 markers); warnings/notes never fail the run; `--dump-ast` does not change exit semantics.

## 3. Python bindings verdict

3. PYTHON BINDINGS: NONE. Audit row "none (C++ plugin, `read_slang`)" CONFIRMED: zero hits for pybind/python/cython/swig in src/, CMakeLists.txt, BUILD.bazel (only prose hit: "Import as an instantiable blackbox", slang_frontend.cc:174). Do not confuse with the separate `slang` tool row (pyslang / --ast-json): sv-elab's elaboration is exposed only as Yosys passes (`read_slang`, `slang_defaults`, `slang_version`, `test_slangdiag`, `test_slangexpr`).

## 4. Stdio-only residue

4. STDIO-ONLY RESIDUE: (i) all diagnostics incl. severity/snippet (C2) -- plugin emits only via yosys log APIs, defines no report file and no `--diag-json`-style flag (full option list SynthesisSettings::addOptions, slang_frontend.cc:126-177, has file outputs: none); (ii) `--dump-ast` JSON (C3) -- hardcoded `std::cout`, no filename option; (iii) crash AST dumps (C4) -- stdout by design (abort path). Standalone slang's structured escapes (--ast-json, JSON diagnostics) belong to the `slang` row and are NOT wired through read_slang (`OptionRequiresStandaloneSlang`, diag.cc:374-375, exists precisely to reject them).

## 5. Adapter recommendation

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text):
 1st -- Structured file (KEEP-STRUCTURED, audit row confirmed): `read_slang ...` then Yosys `write_json <file>`; parse the JSON netlist (schema: Yosys manual; `src` attributes per 2a give file:line provenance). Deterministic, version-pinned via bundle 20261025.
 2nd -- Deterministic text: assert C7 fatal markers + nonzero exit for FAIL; regex `ERROR:`/diag templates from diag.cc:148-377 for classification; golden good+bad fixtures per TOOL-OUTPUTS (repo .ys tests show the pattern: `select -assert-count`, `sat -verify`).
 Do NOT use: C3/C4 stdout JSON (slang-schema-owned, debug-grade), pyosys in-process (exit()-unsafe per audit), pyslang as a substitute (parses, does not elaborate to RTLIL).
 Verified at: clone 4a77e391 (2026-10-29) + provision pins oss-cad-suite 20261025 / Yosys 0.70; caveat: at 0.70 the shipped frontend is Yosys-internal, so re-verify `YOSYS_NEW_LOGGING` behavior text against the bundle's own `read_slang` once installed.

## Weak-evidence gaps (flagged by dissector)

- | C3 | Raw-stdout AST JSON (dev/debug) | `read_slang --dump-ast ...` (option slang_frontend.cc:127; emit driver.cc:584-590; test-expr path driver.cc:846-851) | real stdout via `std::cout` (NOT yosys log) | Pretty-printed slang ASTSerializer JSON of compilation
- (b) C2 diagnostics, new-logging path (Yosys >0.69 incl. pinned 0.70): `YosysDiagnosticClient::formatDiag` (driver.cc:318-347): line = `<message>[ -W<option>]` (driver.cc:325-326), routed `log_file_warning` / `log_file_nonfatal_error` / `log_file_info` by sever
- (d) C3/C4 AST JSON: `slang::JsonWriter` pretty-print + `ast::ASTSerializer` (driver.cc:585-589). Schema owned by slang (ASTSerializer.h in the empty submodule): UNRESOLVED from this clone; treat as version-sensitive debug output, not an adapter contract. No re
- Do NOT use: C3/C4 stdout JSON (slang-schema-owned, debug-grade), pyosys in-process (exit()-unsafe per audit), pyslang as a substitute (parses, does not elaborate to RTLIL).

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
yosys_slang (= sv-elab, formerly yosys-slang) output-capability dissection

CLONE: /tmp/rocket-tool-src/yosys_slang/ @ 4a77e391c2a66bf1caec5e076b7e29609123985b, date 2026-10-29 (`git rev-parse HEAD`, `git log -1 --format=%cs`).
PIN: oss-cad-suite 20261025 / "Yosys 0.70" (rocket-engine/scripts/provision_toolchain.sh:55,57). NOTE: README.md:15,45 says sv-elab is integrated into Yosys >=0.67 and the .so plugin build supports only 0.59-0.66, so at the pinned Yosys 0.70 the code path is Yosys-internal `read_slang`; this clone remains authoritative for the frontend logic. Docs: no /tmp/rocket-tool-docs page (fallback per instructions); grounded in in-repo README.md + upstream https://github.com/povik/sv-elab, wiki Feature-support, https://www.sv-lang.com/command-line-ref.html (cited README.md:76).

1. RESULT CHANNELS (the plugin itself writes NO files, NO db, has NO API returns to a caller; its product is in-memory RTLIL + log/stdio text)

| # | Channel | Producing flag/command | Destination | Content |
|---|---|---|---|---|
| C1 | In-memory RTLIL design (PRIMARY) | `read_slang [opts] files...` (Frontend "slang", driver.cc:352) | `RTLIL::Design`: `design->addModule(...)` per top instance (driver.cc:626), `populate_netlist` (driver.cc:638); post-passes `proc_clean/rmdead/prune/init/rom/mux`, `opt_expr -keepdc` (driver.cc:678-685) | Elaborated word-level netlist; downstream `write_json`/`write_rtlil`/`stat` serialize it |
| C2 | Yosys log diagnostics | any `read_slang` run; `driver.reportCompilation/reportDiagnostics` (driver.cc:594,657) | yosys log = stdout (or `-l file`); severity-routed | Errors/warnings/notes + source snippets (grammar below) |
| C3 | Raw-stdout AST JSON (dev/debug) | `read_slang --dump-ast ...` (option slang_frontend.cc:127; emit driver.cc:584-590; test-expr path driver.cc:846-851) | real stdout via `std::cout` (NOT yosys log) | Pretty-printed slang ASTSerializer JSON of compilation root |
| C4 | Raw-stdout crash dump | internal assert path `error_on_node__` (abort_helpers.cc:48-77) | stdout (`std::cout`) + yosys fatal | Node AST JSON (abort_helpers.cc:51-55) + `Source line f:l:c: text` (abort_helpers.cc:67-71), then `log_error("Feature unimplemented at...")` |
| C5 | Log version lines | `slang_version` pass (driver.cc:234-258) | yosys log | `sv-elab revision %s` / `slang revision %s` (driver.cc:255-256, from version.h.in macros) |
| C6 | Test-only log line | `test_slangdiag -expect "msg"` + `read_slang` (driver.cc:749-775, check driver.cc:458-476) | yosys log | ``Expected diagnostic `%s' found`` (driver.cc:467) |
| C7 | Fatal markers | parse/elaboration failure | yosys log + nonzero exit | `Parsing failed; see full log for details` (driver.cc:577), `Design elaboration failed; see full log for details` (driver.cc:604,659) via log_cmd_error/log_error |

2. FORMAT GRAMMARS
(a) C1 RTLIL: grammar owned by Yosys, not this repo (serialize with `write_json`/Manual C.236). This repo contributes: `(* src *)` attributes on every RTLIL object via `format_src` (driver.cc:66-82): `file:line.col` single-point or `file:line.col-line.col` range, e.g. `top.sv:12.3-12.9`; flows into write_json `attributes.src`. SV attributes transferred verbatim (`convert_attr_value`, driver.cc:162-177; string attrs keep CONST_FLAG_STRING).
(b) C2 diagnostics, new-logging path (Yosys >0.69 incl. pinned 0.70): `YosysDiagnosticClient::formatDiag` (driver.cc:318-347): line = `<message>[ -W<option>]` (driver.cc:325-326), routed `log_file_warning` / `log_file_nonfatal_error` / `log_file_info` by severity (driver.cc:327-334) with file:line location; then source snippet line `log("%s")` + highlight line `log_highlight("%s")` (driver.cc:343-344), lines >4096 chars suppressed. Legacy path (older Yosys): slang's own TextDiagnosticClient piped through `slang::OS::captureOutput(...log...)` (driver.cc:485-486,812-813) -- exact legacy text grammar lives in third_party/slang, EMPTY submodule in this clone: UNRESOLVED, do not rely on it (pinned 0.70 uses the new path).
(c) Internal diag inventory (message templates + severities, all in src/diag.cc:148-377; codes DiagSubsystem::Netlist 1000-1089, diag.cc:55-141). Real examples: `unsynthesizable timing control (ignore with '--ignore-timing')` (Error); `unroll limit of {} exhausted [--unroll-limit=]` (Error); `@(edge) will not be synthesized (override with '--allow-dual-edge-ff')` (Error); `high-impedance state (Z) will be treated as undefined state (X) in this context` (Warning); `mixing of implicit and edge sensitivity` (Error, sanity group); `latch not inferred for variable '{}' driven from always_latch procedure` (Warning). `{}` = fmt placeholders filled positionally.
(d) C3/C4 AST JSON: `slang::JsonWriter` pretty-print + `ast::ASTSerializer` (driver.cc:585-589). Schema owned by slang (ASTSerializer.h in the empty submodule): UNRESOLVED from this clone; treat as version-sensitive debug output, not an adapter contract. No repo test golden-captures it (tests/*.ys assert via `select -assert-count`, `sat -verify`, `dump =*` display checks, e.g. tests/various/meminit.ys, stringattrs.ys).
(e) Exit states: `log_error`/`log_cmd_error` = yosys fatal (nonzero exit, C7 markers); warnings/notes never fail the run; `--dump-ast` does not change exit semantics.

3. PYTHON BINDINGS: NONE. Audit row "none (C++ plugin, `read_slang`)" CONFIRMED: zero hits for pybind/python/cython/swig in src/, CMakeLists.txt, BUILD.bazel (only prose hit: "Import as an instantiable blackbox", slang_frontend.cc:174). Do not confuse with the separate `slang` tool row (pyslang / --ast-json): sv-elab's elaboration is exposed only as Yosys passes (`read_slang`, `slang_defaults`, `slang_version`, `test_slangdiag`, `test_slangexpr`).

4. STDIO-ONLY RESIDUE: (i) all diagnostics incl. severity/snippet (C2) -- plugin emits only via yosys log APIs, defines no report file and no `--diag-json`-style flag (full option list SynthesisSettings::addOptions, slang_frontend.cc:126-177, has file outputs: none); (ii) `--dump-ast` JSON (C3) -- hardcoded `std::cout`, no filename option; (iii) crash AST dumps (C4) -- stdout by design (abort path). Standalone slang's structured escapes (--ast-json, JSON diagnostics) belong to the `slang` row and are NOT wired through read_slang (`OptionRequiresStandaloneSlang`, diag.cc:374-375, exists precisely to reject them).

5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS bindings > structured files > deterministic text):
 1st -- Structured file (KEEP-STRUCTURED, audit row confirmed): `read_slang ...` then Yosys `write_json <file>`; parse the JSON netlist (schema: Yosys manual; `src` attributes per 2a give file:line provenance). Deterministic, version-pinned via bundle 20261025.
 2nd -- Deterministic text: assert C7 fatal markers + nonzero exit for FAIL; regex `ERROR:`/diag templates from diag.cc:148-377 for classification; golden good+bad fixtures per TOOL-OUTPUTS (repo .ys tests show the pattern: `select -assert-count`, `sat -verify`).
 Do NOT use: C3/C4 stdout JSON (slang-schema-owned, debug-grade), pyosys in-process (exit()-unsafe per audit), pyslang as a substitute (parses, does not elaborate to RTLIL).
 Verified at: clone 4a77e391 (2026-10-29) + provision pins oss-cad-suite 20261025 / Yosys 0.70; caveat: at 0.70 the shipped frontend is Yosys-internal, so re-verify `YOSYS_NEW_LOGGING` behavior text against the bundle's own `read_slang` once installed.
```
