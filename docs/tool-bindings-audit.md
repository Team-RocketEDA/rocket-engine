# Tool-bindings audit: what MVP reads, and how

*Date: 2026-11-01 · Branch: GREEN-the-tests · Sources: 5 researcher reports (71 tools) cross-checked against `contracts/v1/catalog/tasks.json` delivery flags and the directive: heavy physics, opensta, xyce, openems stay deferred.*

Rule (from TOOL-OUTPUTS): execution stays subprocess; bindings are for
READING results, never for running tools in-process.

## Verdict counts (synthesis, 71 tools)

| Verdict | Count | Meaning for MVP |
|---|---|---|
| KEEP-BINDINGS | 31 | Read via native Python API / queryable DB; dump-first |
| KEEP-STRUCTURED | 10 | Read via machine grammar (JSON/XML/VCD/SQLite/SPEF/probe files) |
| KEEP-PARSE-ONLY | 4 | Pinned text scrape allowed ONLY on the determinism case below |
| DEFER | 26 | Not in MVP; reason in deferred list |

Researchers said 46/13/5/7. Synthesis moved 19 to DEFER (directive +
post_mvp/off_mvp delivery flags), ngspice BINDINGS→PARSE-ONLY
(dump-first: raw ASCII, shared-lib binding is post-MVP), and icarus
PARSE-ONLY→STRUCTURED (VCD is IEEE-grammar-stable).

## Per-tool table

### digital-rtl (bundle oss-cad-suite 20261025 unless noted)

| tool | pin | adapter | bindings + evidence | structured escapes | MVP verdict |
|---|---|---|---|---|---|
| yosys | 0.70 | synth_yosys | pyosys official BUT lags bundle (0.58/0.69 vs 0.70) and is exit()-unsafe in-process (ordec eval); do NOT use | write_json (Manual C.236, nextpnr-consumed), write_rtlil | KEEP-STRUCTURED |
| abc | bundle | — (via yosys `abc` pass) | none (no PyPI) | none; adapter treats `ABC: Warning:` as noise | DEFER (yosys owns interface) |
| slang | bundle | syntax | pyslang official (`pip install pyslang`, sv-lang.com) | --ast-json + JSON diagnostics | KEEP-BINDINGS |
| yosys_slang | bundle | — | none (C++ plugin, `read_slang`) | inherits yosys write_json | KEEP-STRUCTURED |
| sby | v0.70 | formal_sby | none (PyPI 404) | status-file verdict + `DONE (PASS/FAIL/UNKNOWN/ERROR, rc=N)` + `summary:` lines + CEX VCD; exit != verdict | KEEP-STRUCTURED |
| eqy | bundle | — | none (src/eqy.py, no importable API) | sby-style DONE grammar + partition JSON files | KEEP-STRUCTURED |
| mcy | bundle | — | none (PyPI 404) | SQLite `database/db.sqlite3` + design.il | KEEP-STRUCTURED |
| z3 | bundle | — (sby engine) | z3-solver official PyPI | SMT-LIB2 | KEEP-BINDINGS |
| boolector | bundle | — (sby engine) | PyBoolector, maintainer = upstream dev | SMT-LIB2 | KEEP-BINDINGS |
| bitwuzla | bundle | — (sby engine) | official bitwuzla PyPI (aniemetz/mpreiner) | SMT-LIB2 | KEEP-BINDINGS |
| yices | bundle | — (sby engine) | `yices` PyPI stale (py2.7–3.6 classifiers), needs separate libyices | SMT-LIB2 CLI fallback | DEFER (stale bindings) |
| cvc4 | bundle | — | none (PyPI 404); legacy predecessor of cvc5 | SMT-LIB2 CLI | DEFER (legacy) |
| cvc5 | bundle | — (sby engine) | official `cvc5` PyPI 1.4.2 | SMT-LIB2 | KEEP-BINDINGS |
| icarus | bundle | hdl_sim, cosim | none | VCD via $dumpfile/$dumpvars (IEEE grammar); compile `file:line: msg` + exit 2; `$error` exits 0 so verdict always parsed | KEEP-STRUCTURED |
| verilator | bundle | — | none official; pyverilator is stale Alpha — reject | --xml-only (docs/xml.rst); --json-only on 5.x; VCD/FST | KEEP-STRUCTURED |
| ghdl | bundle | — | pyGHDL official (`pyGHDL.libghdl`, release wheels); PyPI `pyghdl` stale 1.0.dev0 — use bundle/upstream | --vcd/--fst | KEEP-BINDINGS |
| cocotb | 2.1.0 locked | — (harness) | native Python; lock == PyPI latest | results.xml xUnit/JUnit | KEEP-BINDINGS |
| nextpnr | bundle | — | build-time pybind11 API, bundle availability unverified | --report JSON + JSON netlist I/O | DEFER (off_mvp FPGA) |
| icestorm | bundle | — | in-repo pure-Python `icebox` (bundle copy; no PyPI) | chipdb-*.txt tables; bitstream via icepack | DEFER (off_mvp FPGA) |
| trellis | bundle | — | pytrellis official bundle module (Boost::Python; no PyPI) | ECP5 bitstream DB + nextpnr JSON | DEFER (off_mvp FPGA) |
| oxide | bundle | — | in-repo pyo3 bindings (dev/fuzzer-oriented; no PyPI) | BBA chipdb | DEFER (off_mvp FPGA) |
| apicula | bundle | — | python-native (chipdb.py; bundle copy; PyPI Apycula is 0.0.1a5 alpha) | chipdb/BBA | DEFER (off_mvp FPGA) |
| amaranth | UNPINNED | — | native Python (HDL+sim+build) | Verilog-2001 emission | KEEP-BINDINGS (ACTION: pin) |

