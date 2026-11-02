# openvaf — output dissection

Dissector ref: prior result 20 (text `handoff-1ad9c0c2ca953cec6996a947dbb0ce41f8a952b19c8a880bee29e3bd34757045-e3fdecccdf096d2d83c77e617fd3f9c9967165aff58a44349bf912450af26793.txt`, summary `handoff-e4de254af79b88bf1ab6ecd1055d6f40f9822f8ec95dbf17510b9528d6ba4cc0-e3fdecccdf096d2d83c77e617fd3f9c9967165aff58a44349bf912450af26793.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `a9697ae7780518f021f9f64e819b3a57033bd39f`
- Clone date: `2023-10-30`
- Pin: - Pin: NONE. No openvaf entry in `rocket-engine/scripts/provision_toolchain.sh` (all pins grepped); audit row `UNPINNED, not in lock` confirmed.
- Doc/source URLs:
  - https://github.com/OpenVAF/openvaf`
  - https://github.com/openvaf/openvaf-reloaded
  - https://openvaf.github.io/docs/getting-started/usage/
  - https://pypi.org/project/verilogae/

### Dissector header (verbatim, whitespace-trimmed)

```text
# openvaf output-capability dissection

## Provenance (restated)
- Clone: `/tmp/rocket-tool-src/openvaf/` @ SHA `a9697ae7780518f021f9f64e819b3a57033bd39f`, date `2023-10-30`, remote `https://github.com/OpenVAF/openvaf` (pre-fork OSDI-0.3 lineage).
- Versions in tree: `openvaf` crate `0.1.2` (`openvaf/openvaf/Cargo.toml:3`), `verilogae_py`/`verilogae_ffi` `1.0.0`, release `23.5.0 (2023-05-16)` + `[UNRELEASED]` (`CHANGELOG_OSDI.md`), OSDI `0.3` (`openvaf/osdi/src/lib.rs:32`, `openvaf/osdi/header/osdi_0_3.h:8-9`).
- Pin: NONE. No openvaf entry in `rocket-engine/scripts/provision_toolchain.sh` (all pins grepped); audit row `UNPINNED, not in lock` confirmed.
- Docs: `/tmp/rocket-tool-docs/openvaf-index.html` is a 404 page (fetched, unusable). Fell back to in-repo + upstream web: [Usage](https://openvaf.github.io/docs/getting-started/usage/), [PyPI verilogae](https://pypi.org/project/verilogae/), [openvaf-reloaded](https://github.com/openvaf/openvaf-reloaded).
```

## 1. Result channels

## 1. Result channels
| # | Channel | Producing flag/cmd | Filename/pattern | Stream/API |
|---|---|---|---|---|
| C1 | OSDI shared lib (primary) | `openvaf input.va [-o FILE]`; default `input.with_extension("osdi")` (`openvaf-driver/src/cli_process.rs:61-68`) | `<stem>.osdi` (ELF `.so` on Linux) | file |
| C2 | Batch cache lib | `--batch [--cache-dir DIR]` (default `ProjectDirs com/semimod/openvaf` cache) | `<base_n(md5)>.osdi` (`openvaf/src/cache.rs:51-55`) | file + stdout path print (`main.rs:84-87`) |
| C3 | Preprocessed source | `--print-expansion` | n/a | stdout (`openvaf/src/lib.rs:107-139`) |
| C4 | `--dump-json` | DEAD FLAG: driver bails `currently unimplemented` (`main.rs:74-81`); impl commented out (`lib.rs:49-105`) | intended `<stem>_<module>.json` (never written) | none |
| C5 | Listings | `--lints`, `--supported-targets` | n/a | stdout (`cli_process.rs:121-164`) |
| C6 | Diagnostics + status | any compile | n/a | stderr (codespan, see §2) |
| C7 | Fatal error chain | any hard failure | n/a | stderr `error: …` + `error: failed to compile <input>` (`main.rs:38-56`) |
| C8 | Crash report | panic (release only) | `$TMPDIR/openvaf-crash-<unixts>.log` + stderr notice (`crash_report.rs:69-88,160-172`) | file + stderr |
| C9 | verilogae cache libs | `verilogae_load(path, full_compile, opts)` (C ABI) / `verilogae.load/load_info` (Py) | `<base_n(md5)>.mod` (full) / `.modinfo` (info-only) in `com/semimod/verilogae` cache (`verilogae/src/cache.rs:50-61`) | file (dlopen'd in-process) |
| C10 | verilogae C ABI | `verilogae_load/export_vfs/fun_ptr/…` (`verilogae/src/api.rs`) | n/a | in-process FFI |
| C11 | verilogae Python | `import verilogae; load/load_info/export_vfs` (`verilogae_py/src/lib.rs:25-56`) | n/a | in-process objects + numpy |
| C12 | Exit status | any CLI run | n/a | `0` ok; `65` (`DATA_ERROR`) on `FatalDiagnostic` (`main.rs:60,90`). BUG: anyhow-`Err` path prints but never `exit(n)` (`main.rs:36-58`) → hard failures (linker, bad target, `--dump-json`) can exit 0. Never trust exit code alone. |

Intermediates (transient, deleted after link): per-module 4 objects `dst.o<base_n(i)>` + descriptor `dst.o` (`osdi/src/lib.rs:52-59,82`); verilogae `<dst><funprefix>.o` + `<file>_modelinfo.o` (`verilogae/src/lib.rs`). Linker stderr/stdout echoed via `eprintln!` + `linking failed (see linker output for details)` (`linker/src/lib.rs`).

## 2. Format grammars

## 2. Format grammars
### C1/C2 `.osdi` — OSDI 0.3 ABI (structured binary, dlopen contract)
- Schema: `openvaf/osdi/header/osdi_0_3.h`; generated Rust mirror `openvaf/tests/load/osdi_0_3.rs`; consumer pattern `libloading` + `dlsym` in `openvaf/tests/load/mod.rs`.
- Exported globals (emitted `osdi/src/lib.rs`): `OSDI_DESCRIPTORS` (array), `OSDI_NUM_DESCRIPTORS` (u32), `OSDI_VERSION_MAJOR=0`, `OSDI_VERSION_MINOR=3`, optional `OSDI_LIM_TABLE`/`OSDI_LIM_TABLE_LEN`, external `osdi_log`.
- Core consts: `PARA_TY_{REAL=0,INT=1,STR=2}`, `PARA_KIND_{MODEL,INST,OPVAR}=(k<<30)`, `CALC_{RESIST_RESIDUAL=1,…,NOISE=16,OP=32,…}`, `ANALYSIS_{DC=2048,AC=4096,TRAN=8192,…}`, `EVAL_RET_FLAG_{LIM=1,FATAL=2,FINISH=4,STOP=8}`, `LOG_LVL_{DEBUG=0…FATAL=5}`.
- Structs (repr(C), fixed offsets): `OsdiDescriptor{nodes,num_nodes,params,…}`, `OsdiParamOpvar`, `OsdiSimParas`, `OsdiLimFunction{name,num_args,func_ptr}`. Units/descriptions/groups are interned C strings per param/opvar (`lib.rs` `intern_names`, incl. `"deg"`, `"m"`, `"Multiplier (Verilog-A $mfactor)"`).
- Numbers: native doubles/ints in memory; no text number format. Real example: `integration_tests/DIODE/diode.va` → `diode.osdi` (`openvaf-driver/tests/cli.rs:39-46`); ngspice loads via `pre_osdi <file>.osdi` ([Usage](https://openvaf.github.io/docs/getting-started/usage/)).
- Stability: machine ABI pinned to header; FORK RISK: Reloaded master emits OSDI 0.4 (descriptor differs), `mb-experimental` OSDI 0.5; ngspice ≤42 accepts only 0.3 ([reloaded README](https://github.com/openvaf/openvaf-reloaded)).

### C9 verilogae `.mod`/`.modinfo` — symbol-table contract = `verilogae/src/api.rs`
- Globals read via `verilogae_*` accessors: `module_name`, `functions`, `functions.sym`, `functions.cnt`, `opvars(.cnt)`, `nodes(.cnt)`, `params.{real,integer,string}(.cnt)`, `params.{unit,desc,group}.{real,integer,string}`, per-function `fun.{N}{params.real,depbreak.real,voltages,currents,…}(.cnt)`, `voltages.default(.cnt)`, `init_modelcard` (writes real[3n],int[3n],str[n] + `ParamFlags` bitmask), `VaeFun(idx, FatPtr…)` kernels. `FatPtr<T> = {ptr, stride|s64 scalar}` — scalar-or-strided broadcast rule (`api.rs:223-257`).

### C6/C7 stderr text (codespan, ASCII `Chars::ascii()`, `sink.rs:136`)
```
^(error|warning)(\[L\d+\])?: <msg>$
  --> <path>:<line>:<col>
<n> | <source line>
  |   <^~~~> <label>
  = <note>            (zero or more)
```
Real example (`openvaf/test_data/ui/port_without_direction.log:1-9`):
```
error[L016]: no direction declared for port 'x'
  --> /port_without_direction.va:3:14
3 | module error(x);
  |              ^ 'x' is declared here without direction
  = port_without_direction is set to deny by default
```
Summary lines (`sink.rs:100-123`): ``could not compile `<f>` due to <E> previous errors[; <W> warning emitted]``; ``` `<f>` generated <W> warning ``` (singular even if plural — literal). Status: `Finished building <file> in <secs>s` / `Finished preprocessing …` (stderr, colorized iff tty). Verdict = summary/exit-65, never exit-0-alone (§1 C12 bug).

### C2/C3/C5 stdout
- Batchmode: single line = lib path. `--print-expansion`: raw preprocessed tokens + trailing newline (no headers). `--lints`: `ERRORS:\n    <name>…\nWARNINGS:…\nALLOWED:…`.

### C11 Python value shapes
`VaeModel{functions: dict[str,VaeFun], modelcard: dict[str,VaeParam], op_vars: list[str], module_name: str, nodes: list[str]}` (`model.rs:48-85`); `VaeParam{name,default,min,max,min_inclusive,max_inclusive,description,unit,group}`; `VaeFun{name,voltages,currents,parameters,depbreak: list[str], eval(**kw)->ndarray float64}`. Real call (`verilogae/tests/test_hicum.py:19-28`): `hl2=verilogae.load("hicumL2V2p4p0_vae.va"); itf=hl2.functions["itf"].eval(**args)` with `args={voltages:{br_bpbi:0.0,…}, temperature:ndarray, <params>…}`; `export_vfs(path)->dict(str,str)` path→contents.

## 3. Python bindings verdict

## 3. Python bindings (audit row: confirm/correct)
- `import verilogae` (`verilogae/__init__.py` → pyo3-ffi cdylib `verilogae_py` 1.0.0, py≥3.8, `setup.py`). Returns natively: full model introspection (modelcard w/ units+descriptions+bounds, nodes, opvars) + JIT-compiled evaluatable functions → numpy. CORRECTION: PyPI `verilogae==1.0.0` released **May 16 2023** (cp38–311 linux wheels), not "Jan 2022" — but STALE stands (no release in >3y, matches tree).
- `openvaf-py`: confirmed experimental 3rd-party (ChipFlow `vajax`, PyO3 over OpenVAF MIR → JAX; needs Rust+LLVM build; zero refs in this repo). ([pkg doc](https://github.com/chipflow/vajax/blob/HEAD/docs/packages/openvaf-py.md))
- Fork split confirmed: original `pascalkuthe/OpenVAF` dormant since late 2023; active `OpenVAF/openvaf-reloaded` (binary renamed `openvaf-r`, OSDI 0.4; `osdi_0.3` tag/branch frozen Dec 2024). This clone = OSDI-0.3 lineage.
- Caveat: `load()` compiles in-process (LLVM), violating TOOL-OUTPUTS "bindings read, subprocess runs" — usable only via worker-subprocess + dump-out pattern. GPL-3.0 license on all of it.

## 4. Stdio-only residue

## 4. STDIO-only residue (and why)
Only on stderr/stdout with no file/ABI mirror: per-diagnostic errors/warnings, `could not compile…`/`generated…warning` summaries, `Finished…` lines, fatal `error:` chains, linker passthrough, crash notice, `--lints/--supported-targets` listings, `--print-expansion` text, batchmode path print. Why: `ConsoleSink` writes solely to `StandardStream::stderr` (`sink.rs:92-93`); no JSON/report-file emitter exists and `--dump-json` is unimplemented — the CLI was built for human terminal consumption (`termcolor`, tty colors).

## 5. Adapter recommendation

## 5. Adapter recommendation (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1. **Structured file (primary, subprocess-clean): CLI `openvaf in.va -o out.osdi`, then read descriptors via dlopen/dlsym per `osdi_0_3.h`.** Keeps execution subprocess; machine ABI; covers params/nodes/opvars/meta. Watch: `.so` build-id/toolchain instability + OSDI 0.3-vs-0.4 fork今回は0.3固定.
2. **Bindings (equation-level, worker-subprocess only): `verilogae.load_info`** for metadata/modelcard without full codegen, `load` + `eval` for equation values → dump to JSON/npy from the worker. Incompatible with in-process use (LLVM compile inside `load`).
3. **Deterministic text (verdict/errors): stderr grammar §2 + exit 65.** Required in all paths because exit-0-on-hard-failure bug (§1 C12) makes exit code untrustworthy.
Do NOT plan on `--dump-json` at this rev. DEFER verdict upheld: pin fork (`openvaf` vs `openvaf-reloaded`) + rev + OSDI minor before any adapter; all evidence verified at clone `a9697ae7` (2023-10-30) / release 23.5.0+ / OSDI 0.3 / verilogae 1.0.0. Out of scope: melange simulator APIs, Rust-internal `mir_*` crates.

## Weak-evidence gaps (flagged by dissector)

- | C4 | `--dump-json` | DEAD FLAG: driver bails `currently unimplemented` (`main.rs:74-81`); impl commented out (`lib.rs:49-105`) | intended `<stem>_<module>.json` (never written) | none |
- | C12 | Exit status | any CLI run | n/a | `0` ok; `65` (`DATA_ERROR`) on `FatalDiagnostic` (`main.rs:60,90`). BUG: anyhow-`Err` path prints but never `exit(n)` (`main.rs:36-58`) → hard failures (linker, bad target, `--dump-json`) can exit 0. Never trust exit c
- - Core consts: `PARA_TY_{REAL=0,INT=1,STR=2}`, `PARA_KIND_{MODEL,INST,OPVAR}=(k<<30)`, `CALC_{RESIST_RESIDUAL=1,…,NOISE=16,OP=32,…}`, `ANALYSIS_{DC=2048,AC=4096,TRAN=8192,…}`, `EVAL_RET_FLAG_{LIM=1,FATAL=2,FINISH=4,STOP=8}`, `LOG_LVL_{DEBUG=0…FATAL=5}`.
- Summary lines (`sink.rs:100-123`): ``could not compile `<f>` due to <E> previous errors[; <W> warning emitted]``; ``` `<f>` generated <W> warning ``` (singular even if plural — literal). Status: `Finished building <file> in <secs>s` / `Finished preprocessing …
- 3. **Deterministic text (verdict/errors): stderr grammar §2 + exit 65.** Required in all paths because exit-0-on-hard-failure bug (§1 C12) makes exit code untrustworthy.
- - Pin: NONE. No openvaf entry in `rocket-engine/scripts/provision_toolchain.sh` (all pins grepped); audit row `UNPINNED, not in lock` confirmed.

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
# openvaf output-capability dissection

## Provenance (restated)
- Clone: `/tmp/rocket-tool-src/openvaf/` @ SHA `a9697ae7780518f021f9f64e819b3a57033bd39f`, date `2023-10-30`, remote `https://github.com/OpenVAF/openvaf` (pre-fork OSDI-0.3 lineage).
- Versions in tree: `openvaf` crate `0.1.2` (`openvaf/openvaf/Cargo.toml:3`), `verilogae_py`/`verilogae_ffi` `1.0.0`, release `23.5.0 (2023-05-16)` + `[UNRELEASED]` (`CHANGELOG_OSDI.md`), OSDI `0.3` (`openvaf/osdi/src/lib.rs:32`, `openvaf/osdi/header/osdi_0_3.h:8-9`).
- Pin: NONE. No openvaf entry in `rocket-engine/scripts/provision_toolchain.sh` (all pins grepped); audit row `UNPINNED, not in lock` confirmed.
- Docs: `/tmp/rocket-tool-docs/openvaf-index.html` is a 404 page (fetched, unusable). Fell back to in-repo + upstream web: [Usage](https://openvaf.github.io/docs/getting-started/usage/), [PyPI verilogae](https://pypi.org/project/verilogae/), [openvaf-reloaded](https://github.com/openvaf/openvaf-reloaded).

## 1. Result channels
| # | Channel | Producing flag/cmd | Filename/pattern | Stream/API |
|---|---|---|---|---|
| C1 | OSDI shared lib (primary) | `openvaf input.va [-o FILE]`; default `input.with_extension("osdi")` (`openvaf-driver/src/cli_process.rs:61-68`) | `<stem>.osdi` (ELF `.so` on Linux) | file |
| C2 | Batch cache lib | `--batch [--cache-dir DIR]` (default `ProjectDirs com/semimod/openvaf` cache) | `<base_n(md5)>.osdi` (`openvaf/src/cache.rs:51-55`) | file + stdout path print (`main.rs:84-87`) |
| C3 | Preprocessed source | `--print-expansion` | n/a | stdout (`openvaf/src/lib.rs:107-139`) |
| C4 | `--dump-json` | DEAD FLAG: driver bails `currently unimplemented` (`main.rs:74-81`); impl commented out (`lib.rs:49-105`) | intended `<stem>_<module>.json` (never written) | none |
| C5 | Listings | `--lints`, `--supported-targets` | n/a | stdout (`cli_process.rs:121-164`) |
| C6 | Diagnostics + status | any compile | n/a | stderr (codespan, see §2) |
| C7 | Fatal error chain | any hard failure | n/a | stderr `error: …` + `error: failed to compile <input>` (`main.rs:38-56`) |
| C8 | Crash report | panic (release only) | `$TMPDIR/openvaf-crash-<unixts>.log` + stderr notice (`crash_report.rs:69-88,160-172`) | file + stderr |
| C9 | verilogae cache libs | `verilogae_load(path, full_compile, opts)` (C ABI) / `verilogae.load/load_info` (Py) | `<base_n(md5)>.mod` (full) / `.modinfo` (info-only) in `com/semimod/verilogae` cache (`verilogae/src/cache.rs:50-61`) | file (dlopen'd in-process) |
| C10 | verilogae C ABI | `verilogae_load/export_vfs/fun_ptr/…` (`verilogae/src/api.rs`) | n/a | in-process FFI |
| C11 | verilogae Python | `import verilogae; load/load_info/export_vfs` (`verilogae_py/src/lib.rs:25-56`) | n/a | in-process objects + numpy |
| C12 | Exit status | any CLI run | n/a | `0` ok; `65` (`DATA_ERROR`) on `FatalDiagnostic` (`main.rs:60,90`). BUG: anyhow-`Err` path prints but never `exit(n)` (`main.rs:36-58`) → hard failures (linker, bad target, `--dump-json`) can exit 0. Never trust exit code alone. |

Intermediates (transient, deleted after link): per-module 4 objects `dst.o<base_n(i)>` + descriptor `dst.o` (`osdi/src/lib.rs:52-59,82`); verilogae `<dst><funprefix>.o` + `<file>_modelinfo.o` (`verilogae/src/lib.rs`). Linker stderr/stdout echoed via `eprintln!` + `linking failed (see linker output for details)` (`linker/src/lib.rs`).

## 2. Format grammars
### C1/C2 `.osdi` — OSDI 0.3 ABI (structured binary, dlopen contract)
- Schema: `openvaf/osdi/header/osdi_0_3.h`; generated Rust mirror `openvaf/tests/load/osdi_0_3.rs`; consumer pattern `libloading` + `dlsym` in `openvaf/tests/load/mod.rs`.
- Exported globals (emitted `osdi/src/lib.rs`): `OSDI_DESCRIPTORS` (array), `OSDI_NUM_DESCRIPTORS` (u32), `OSDI_VERSION_MAJOR=0`, `OSDI_VERSION_MINOR=3`, optional `OSDI_LIM_TABLE`/`OSDI_LIM_TABLE_LEN`, external `osdi_log`.
- Core consts: `PARA_TY_{REAL=0,INT=1,STR=2}`, `PARA_KIND_{MODEL,INST,OPVAR}=(k<<30)`, `CALC_{RESIST_RESIDUAL=1,…,NOISE=16,OP=32,…}`, `ANALYSIS_{DC=2048,AC=4096,TRAN=8192,…}`, `EVAL_RET_FLAG_{LIM=1,FATAL=2,FINISH=4,STOP=8}`, `LOG_LVL_{DEBUG=0…FATAL=5}`.
- Structs (repr(C), fixed offsets): `OsdiDescriptor{nodes,num_nodes,params,…}`, `OsdiParamOpvar`, `OsdiSimParas`, `OsdiLimFunction{name,num_args,func_ptr}`. Units/descriptions/groups are interned C strings per param/opvar (`lib.rs` `intern_names`, incl. `"deg"`, `"m"`, `"Multiplier (Verilog-A $mfactor)"`).
- Numbers: native doubles/ints in memory; no text number format. Real example: `integration_tests/DIODE/diode.va` → `diode.osdi` (`openvaf-driver/tests/cli.rs:39-46`); ngspice loads via `pre_osdi <file>.osdi` ([Usage](https://openvaf.github.io/docs/getting-started/usage/)).
- Stability: machine ABI pinned to header; FORK RISK: Reloaded master emits OSDI 0.4 (descriptor differs), `mb-experimental` OSDI 0.5; ngspice ≤42 accepts only 0.3 ([reloaded README](https://github.com/openvaf/openvaf-reloaded)).

### C9 verilogae `.mod`/`.modinfo` — symbol-table contract = `verilogae/src/api.rs`
- Globals read via `verilogae_*` accessors: `module_name`, `functions`, `functions.sym`, `functions.cnt`, `opvars(.cnt)`, `nodes(.cnt)`, `params.{real,integer,string}(.cnt)`, `params.{unit,desc,group}.{real,integer,string}`, per-function `fun.{N}{params.real,depbreak.real,voltages,currents,…}(.cnt)`, `voltages.default(.cnt)`, `init_modelcard` (writes real[3n],int[3n],str[n] + `ParamFlags` bitmask), `VaeFun(idx, FatPtr…)` kernels. `FatPtr<T> = {ptr, stride|s64 scalar}` — scalar-or-strided broadcast rule (`api.rs:223-257`).

### C6/C7 stderr text (codespan, ASCII `Chars::ascii()`, `sink.rs:136`)
```
^(error|warning)(\[L\d+\])?: <msg>$
  --> <path>:<line>:<col>
<n> | <source line>
  |   <^~~~> <label>
  = <note>            (zero or more)
```
Real example (`openvaf/test_data/ui/port_without_direction.log:1-9`):
```
error[L016]: no direction declared for port 'x'
  --> /port_without_direction.va:3:14
3 | module error(x);
  |              ^ 'x' is declared here without direction
  = port_without_direction is set to deny by default
```
Summary lines (`sink.rs:100-123`): ``could not compile `<f>` due to <E> previous errors[; <W> warning emitted]``; ``` `<f>` generated <W> warning ``` (singular even if plural — literal). Status: `Finished building <file> in <secs>s` / `Finished preprocessing …` (stderr, colorized iff tty). Verdict = summary/exit-65, never exit-0-alone (§1 C12 bug).

### C2/C3/C5 stdout
- Batchmode: single line = lib path. `--print-expansion`: raw preprocessed tokens + trailing newline (no headers). `--lints`: `ERRORS:\n    <name>…\nWARNINGS:…\nALLOWED:…`.

### C11 Python value shapes
`VaeModel{functions: dict[str,VaeFun], modelcard: dict[str,VaeParam], op_vars: list[str], module_name: str, nodes: list[str]}` (`model.rs:48-85`); `VaeParam{name,default,min,max,min_inclusive,max_inclusive,description,unit,group}`; `VaeFun{name,voltages,currents,parameters,depbreak: list[str], eval(**kw)->ndarray float64}`. Real call (`verilogae/tests/test_hicum.py:19-28`): `hl2=verilogae.load("hicumL2V2p4p0_vae.va"); itf=hl2.functions["itf"].eval(**args)` with `args={voltages:{br_bpbi:0.0,…}, temperature:ndarray, <params>…}`; `export_vfs(path)->dict(str,str)` path→contents.

## 3. Python bindings (audit row: confirm/correct)
- `import verilogae` (`verilogae/__init__.py` → pyo3-ffi cdylib `verilogae_py` 1.0.0, py≥3.8, `setup.py`). Returns natively: full model introspection (modelcard w/ units+descriptions+bounds, nodes, opvars) + JIT-compiled evaluatable functions → numpy. CORRECTION: PyPI `verilogae==1.0.0` released **May 16 2023** (cp38–311 linux wheels), not "Jan 2022" — but STALE stands (no release in >3y, matches tree).
- `openvaf-py`: confirmed experimental 3rd-party (ChipFlow `vajax`, PyO3 over OpenVAF MIR → JAX; needs Rust+LLVM build; zero refs in this repo). ([pkg doc](https://github.com/chipflow/vajax/blob/HEAD/docs/packages/openvaf-py.md))
- Fork split confirmed: original `pascalkuthe/OpenVAF` dormant since late 2023; active `OpenVAF/openvaf-reloaded` (binary renamed `openvaf-r`, OSDI 0.4; `osdi_0.3` tag/branch frozen Dec 2024). This clone = OSDI-0.3 lineage.
- Caveat: `load()` compiles in-process (LLVM), violating TOOL-OUTPUTS "bindings read, subprocess runs" — usable only via worker-subprocess + dump-out pattern. GPL-3.0 license on all of it.

## 4. STDIO-only residue (and why)
Only on stderr/stdout with no file/ABI mirror: per-diagnostic errors/warnings, `could not compile…`/`generated…warning` summaries, `Finished…` lines, fatal `error:` chains, linker passthrough, crash notice, `--lints/--supported-targets` listings, `--print-expansion` text, batchmode path print. Why: `ConsoleSink` writes solely to `StandardStream::stderr` (`sink.rs:92-93`); no JSON/report-file emitter exists and `--dump-json` is unimplemented — the CLI was built for human terminal consumption (`termcolor`, tty colors).

## 5. Adapter recommendation (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1. **Structured file (primary, subprocess-clean): CLI `openvaf in.va -o out.osdi`, then read descriptors via dlopen/dlsym per `osdi_0_3.h`.** Keeps execution subprocess; machine ABI; covers params/nodes/opvars/meta. Watch: `.so` build-id/toolchain instability + OSDI 0.3-vs-0.4 fork今回は0.3固定.
2. **Bindings (equation-level, worker-subprocess only): `verilogae.load_info`** for metadata/modelcard without full codegen, `load` + `eval` for equation values → dump to JSON/npy from the worker. Incompatible with in-process use (LLVM compile inside `load`).
3. **Deterministic text (verdict/errors): stderr grammar §2 + exit 65.** Required in all paths because exit-0-on-hard-failure bug (§1 C12) makes exit code untrustworthy.
Do NOT plan on `--dump-json` at this rev. DEFER verdict upheld: pin fork (`openvaf` vs `openvaf-reloaded`) + rev + OSDI minor before any adapter; all evidence verified at clone `a9697ae7` (2023-10-30) / release 23.5.0+ / OSDI 0.3 / verilogae 1.0.0. Out of scope: melange simulator APIs, Rust-internal `mir_*` crates.
```
