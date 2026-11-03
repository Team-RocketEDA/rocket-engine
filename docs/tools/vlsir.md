# vlsir — output dissection

Dissector ref: prior result 15 (text `handoff-3c3d9ef5ed711a4c2361f8a28e634347e4864443bdaf81676c5c662d2aac2bd5-141521f861e6cc7b5fde58b62a78a6231d17837af8bee6436fc5ee084f43e25d.txt`, summary `handoff-9713f2d11dc8071fa909b6574ff17ec2c9f73c6209e24d6179ac82ebc8ec4e67-be70fde1a09514fab773b6be65a48f9c4a732c64e92f83a1158ff517ac937db3.txt`; text == summary (modulo trailing newline)).
Synthesis owns this write; the dissector wrote nothing.

## Evidence

- Clone SHA: `194c7a76f01e02e246f8cde822f195e02168c64e`
- Clone date: `2026-02-15`
- Pin: PIN/VERSION: vlsir==7.0.0 + vlsirtools==7.0.0 — verified at: `bindings/python/setup.py:18`, `VlsirTools/setup.py:18`, `VlsirTools/vlsirtools/__init__.py:5`, `bindings/python/vlsir/__init__.py:8`, tests assert 7.0.0 (`VlsirTools/tests/test_vlsirtools.py:59`), PyPI live `info.version=7.0.0` for both (
- Doc/source URLs:
  - https://github.com/Vlsir/Vlsir
  - https://pypi.org/pypi/vlsir/json
  - https://pypi.org/pypi/vlsirtools/json

### Dissector header (verbatim, whitespace-trimmed)

```text
# vlsir output-capability dissection

CLONE SHA: 194c7a76f01e02e246f8cde822f195e02168c64e · DATE: 2026-02-15 (`git rev-parse HEAD`, `git log -1 --format=%cs` in /tmp/rocket-tool-src/vlsir/)
PIN/VERSION: vlsir==7.0.0 + vlsirtools==7.0.0 — verified at: `bindings/python/setup.py:18`, `VlsirTools/setup.py:18`, `VlsirTools/vlsirtools/__init__.py:5`, `bindings/python/vlsir/__init__.py:8`, tests assert 7.0.0 (`VlsirTools/tests/test_vlsirtools.py:59`), PyPI live `info.version=7.0.0` for both ([vlsir](https://pypi.org/pypi/vlsir/json), [vlsirtools](https://pypi.org/pypi/vlsirtools/json)). Deps: protobuf>=4.23, numpy, pandas (`VlsirTools/setup.py:31-35`), python>=3.7 (<3.13 for vlsirtools). NOT pinned in `rocket-engine/scripts/provision_toolchain.sh` (no vlsir entries) — audit's pin+lock action stands.
DOCS: no /tmp/rocket-tool-docs/vlsir-* fetched → fell back to in-repo readme/docs + upstream web (repo: https://github.com/Vlsir/Vlsir).
NATURE: vlsir is a protobuf schema + Python tooling repo, not a simulator binary. No daemon Binaries, no DBs. "hugc" from focus hint: ABSENT at this SHA (repo-wide grep for hugc/HuGC: zero hits) — no hugc outputs to cover.
```

## 1. Result channels

## 1. RESULT CHANNELS (one table)

| # | Channel | Producing call / flag | Filename / return | Content |
|---|---|---|---|---|
| C1 | Netlist text file / stream | `vlsirtools.netlist(pkg, dest, fmt)` (`VlsirTools/vlsirtools/netlist/main.py:28-68`); `dest`=any IO (file, StringIO, stdout) | caller-chosen (tests use `scratch/*.sp`); sim runs fix names below | spectre/spice/hspice/cdl/ngspice/xyce/verilog text |
| C2 | Netlist via proto RPC-style | `netlist_from_proto(NetlistInput)` (`netlist/main.py:71-82`) | writes `inp.netlist_path`; returns `NetlistResult` proto | same text as C1 + success/fail proto |
| C3 | CLI netlist | `python -m vlsirtools.cli netlist <NetlistInput.pb>` (`vlsirtools/cli/__main__.py:41-46,51-66`) | `netlist_path` file + optional `result_path` file (protobuf binary `NetlistResult`) | text + binary proto |
| C4 | CLI version (stdio) | `python -m vlsirtools.cli version ...` (`cli/__main__.py:38-39`) | stdout: `7.0.0` | version string only |
| C5 | proto2spice script | `scripts/proto2spice.py -p pkg.pb\|-l lib.pb -o output.sp -f xyce` (defaults: output=`output.sp`, format=`xyce`; accepts binary pb or textproto input) | `-o` path (default `output.sp`) | netlist text |
| C6 | In-process sim results (proto) | `vlsirtools.spice.sim(inp, SimOptions(fmt=VLSIR_PROTO))` — DEFAULT fmt (`spice/spice.py:58-72,85-145`) | returns `vsp.SimResult` (single input) or list | per-analysis results proto |
| C7 | In-process sim results (numpy) | same with `fmt=SIM_DATA` | returns `sim_data.SimResult` dataclass | dicts of np.ndarray + measurements |
| C8 | Sim rundir intermediates | any `sim()` with `opts.rundir` set, else tempdir auto-deleted (`spice/base.py:99-115`) | spectre: `netlist.scs`,`netlist.raw`; ngspice: `netlist.sp`,`netlist.raw`,`*.mt*/*.ms*`; xyce: `dut`,`<an>.sp`,`<an>.sp.csv`/`.FD.csv`,`*.m*0` | netlists + nutbin/CSV/meas files (see grammars) |
| C9 | Proto serialization (any msg) | `SerializeToString()` / `text_format` (protobuf API; schema in `protos/`) | caller-chosen `.pb` / `.textproto` | binary or text proto |
| C10 | SpiceCmp comparison rows | `SpiceCmp/spicecmp/compare_meas.py:compare_case()` | returns `List[MeasComparison]` in-process | Test/Dut/Corner/Temper/Measurement/Xyce/Spectre/Diff |
| C11 | Failure diagnostics | `SimError` exception (`spice/spice.py:148-162`) on nonzero sim subprocess rc (`spice/base.py:117-136`) | exception attrs `.stdout/.stderr/.rundir` (bytes) | captured sim console output |

NOT a channel: `cli sim` raises `NotImplementedError` (`cli/__main__.py:69-70`). Sweep/Monte/Custom analyses unimplemented in all 3 sim drivers (NotImplementedError).

## 2. Format grammars

## 2. FORMAT GRAMMARS

Schema files: `protos/circuit.proto`, `protos/spice.proto`, `protos/netlist.proto`, `protos/utils.proto`, `protos/tech.proto`, `protos/layout/raw.proto`, `protos/layout/tetris.proto`. Python bindings generated: `bindings/python/vlsir/*_pb2.py`.

### G1. `SimResult` proto (`protos/spice.proto:73-122`)
`SimResult { repeated AnalysisResult an }`; `AnalysisResult` oneof op/dc/tran/ac/noise/sweep/monte/custom. Per-result fields:
- OpResult: `analysis_name, signals[], data[]` (pairwise, `data[i]`↔`signals[i]`; L141-150)
- DcResult: + `indep_name`, flat `data[]` len=|signals|×npts, `map<string,double> measurements` (L170-182)
- TranResult: same shape as Dc minus indep (L202-213)
- AcResult: `freq[]` (Hz, real), `signals[]`, flat `ComplexNum{re,im}[]` len=|signals|×npts, measurements (L243-255)
- NoiseResult: `data[]` in V²/Hz or A²/Hz, `integrated_noise` map, measurements (L288-302)
- Units: plain SI doubles (s, Hz, V, A); no unit tags on the wire. Sweep oneof linear{start,stop,step}/log{start,stop,npts}/points{points[]} (L405-429).

### G2. `sim_data` mirror (`VlsirTools/vlsirtools/spice/sim_data.py`)
`SimResult.an: List[AnalysisResult]` + `AnalysisResultsTable` indexed by int|name|AnalysisType (`sim_data.py:163-229`). `OpResult{analysis_name, data:Mapping[str,float]}`; `Dc/TranResult{analysis_name[,indep_name], data:Mapping[str,np.ndarray], measurements}`; `AcResult{+freq:np.ndarray, complex data}`; each has `.to_proto()` (L41-106,231-236). Sweep/MonteResult raise NotImplementedError (L121-134).
Test usage (`tests/test_vlsirtools.py:428-473`): `sim(inp, SimOptions(simulator, fmt, rundir))` → `isinstance(sd.SimResult)` → `sd_results[AnalysisType.OP]` → `.to_proto()` → `vsp.SimResult`.

### G3. Netlist text — headers + spectre (`netlist/base.py:519-567`, `netlist/spectre.py`)
- Package header: `` `circuit.Package` `<domain>` `` or `Anonymous \`circuit.Package\`` + `` Generated by \`vlsirtools.<Class>\` `` (asserted in `tests/test_netlist.py:22-23` as `*`-comments for SPICE). No timestamps → byte-deterministic for fixed Package. Comment chars: SPICE `*`, Xyce `;`, spectre `//`, verilog `//`.
- Spectre sim file (`netlist.scs`): `simulator lang=spectre`, `global 0`, `subckt NAME` + continuation `+ port… `, instances, analyses: `<an> ac start=F stop=F dec=N` / `<an> dc param=P start… step…` / `<an> dc oppoint=rawfile` / `<an> tran stop=T` (`spectre.py:266-279,313-369`); DUT: `xtop 0 <mod> // Top-Level DUT`; include: `include "path"[ section=S]`; meas wrapped in `simulator lang=spice` … `.meas TYPE NAME EXPR` … `simulator lang=spectre`; params: `parameters NAME=VAL` (`spectre.py:261-306`).

### G4. Netlist text — SPICE dialects (`netlist/spice.py`)
- Generic: `.SUBCKT <name>` / `+ <ports>` / `+ <params>` … instances … `.ENDS` (`spice.py:76-118`); instance cards: `<PREFIX><name>` line + `+ <conns>` + `+ <subckt|model>` + `+ <params>` where PREFIX∈{X,R,C,L,V,I,…} by SpiceType (`spice.py:197-221`); expressions in single quotes `'expr'`; Xyce variant: `;` comments, `PARAMS:` keyword on decl+instance lines, `{expr}` braces (`spice.py:463-504`); DUT `xtop 0 <mod>`; `.include '/.lib/.meas/.param/.dc LIN|DEC|LIST/.tran/.ac DEC/.print … format=csv/.end` (Xyce L506-562; ngspice `.include "/.lib "/.meas/.param/.option/.ac dec/.dc param start stop step` L650-711).

### G5. Netlist text — Verilog (`netlist/verilog.py:24-77,106-225`)
`module NAME` `#( parameter P = D, … )` `( input wire A, output wire [w-1:0] B );` `wire internal;` instances `MOD #( .P(V),… ) INST ( .p(net),… );` `endmodule // NAME`. Directed ports required (NONE→RuntimeError); primitives rejected (RuntimeError) — `tests/test_vlsirtools.py:361-363` asserts verilog fails on the analog testbench.

### G6. Xyce CSV + measurements (`spice/xyce.py:170-202,383-399`)
`<an>.sp.csv` (dc/tran/op) and `<an>.sp.FD.csv` (ac): pandas-readable, header row = signal names; AC pairs `Re(NAME)`/`Im(NAME)` columns + `FREQ` col, zipped to complex (L181-191). Meas files `*<an>*.m*0`: lines `NAME = VALUE` (exactly 3 whitespace tokens, else RuntimeError), keys lowercased (L364-374,390-399).

### G7. nutbin raw (`spice/ngspice.py:265-394`, `spice/spectre.py:220-345`)
ASCII header then binary: `Plotname: …` … `Flags: real|complex[ …]` … `No. Variables: N` … `No. Points: M` … `Variables:` + N lines `<idx> <name> <units>` … `Binary:` then N·M doubles, de-interleaved `data[name]=bin[i::N]`. ngspice reads little-endian (`newbyteorder("<")`, L369-372), spectre big-endian (`">"`, L322-324). Dispatch keys ngspice: `Plotname: Operating Point|DC Analysis|AC Analysis|Transient Analysis` (spectre keys by `analysis_name` instead, L98). Units vocab differs: ngspice `seconds/voltage/current/frequency` vs spectre `s/V/A/Hz` (ngspice.py:227-244, spectre.py:189-199).

### G8. mt0/ms0 meas (`spice/ngspice.py:396-413`, identical `spectre.py:348-365`)
4 lines: header, title, space-sep NAMES, space-sep VALUES; unparseable→NaN. Glob `*.mt*` (ac/tran) / `*.ms*` (dc); >1 match warns, first wins (L188-198).

### G9. `NetlistResult` proto (`protos/netlist.proto:34-39`)
oneof `{bool success=1; string fail=2}`; `NetlistFormat` enum UNSPECIFIED/SPECTRE/SPICE/NGSPICE/XYCE/HSPICE/CDL/VERILOG (L23-32); CLI writes it binary to `result_path` (`cli/__main__.py:62-64`).

### G10. Layout/tech protos (schema-only, no writers in repo)
raw.proto: Point{x,y int64}, Units{MICRO,NANO,ANGSTROM}, Layer{number,purpose}, Rectangle/Polygon/Path + net, LayerShapes, Instance{name,cell,origin_location,reflect_vert,rotation_clockwise_degrees}, Layout/Abstract/Cell/Library{domain,units,cells[],author}. tetris.proto: gridded Outline{x[],y[],metals}, Assign{net,TrackCross{track,cross}}, TrackRef{layer,track}, ports edge/ztop_edge/ztop_inner, Stack/MetalLayer/ViaLayer/TrackSpec. tech.proto: Technology{name,packages[],layers[]}. proto2spice extracts `cell.module` from a raw Library into a Package (scripts/proto2spice.py load_library_into_package).

## 3. Python bindings verdict

## 3. PYTHON BINDINGS (audit-row verdict: CONFIRMED both rows)
- `import vlsir` (+`vlsir.circuit/circuit_pb2, spice/spice_pb2, netlist/netlist_pb2, utils/utils_pb2, raw/raw_pb2, tetris/tetris_pb2`; utils names re-exported top-level) — `bindings/python/vlsir/__init__.py:10-19`. Returns protobuf messages natively (binary + textproto via protobuf runtime). Row "vlsir … protobuf schemas … protobuf (binary + textproto)" CORRECT.
- `import vlsirtools` (`netlist` fn, `spice.sim/SimOptions/ResultFormat/SupportedSimulators`, `spice.{xyce,spectre,ngspice}`, `primitives`, `spicetype.SpiceType`) — `VlsirTools/vlsirtools/__init__.py:8-22`. Returns `SimResult` proto or numpy dataclasses (C6/C7). Row "vlsirtools … spice sim drivers … SimResult protobuf / numpy dataclasses" CORRECT.
- Caveat vs audit's "bindings for READING, never running": `vlsirtools.spice.sim()` both WRITES netlists and shells out to spectre/Xyce/ngspice via subprocess (`base.py:117-136`) orchestrated by ThreadPoolExecutor (`spice.py:135-136`) — sim binaries stay subprocess-isolated, but the driver is an in-process runner, not a pure dump-reader. Rust bindings also exist (`bindings/rust/`, prost-based); C++/Julia/TS present but unmaintained per readme.

## 4. Stdio-only residue

## 4. STDIO-ONLY RESIDUE: ~NONE on success
- Only stdout emission in-repo: CLI `version` print (C4). All result data goes to files/API returns/protos.
- Sim subprocess stdout/stderr are piped and DISCARDED on success; on nonzero rc they surface only inside the raised `SimError` (`.stdout/.stderr` bytes + `.rundir`), never parsed into results (`base.py:122-136`, `spice.py:148-162`). Simulator console logs are therefore failure-diagnostics-only residue — an adapter wanting them must catch SimError or rerun the binary itself. Netlist `.raw/.csv` rundir files survive only if `opts.rundir` is set (else tempdir cleaned, `base.py:112-115`).

## 5. Adapter recommendation

## 5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1. **Bindings (first)**: read via `vlsirtools.spice.sim(..., SimOptions(fmt=SIM_DATA))` for numpy-native post-processing, or `VLSIR_PROTO` (default) for portable `SimResult` protos; parse any `.pb` with `ParseFromString`/text_format against `protos/*.proto`. For netlists call `vlsirtools.netlist(pkg, dest, fmt)` in the reader (deterministic, no timestamps).
2. **Structured files (fallback)**: Xyce `<an>.sp.csv`/`.FD.csv` (pandas) + `*.m*0` (`NAME = VALUE`); ngspice/spectre `netlist.raw` via in-repo `parse_nutbin` + `parse_mt0` (do NOT reimplement endianness/units); CLI `result_path` NetlistResult binary.
3. **Deterministic text (last)**: emitted netlists are golden-able (fixed headers, no dates); do not scrape simulator stdout (unparsed by design).
Verified-at evidence: clone SHA+date above; vlsir==vlsirtools==7.0.0 (setup.py files, `__version__`, PyPI live); protobuf>=4.23 + numpy + pandas required; sim backends needed on PATH only for live sim (spectre/xyce/ngspice availability probes: `spice/{spectre,xyce,ngspice}.py:available()`).

## Weak-evidence gaps (flagged by dissector)

- PIN/VERSION: vlsir==7.0.0 + vlsirtools==7.0.0 — verified at: `bindings/python/setup.py:18`, `VlsirTools/setup.py:18`, `VlsirTools/vlsirtools/__init__.py:5`, `bindings/python/vlsir/__init__.py:8`, tests assert 7.0.0 (`VlsirTools/tests/test_vlsirtools.py:59`), P

## Appendix: full dissector text (verbatim, trailing whitespace trimmed)

```text
# vlsir output-capability dissection

CLONE SHA: 194c7a76f01e02e246f8cde822f195e02168c64e · DATE: 2026-02-15 (`git rev-parse HEAD`, `git log -1 --format=%cs` in /tmp/rocket-tool-src/vlsir/)
PIN/VERSION: vlsir==7.0.0 + vlsirtools==7.0.0 — verified at: `bindings/python/setup.py:18`, `VlsirTools/setup.py:18`, `VlsirTools/vlsirtools/__init__.py:5`, `bindings/python/vlsir/__init__.py:8`, tests assert 7.0.0 (`VlsirTools/tests/test_vlsirtools.py:59`), PyPI live `info.version=7.0.0` for both ([vlsir](https://pypi.org/pypi/vlsir/json), [vlsirtools](https://pypi.org/pypi/vlsirtools/json)). Deps: protobuf>=4.23, numpy, pandas (`VlsirTools/setup.py:31-35`), python>=3.7 (<3.13 for vlsirtools). NOT pinned in `rocket-engine/scripts/provision_toolchain.sh` (no vlsir entries) — audit's pin+lock action stands.
DOCS: no /tmp/rocket-tool-docs/vlsir-* fetched → fell back to in-repo readme/docs + upstream web (repo: https://github.com/Vlsir/Vlsir).
NATURE: vlsir is a protobuf schema + Python tooling repo, not a simulator binary. No daemon Binaries, no DBs. "hugc" from focus hint: ABSENT at this SHA (repo-wide grep for hugc/HuGC: zero hits) — no hugc outputs to cover.

## 1. RESULT CHANNELS (one table)

| # | Channel | Producing call / flag | Filename / return | Content |
|---|---|---|---|---|
| C1 | Netlist text file / stream | `vlsirtools.netlist(pkg, dest, fmt)` (`VlsirTools/vlsirtools/netlist/main.py:28-68`); `dest`=any IO (file, StringIO, stdout) | caller-chosen (tests use `scratch/*.sp`); sim runs fix names below | spectre/spice/hspice/cdl/ngspice/xyce/verilog text |
| C2 | Netlist via proto RPC-style | `netlist_from_proto(NetlistInput)` (`netlist/main.py:71-82`) | writes `inp.netlist_path`; returns `NetlistResult` proto | same text as C1 + success/fail proto |
| C3 | CLI netlist | `python -m vlsirtools.cli netlist <NetlistInput.pb>` (`vlsirtools/cli/__main__.py:41-46,51-66`) | `netlist_path` file + optional `result_path` file (protobuf binary `NetlistResult`) | text + binary proto |
| C4 | CLI version (stdio) | `python -m vlsirtools.cli version ...` (`cli/__main__.py:38-39`) | stdout: `7.0.0` | version string only |
| C5 | proto2spice script | `scripts/proto2spice.py -p pkg.pb\|-l lib.pb -o output.sp -f xyce` (defaults: output=`output.sp`, format=`xyce`; accepts binary pb or textproto input) | `-o` path (default `output.sp`) | netlist text |
| C6 | In-process sim results (proto) | `vlsirtools.spice.sim(inp, SimOptions(fmt=VLSIR_PROTO))` — DEFAULT fmt (`spice/spice.py:58-72,85-145`) | returns `vsp.SimResult` (single input) or list | per-analysis results proto |
| C7 | In-process sim results (numpy) | same with `fmt=SIM_DATA` | returns `sim_data.SimResult` dataclass | dicts of np.ndarray + measurements |
| C8 | Sim rundir intermediates | any `sim()` with `opts.rundir` set, else tempdir auto-deleted (`spice/base.py:99-115`) | spectre: `netlist.scs`,`netlist.raw`; ngspice: `netlist.sp`,`netlist.raw`,`*.mt*/*.ms*`; xyce: `dut`,`<an>.sp`,`<an>.sp.csv`/`.FD.csv`,`*.m*0` | netlists + nutbin/CSV/meas files (see grammars) |
| C9 | Proto serialization (any msg) | `SerializeToString()` / `text_format` (protobuf API; schema in `protos/`) | caller-chosen `.pb` / `.textproto` | binary or text proto |
| C10 | SpiceCmp comparison rows | `SpiceCmp/spicecmp/compare_meas.py:compare_case()` | returns `List[MeasComparison]` in-process | Test/Dut/Corner/Temper/Measurement/Xyce/Spectre/Diff |
| C11 | Failure diagnostics | `SimError` exception (`spice/spice.py:148-162`) on nonzero sim subprocess rc (`spice/base.py:117-136`) | exception attrs `.stdout/.stderr/.rundir` (bytes) | captured sim console output |

NOT a channel: `cli sim` raises `NotImplementedError` (`cli/__main__.py:69-70`). Sweep/Monte/Custom analyses unimplemented in all 3 sim drivers (NotImplementedError).

## 2. FORMAT GRAMMARS

Schema files: `protos/circuit.proto`, `protos/spice.proto`, `protos/netlist.proto`, `protos/utils.proto`, `protos/tech.proto`, `protos/layout/raw.proto`, `protos/layout/tetris.proto`. Python bindings generated: `bindings/python/vlsir/*_pb2.py`.

### G1. `SimResult` proto (`protos/spice.proto:73-122`)
`SimResult { repeated AnalysisResult an }`; `AnalysisResult` oneof op/dc/tran/ac/noise/sweep/monte/custom. Per-result fields:
- OpResult: `analysis_name, signals[], data[]` (pairwise, `data[i]`↔`signals[i]`; L141-150)
- DcResult: + `indep_name`, flat `data[]` len=|signals|×npts, `map<string,double> measurements` (L170-182)
- TranResult: same shape as Dc minus indep (L202-213)
- AcResult: `freq[]` (Hz, real), `signals[]`, flat `ComplexNum{re,im}[]` len=|signals|×npts, measurements (L243-255)
- NoiseResult: `data[]` in V²/Hz or A²/Hz, `integrated_noise` map, measurements (L288-302)
- Units: plain SI doubles (s, Hz, V, A); no unit tags on the wire. Sweep oneof linear{start,stop,step}/log{start,stop,npts}/points{points[]} (L405-429).

### G2. `sim_data` mirror (`VlsirTools/vlsirtools/spice/sim_data.py`)
`SimResult.an: List[AnalysisResult]` + `AnalysisResultsTable` indexed by int|name|AnalysisType (`sim_data.py:163-229`). `OpResult{analysis_name, data:Mapping[str,float]}`; `Dc/TranResult{analysis_name[,indep_name], data:Mapping[str,np.ndarray], measurements}`; `AcResult{+freq:np.ndarray, complex data}`; each has `.to_proto()` (L41-106,231-236). Sweep/MonteResult raise NotImplementedError (L121-134).
Test usage (`tests/test_vlsirtools.py:428-473`): `sim(inp, SimOptions(simulator, fmt, rundir))` → `isinstance(sd.SimResult)` → `sd_results[AnalysisType.OP]` → `.to_proto()` → `vsp.SimResult`.

### G3. Netlist text — headers + spectre (`netlist/base.py:519-567`, `netlist/spectre.py`)
- Package header: `` `circuit.Package` `<domain>` `` or `Anonymous \`circuit.Package\`` + `` Generated by \`vlsirtools.<Class>\` `` (asserted in `tests/test_netlist.py:22-23` as `*`-comments for SPICE). No timestamps → byte-deterministic for fixed Package. Comment chars: SPICE `*`, Xyce `;`, spectre `//`, verilog `//`.
- Spectre sim file (`netlist.scs`): `simulator lang=spectre`, `global 0`, `subckt NAME` + continuation `+ port… `, instances, analyses: `<an> ac start=F stop=F dec=N` / `<an> dc param=P start… step…` / `<an> dc oppoint=rawfile` / `<an> tran stop=T` (`spectre.py:266-279,313-369`); DUT: `xtop 0 <mod> // Top-Level DUT`; include: `include "path"[ section=S]`; meas wrapped in `simulator lang=spice` … `.meas TYPE NAME EXPR` … `simulator lang=spectre`; params: `parameters NAME=VAL` (`spectre.py:261-306`).

### G4. Netlist text — SPICE dialects (`netlist/spice.py`)
- Generic: `.SUBCKT <name>` / `+ <ports>` / `+ <params>` … instances … `.ENDS` (`spice.py:76-118`); instance cards: `<PREFIX><name>` line + `+ <conns>` + `+ <subckt|model>` + `+ <params>` where PREFIX∈{X,R,C,L,V,I,…} by SpiceType (`spice.py:197-221`); expressions in single quotes `'expr'`; Xyce variant: `;` comments, `PARAMS:` keyword on decl+instance lines, `{expr}` braces (`spice.py:463-504`); DUT `xtop 0 <mod>`; `.include '/.lib/.meas/.param/.dc LIN|DEC|LIST/.tran/.ac DEC/.print … format=csv/.end` (Xyce L506-562; ngspice `.include "/.lib "/.meas/.param/.option/.ac dec/.dc param start stop step` L650-711).

### G5. Netlist text — Verilog (`netlist/verilog.py:24-77,106-225`)
`module NAME` `#( parameter P = D, … )` `( input wire A, output wire [w-1:0] B );` `wire internal;` instances `MOD #( .P(V),… ) INST ( .p(net),… );` `endmodule // NAME`. Directed ports required (NONE→RuntimeError); primitives rejected (RuntimeError) — `tests/test_vlsirtools.py:361-363` asserts verilog fails on the analog testbench.

### G6. Xyce CSV + measurements (`spice/xyce.py:170-202,383-399`)
`<an>.sp.csv` (dc/tran/op) and `<an>.sp.FD.csv` (ac): pandas-readable, header row = signal names; AC pairs `Re(NAME)`/`Im(NAME)` columns + `FREQ` col, zipped to complex (L181-191). Meas files `*<an>*.m*0`: lines `NAME = VALUE` (exactly 3 whitespace tokens, else RuntimeError), keys lowercased (L364-374,390-399).

### G7. nutbin raw (`spice/ngspice.py:265-394`, `spice/spectre.py:220-345`)
ASCII header then binary: `Plotname: …` … `Flags: real|complex[ …]` … `No. Variables: N` … `No. Points: M` … `Variables:` + N lines `<idx> <name> <units>` … `Binary:` then N·M doubles, de-interleaved `data[name]=bin[i::N]`. ngspice reads little-endian (`newbyteorder("<")`, L369-372), spectre big-endian (`">"`, L322-324). Dispatch keys ngspice: `Plotname: Operating Point|DC Analysis|AC Analysis|Transient Analysis` (spectre keys by `analysis_name` instead, L98). Units vocab differs: ngspice `seconds/voltage/current/frequency` vs spectre `s/V/A/Hz` (ngspice.py:227-244, spectre.py:189-199).

### G8. mt0/ms0 meas (`spice/ngspice.py:396-413`, identical `spectre.py:348-365`)
4 lines: header, title, space-sep NAMES, space-sep VALUES; unparseable→NaN. Glob `*.mt*` (ac/tran) / `*.ms*` (dc); >1 match warns, first wins (L188-198).

### G9. `NetlistResult` proto (`protos/netlist.proto:34-39`)
oneof `{bool success=1; string fail=2}`; `NetlistFormat` enum UNSPECIFIED/SPECTRE/SPICE/NGSPICE/XYCE/HSPICE/CDL/VERILOG (L23-32); CLI writes it binary to `result_path` (`cli/__main__.py:62-64`).

### G10. Layout/tech protos (schema-only, no writers in repo)
raw.proto: Point{x,y int64}, Units{MICRO,NANO,ANGSTROM}, Layer{number,purpose}, Rectangle/Polygon/Path + net, LayerShapes, Instance{name,cell,origin_location,reflect_vert,rotation_clockwise_degrees}, Layout/Abstract/Cell/Library{domain,units,cells[],author}. tetris.proto: gridded Outline{x[],y[],metals}, Assign{net,TrackCross{track,cross}}, TrackRef{layer,track}, ports edge/ztop_edge/ztop_inner, Stack/MetalLayer/ViaLayer/TrackSpec. tech.proto: Technology{name,packages[],layers[]}. proto2spice extracts `cell.module` from a raw Library into a Package (scripts/proto2spice.py load_library_into_package).

## 3. PYTHON BINDINGS (audit-row verdict: CONFIRMED both rows)
- `import vlsir` (+`vlsir.circuit/circuit_pb2, spice/spice_pb2, netlist/netlist_pb2, utils/utils_pb2, raw/raw_pb2, tetris/tetris_pb2`; utils names re-exported top-level) — `bindings/python/vlsir/__init__.py:10-19`. Returns protobuf messages natively (binary + textproto via protobuf runtime). Row "vlsir … protobuf schemas … protobuf (binary + textproto)" CORRECT.
- `import vlsirtools` (`netlist` fn, `spice.sim/SimOptions/ResultFormat/SupportedSimulators`, `spice.{xyce,spectre,ngspice}`, `primitives`, `spicetype.SpiceType`) — `VlsirTools/vlsirtools/__init__.py:8-22`. Returns `SimResult` proto or numpy dataclasses (C6/C7). Row "vlsirtools … spice sim drivers … SimResult protobuf / numpy dataclasses" CORRECT.
- Caveat vs audit's "bindings for READING, never running": `vlsirtools.spice.sim()` both WRITES netlists and shells out to spectre/Xyce/ngspice via subprocess (`base.py:117-136`) orchestrated by ThreadPoolExecutor (`spice.py:135-136`) — sim binaries stay subprocess-isolated, but the driver is an in-process runner, not a pure dump-reader. Rust bindings also exist (`bindings/rust/`, prost-based); C++/Julia/TS present but unmaintained per readme.

## 4. STDIO-ONLY RESIDUE: ~NONE on success
- Only stdout emission in-repo: CLI `version` print (C4). All result data goes to files/API returns/protos.
- Sim subprocess stdout/stderr are piped and DISCARDED on success; on nonzero rc they surface only inside the raised `SimError` (`.stdout/.stderr` bytes + `.rundir`), never parsed into results (`base.py:122-136`, `spice.py:148-162`). Simulator console logs are therefore failure-diagnostics-only residue — an adapter wanting them must catch SimError or rerun the binary itself. Netlist `.raw/.csv` rundir files survive only if `opts.rundir` is set (else tempdir cleaned, `base.py:112-115`).

## 5. ADAPTER RECOMMENDATION (per TOOL-OUTPUTS: bindings > structured files > deterministic text)
1. **Bindings (first)**: read via `vlsirtools.spice.sim(..., SimOptions(fmt=SIM_DATA))` for numpy-native post-processing, or `VLSIR_PROTO` (default) for portable `SimResult` protos; parse any `.pb` with `ParseFromString`/text_format against `protos/*.proto`. For netlists call `vlsirtools.netlist(pkg, dest, fmt)` in the reader (deterministic, no timestamps).
2. **Structured files (fallback)**: Xyce `<an>.sp.csv`/`.FD.csv` (pandas) + `*.m*0` (`NAME = VALUE`); ngspice/spectre `netlist.raw` via in-repo `parse_nutbin` + `parse_mt0` (do NOT reimplement endianness/units); CLI `result_path` NetlistResult binary.
3. **Deterministic text (last)**: emitted netlists are golden-able (fixed headers, no dates); do not scrape simulator stdout (unparsed by design).
Verified-at evidence: clone SHA+date above; vlsir==vlsirtools==7.0.0 (setup.py files, `__version__`, PyPI live); protobuf>=4.23 + numpy + pandas required; sim backends needed on PATH only for live sim (spectre/xyce/ngspice availability probes: `spice/{spectre,xyce,ngspice}.py:available()`).
```