### physical

| tool | pin | adapter | bindings + evidence | structured escapes | MVP verdict |
|---|---|---|---|---|---|
| openroad | 2.x via LibreLane nix-eda 6.11.0 closure | — (flow-internal) | OFFICIAL: Python API is now a Bazel-built wheel — `openroad -python` NO LONGER EXISTS upstream (dissection correction; re-verify inside LibreLane 3.0.17 closure). WARNING: PyPI `openroad` 0.0.1 is UNOFFICIAL squat (ethanmoon) — never use | .odb checkpoints, LEF/DEF, SPEF, SDC, `-metrics file.json` | KEEP-BINDINGS |
| opendb | via openroad closure | — | OFFICIAL: `import odb` inside `openroad -python` (same repo src/odb) | queryable .odb; LEF/DEF round-trip | KEEP-BINDINGS |
| opensta | 857316f | timing_sta (deferred) | NONE standalone (Tcl interpreter only; `sta` python module exists solely inside OpenROAD) | none (report text) | DEFER (directive; STA-text grammar kept as residue) |
| openrcx | via openroad/LibreLane closure | — | NONE of its own (Tcl cmds inside openroad) | SPEF output (IEEE 1481) + queryable .odb | KEEP-STRUCTURED |
| magic | 707d67e (expect 8.3) | drc, extract_magic | NONE (Tcl/Tk over stdin) | .ext/.spice/.sim extraction files | KEEP-PARSE-ONLY |
| netgen | e310f30 (expect 1.5) | lvs_netgen | NONE (Tcl batch; PyPI/apt `netgen` may be mesh-generator collision — banner-probe) | none (report text) | KEEP-PARSE-ONLY |
| klayout | 0.30.12 locked | drc_kl | NATIVE official: PyPI `klayout` 0.30.12 (owner matthias67) + `pya`/`klayout.db` | .lyrdb report-DB XML; GDS/OASIS I/O | KEEP-BINDINGS |
| gdsfactory | 9.51.0 locked | gdsfactory | NATIVE Python library | GDS/OASIS/STL/GERBER + YAML settings/netlists | KEEP-BINDINGS |
| kfactory | 3.0.4 locked (transitive) | — | NATIVE Python on KLayout engine. STALE: clone is 3.5.0 needing klayout>=0.30.12 (dissection) — satisfied by pin 0.30.12, re-lock on adopt | KCell/DKCell, kdb.Region; GDS/OASIS | KEEP-BINDINGS |

### analog

| tool | pin | adapter | bindings + evidence | structured escapes | MVP verdict |
|---|---|---|---|---|---|
| ngspice | 47 (expect ngspice-4) | ngspice, postlayout, cosim | No PyPI (404). C shared-lib API (manual ch.19) + PySpice CFFI exist but are POST-MVP; MVP reads dumps | `-r rawfile` ASCII (`SPICE_ASCIIRAWFILE`/`filetype=ascii`, ch.16), `wrdata` tables | KEEP-PARSE-ONLY |
| xyce | Release-7.10.0 | — | PyPI `xyce` is a PLACEHOLDER (PyMi needs separate shared-object build, not pip-installable) | .PRINT FORMAT=CSV/RAW, .MEASURE .mt0/.ms0/.ma0 | DEFER (directive) |
| xschem | 7811010 (expect V3) | — | NONE official (Tcl/Tk; pyxschem is self-declared WIP, not for production) | product IS text: batch `xschem -n -x -q -s` netlist print | KEEP-PARSE-ONLY |
| cace | 2.13.0 (pip) | — | NATIVE: `pip install cace`, `import cace`. NOTE: dissection evidence at 2.5.6, ~8 minors behind pin — re-verify filenames/grammars before normalizer | YAML datasheet in/out (format 5.2) + JSON project file | KEEP-BINDINGS |
| openvaf | UNPINNED, not in lock | — | verilogae PyPI stale (May 2023, not Jan 2022 — dissection); openvaf-py experimental; Original-vs-Reloaded fork split | `--dump-json` is a DEAD FLAG at a9697ae (driver bails `currently unimplemented`); output is OSDI .so (build-id risk); exit-0-on-hard-failure bug | DEFER (pin fork+rev first) |
| pyspice | 1.5 locked | — (lib) | NATIVE: PyPI PySpice/1.5 (CFFI libngspice + netlist parser + raw→numpy) | raw parsers → numpy; Xyce netlist support | KEEP-BINDINGS |

### photonic-em

| tool | pin | adapter | bindings + evidence | structured escapes | MVP verdict |
|---|---|---|---|---|---|
| sax | 0.18.2 locked | sax | native Python (JAX S-params); JSON-envelope driver exists | in-API numpy/JAX arrays | KEEP-BINDINGS |
| circulax | 0.2.5 locked | circulax | native Python (JAX/Optimistix/Diffrax); driver exists | in-API arrays | KEEP-BINDINGS |
| meep | pymeep 1.35.0 (conda-forge) | — | official Python interface; install doc shows official pymeep wheels on PyPI (dissection correction — conda-only claim was wrong). PyPI bare `meep` 1.0.6 is still an unrelated task-runner SQUAT — never pip-install | HDF5 field dumps; in-API numpy via h5py | DEFER (unstaffed: provisioned, needs adapter+proof) |
| openems | v0.37.0 | — | official Python extension (`update_openEMS.sh --python`, isolated venv) | Touchstone .sNp, HDF5/VTK, CSX XML | DEFER (directive + post_mvp) |
| csxcad | v0.7.0 | — | official Python module (`pip install .` from CSXCAD/python) | .csx geometry XML | DEFER (post_mvp-only) |
| palace | UNSOURCED | — | NONE official (C++ binary, JSON config) | port-S.csv is mag-dB/phase-deg CSV, NOT Touchstone (dissection correction); palace.json run metadata; VTU; MFEM .gf; _resolved.json | DEFER (post_mvp + unsourced) |
| gmsh | UNPINNED | — | official `gmsh` PyPI wheel (`import gmsh`) | .msh mesh files, .geo scripts | DEFER (post_mvp-only; pin on adopt) |
| meow | meow-sim 0.15.0 locked | meow (deferred) | native Python EME (Tidy3D cloud excluded by no-cloud rule); adapter exists | in-API T/R/phase/modes | DEFER (unstaffed: locked + adapter exists, needs proof fixtures) |
| femwell | UNPINNED | — | native Python FEM (scikit-fem based) | in-API fields/modes | DEFER (post_mvp; pin on adopt) |
| meshwell | UNPINNED | — | native Python GMSH wrapper | returns gmsh meshes | DEFER (post_mvp-only) |
| scikit_fem | UNPINNED | — | pure-Python FEM assembly | sparse matrices/vectors | DEFER (post_mvp-only) |
| scikit_rf | 1.13.0 locked | — (lib) | native Python (`skrf.Network`, numpy FxNxN) | Touchstone I/O built in | KEEP-BINDINGS |
| gplugins | UNPINNED | — | native meta-package (femwell/meow/elmer/gmsh/sax plugins) | per-plugin | DEFER (post_mvp-only; EXCLUDE tidy3d cloud plugin) |
| elmer_fem | UNPINNED (PPA) | — | NONE official (ElmerSolver binaries + .sif); pyelmer = SIF writer only | VTU via ResultOutputSolve, SaveScalars .dat/JSON/CSV, convergence.dat | DEFER (unstaffed: ambient + file channels per dissection, needs adapter+proof) |
| devsim | 2.11.2 (pip) | — | native Python-scripted TCAD (devsim.solve/get_contact_charge/write_devices) | ParaView ASCII + restart format | DEFER (unstaffed: installed in venv, needs adapter+proof) |

### flow-infra

| tool | pin | adapter | bindings + evidence | structured escapes | MVP verdict |
|---|---|---|---|---|---|
| librelane | 3.0.17 (commit 64ef808) | digital_flow | NATIVE package (`import librelane`); pip route is flow-infra-only, bring-own-tools | run-dir layout (config.json, per-step reports, ODB, GDS/SPEF) | KEEP-BINDINGS |
| oss-cad-suite | 20261025 (bundle itself) | — | NONE as a bundle (tarball of binaries) | member structured outputs (write_json, SBY status, VCD/FST) | KEEP-STRUCTURED |
| cudd | 3.0.0 (build-only) | — | community repycudd only; no official binding | n/a (static lib inside OpenSTA build) | DEFER (build-only dep) |
| trilinos | 17-2-1 (build-only) | — | PyTrilinos deprecated (feedstock archived Jun 2026); PyTrilinos2 replaces | n/a (static lib inside Xyce build) | DEFER (build-only dep) |
| miniforge | UNPINNED latest URL | — | NONE (conda installer bootstrap) | determinism via env export, not bindings | DEFER (bootstrap; pin URL+checksum) |
| connectgraph | engine-owned | connectivity, view_sync | NATIVE — it IS Python (dicts, in-process, no parsing) | findings/netlists/net table as dicts | KEEP-BINDINGS |
| numpy | 2.5.4 locked | lib | NATIVE (IS the structured layer) | arrays | KEEP-BINDINGS |
| scipy | 1.18.1 locked | lib | NATIVE | — | KEEP-BINDINGS |
| pandas | 3.1.0 locked | lib | NATIVE | DataFrames; parquet/feather IO | KEEP-BINDINGS |
| matplotlib | 3.11.2 locked | lib | NATIVE | PNG/SVG export (Agg backend) | KEEP-BINDINGS |
| pint | UNPINNED, not in lock | lib | NATIVE (PyPI Pint 0.26.2, "Physical quantities module") | Quantity objects (kills unit-parsing) | KEEP-BINDINGS (pin+lock) |
| networkx | 3.7 locked | lib | NATIVE | graph objects; node-link JSON | KEEP-BINDINGS |
| pyvista | UNPINNED, not in lock | lib | NATIVE (PyPI pyvista 0.49.2, VTK-backed) | VTK/VTU/VTP; trimesh interop | KEEP-BINDINGS (pin+lock) |
| trimesh | 5.2.0 locked | lib | NATIVE | STL/GLB/OBJ IO | KEEP-BINDINGS |
| jax | 0.9.2 locked (CPU) | lib (circulax driver) | NATIVE (lock holds 0.9.2; latest 0.12.0.1) | arrays | KEEP-BINDINGS |
| vlsir | UNPINNED, not in lock | — | NATIVE (PyPI vlsir 7.0.0, protobuf schemas) | protobuf (binary + textproto) | KEEP-BINDINGS (pin+lock) |
| vlsirtools | UNPINNED, not in lock | — | NATIVE (PyPI vlsirtools 7.0.0, spice sim drivers) | SimResult protobuf / numpy dataclasses | KEEP-BINDINGS (pin+lock) |
| gtkwave | catalog viewer; provisioning EXCLUDED | — | NONE official; community READERS for its formats: pywellen (VCD/FST/GHW), PyVCD, FST libs | VCD (IEEE 1364) + FST via pywellen; never drive the viewer (headless rule) | KEEP-STRUCTURED |

## KEEP-PARSE-ONLY determinism cases

Pinned text scraping is allowed ONLY on these grammars. Every case:
pinned tool rev + golden good/bad fixtures + documented shape, and the
adapter never trusts the exit code alone.

1. magic DRC total + area regexes (adapters drc, extract_magic, verified
   vs 8.3.685). `Total DRC errors found: N` verdict line; per-rule area
   summaries; `exttospice finished` marker; ext2spice SPICE grammar
   (X-devices, w=/l=) stable for decades. Exits 0 even on broken cells,
   so the verdict always comes from the parse.
2. netgen verdict text (adapter lvs_netgen, expect Netgen 1.5). Exact
   lines `Circuits match uniquely.` / `Netlists do not match.` /
   `*** MISMATCH ***`, plus sectioned `Net:` / `Instance:` mismatch
   lists, stable since 1.5. Exits 0 on mismatch. Banner-probe guards
   the PyPI/apt `netgen` mesh-generator name collision.
3. ngspice raw ASCII (adapters ngspice, postlayout, cosim). `-r rawfile`
   with `SPICE_ASCIIRAWFILE` / `set filetype=ascii` (manual ch.16),
   `wrdata` ASCII tables, plus the adapter-generated `.control`
   (`let`/`print meas_*`) regexed as `meas_* = value`. Exit code is
   unreliable and ignored. Shared-lib/PySpice in-process binding is
   post-MVP.
4. xschem netlist print (no adapter yet). Pinned-rev batch
   `xschem -n -x -q -s` netlist is byte-deterministic (GUI-vs-batch
   diff is only redundant `m=1`); `.sch` C/N/T/L/B/A/P line grammar is
   manual-documented. Revisit pyxschem when it leaves WIP.
5. STA report text — RESIDUE, tool deferred. opensta stays deferred per
   directive, but the grammar is recorded for when it lands:
   `report_checks` (`Startpoint:`/`Endpoint:`/`Path Group:`/
   `Path Type: max|min`, `<slack> slack (MET|VIOLATED)`),
   `report_wns`/`report_tns` scalars, `Error:` lines fail the run.
   timing_sta already implements marker-delimited sections + requires
   all 4 WNS/TNS margins.

## Deferred list with reasons (26)

Re-triaged 2026-11-02 under the rule: defer iff unproven AND
heavy/unprovisioned. Implemented + provisioned physics is NOT deferred
as a tool — it is unstaffed (needs adapter + proof fixtures). See
`docs/tool-frontends-review.md`: only 12 of these 26 are frontends;
the other 14 are internals that ride with their frontend.

A. Directive + scope (8 — stay deferred): opensta, xyce, openems
(directive; STA-text/CSV/RAW grammars kept as residue for later);
nextpnr, icestorm, trellis, oxide, apicula (off_mvp FPGA scope).

B. Blocked on concrete cause (8): palace (unsourced — sourcing gates
any work); openvaf (unpinned + fork split; `--dump-json` dead at
a9697ae; compile.model ships without it until pinned); abc
(yosys-internal sub-pass, no standalone adapter ever); yices (stale
bindings); cvc4 (legacy); cudd + trilinos (build-only); miniforge
(bootstrap; pin URL+checksum).

C. Provisioned-but-unstaffed (4 — cheapest adapter wins, NOT tool
gaps): meep (pymeep 1.35.0 installed; in-API numpy + HDF5), devsim
(2.11.2 installed; native API), elmer_fem (ambient PPA; SaveScalars
JSON/CSV + VTU per dissection), meow (locked + adapter exists; needs
proof fixtures to activate).

D. Pin-and-go (6 — native bindings/files, needs pin + proof):
femwell, gmsh, meshwell, scikit_fem, gplugins (pin on adopt; EXCLUDE
tidy3d cloud plugin), csxcad (pin v0.7.0; provision standalone or
with openEMS).

Note: meow/femwell/meep also appear in workflow.photonic (mvp), but
their solver role is simulate.em (post_mvp); the workflow's MVP path
uses sax/circulax/gdsfactory/kfactory/klayout.

## What this means for demo-first MVP

Coherent dumps over forced v1 shapes. The MVP bar per adapter is a
coherent deterministic dump: bindings/structured reads preferred,
golden good+bad fixtures, documented shape — NOT strict ResultBundle
normalization (that moves to post-MVP under API-V1-CONFORMANCE).
Concretely: 41 kept tools read via bindings or machine grammars, 4 via
the pinned determinism cases above, and zero adapters ship on unpinned
text scraping (uranium-grade rule). The demo path runs
digital/analog/photonic/mixed fixtures end to end on dumps the audience
can inspect, while deferred groups A/B stay out of staffing until
scope opens and groups C/D wait only on adapters + proof (see
re-triage above and `docs/tools/` grammars).

## Gaps (weak evidence)

- amaranth: sim VCD details unverified this pass (ACTION: pin + verify).
- verilator: --xml-only vs --json-only flag against the bundle version
  unconfirmed; VCD/FST fallback is solid.
- cvc5: kept on official PyPI bindings but is a provision extra, not in
  the catalog and not consumed by any adapter today.
- palace: unsourced (no pin); sourcing per provision-sources §12 gates
  all work.
- openvaf: Original-vs-Reloaded fork choice + rev pin still open.
- Unpinned kept tools needing pin+lock: amaranth, pint, pyvista, vlsir,
  vlsirtools. Unpinned deferred tools pin on adopt: gmsh, femwell,
  meshwell, scikit_fem, gplugins, elmer_fem, miniforge (URL+checksum).
