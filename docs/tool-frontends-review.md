# Tool frontends vs internals review

*Date: 2026-11-02 · Branch: GREEN-the-tests · Source: `docs/tool-bindings-audit.md` (71 rows). Re-triaged 2026-11-02: openroad demoted (LibreLane-internal engine), openrcx struck (dead upstream).*

## Rule

- **TOOL == FRONTEND (repo definition).** In this repository the word
  "tool" means exactly a frontend: something an agent or user invokes
  directly to do a design task. Own CLI/API entry point, own results,
  appears in the task catalog as a provider. This is the list we
  staff, provision, and count coverage against. Anything else is an
  internal, a dead row, or a library — never called a tool.
- **INTERNAL**: only ever touched *through* another tool. Solver
  engines, sub-passes, plugins, arch backends, chip DBs, bundled
  libraries, build-only deps, bootstrap, the bundle itself, plumbing
  libs, engine-owned code, excluded viewers. Nobody runs these
  standalone for a design task (e.g. nobody runs `abc` without yosys).

## Counts

71 audited rows = **34 frontends + 36 internals + 1 dead**
(openrcx, struck — see below).

Internals by kind (36): SMT engines 6 · sub-pass/plugin 2 ·
arch-backend/chipdb 4 · bundled lib 8 · build-only 2 ·
bootstrap/dist/viewer 3 · plumbing 9 · engine-owned 1 ·
flow-engine 1 (openroad — results surface through LibreLane).

## Frontends (34) with adapter coverage

`+` = adapter exists today (14) · `·` = provider gap, no adapter (20).

| # | frontend | adapter today |
|---|---|---|
| 1 | yosys | + synth_yosys |
| 2 | slang | + syntax |
| 3 | sby | + formal_sby |
| 4 | eqy | · |
| 5 | mcy | · |
| 6 | icarus | + hdl_sim, cosim |
| 7 | verilator | · |
| 8 | ghdl | · |
| 9 | cocotb | · |
| 10 | nextpnr | · (off_mvp FPGA scope) |
| 11 | amaranth | · |
| 12 | opensta | + timing_sta (deferred per directive) |
| 13 | magic | + drc, extract_magic |
| 14 | netgen | + lvs_netgen |
| 15 | klayout | + drc_kl |
| 16 | gdsfactory | + gdsfactory |
| 17 | kfactory | · |
| 18 | ngspice | + ngspice, postlayout, cosim |
| 19 | xyce | · (deferred per directive) |
| 20 | xschem | · |
| 21 | cace | · |
| 22 | openvaf | · (deferred: unpinned + fork split) |
| 23 | sax | + sax |
| 24 | circulax | + circulax |
| 25 | meep | · |
| 26 | openems | · (deferred per directive) |
| 27 | palace | · (deferred: unsourced) |
| 28 | gmsh | · |
| 29 | meow | + meow (task-scope deferred, tool ready) |
| 30 | femwell | · |
| 31 | elmer_fem | · |
| 32 | devsim | · |
| 33 | librelane | + digital_flow (the physical frontend; see `docs/tools/librelane.md`) |
| 34 | vlsirtools | · (sim drivers; the schema `vlsir` is internal) |

## Internals (35) by kind

| kind | members |
|---|---|
| smt-engine (6) | z3, boolector, bitwuzla, yices, cvc4, cvc5 — sby/eqy backends via SMT-LIB2, never direct |
| sub-pass/plugin (2) | abc (yosys `abc` pass), yosys_slang (`read_slang` plugin) |
| arch-backend/chipdb (4) | icestorm, trellis, oxide, apicula — nextpnr arch data |
| bundled lib (8) | opendb (`import odb` only inside `openroad -python`), csxcad (openEMS geometry), pyspice (ngspice reader lib), meshwell (gmsh wrapper), scikit_fem (FEM assembly), scikit_rf (Touchstone/RF compute lib), gplugins (meta-package), vlsir (protobuf schema; drivers live in vlsirtools) |
| build-only (2) | cudd, trilinos |
| bootstrap/dist/viewer (3) | miniforge, oss-cad-suite (the bundle, not a tool), gtkwave (excluded; only VCD/FST formats matter) |
| plumbing (9) | numpy, scipy, pandas, matplotlib, pint, networkx, pyvista, trimesh, jax |
| engine-owned (1) | connectgraph (is engine code, not a tool) |
| flow-engine (1) | openroad — LibreLane-internal engine; all results surface through LibreLane run dirs + `-metrics` JSON (see `docs/tools/librelane.md` + `docs/tools/openroad.md` as grammar reference) |

DEAD, struck from both lists (1): ~~openrcx~~ — standalone repo
dead since 2020, absorbed into OpenROAD `src/rcx`. No provisioning,
no staffing, no row. SPEF grammar knowledge lives with
openroad/librelane.

## Borderline calls (recorded, disputable)

- **openroad → INTERNAL (flow-engine).** Demoted 2026-11-02: every
  result surfaces through LibreLane run dirs (`state_out.json`,
  `metrics.csv`, views) or `-metrics` JSON. The single-step Tcl
  escape hatch does not earn frontend status; no standalone
  adapter will be staffed.
- **~~openrcx~~ → DEAD.** Struck 2026-11-02: standalone repo dead
  since 2020, absorbed into OpenROAD `src/rcx`. Earlier
  FRONTEND call was wrong; a dead repo cannot be a tool.
- **vlsir → INTERNAL / vlsirtools → FRONTEND.** The schema is a data
  format; the sim drivers run tools and are the frontend.
- **scikit_rf → INTERNAL.** Compute/IO lib (Touchstone, Network math),
  not a solver; used inside adapters, never "run" as a design step.
- **slang → FRONTEND.** A library too, but its lint driver is invoked
  directly with own diagnostics.
- **yosys_slang → INTERNAL.** A yosys plugin; results inherit yosys
  channels. (Dissection report still useful for `read_slang` behavior.)

## Consequences

1. **Coverage metric is 14/34 frontends**, not "19 adapters over 71
   tools". The 20 gaps are the real adapter-build backlog.
2. **Provider-gap list needs a rewrite**, not just additions: drop
   `vlsir` (schema), `yosys_slang` (plugin), `openroad` (LibreLane-
   internal), `openrcx` (dead) from the gap list; add `cocotb`,
   `gmsh`, `vlsirtools`. Net: 20 gaps (eqy, mcy, verilator, ghdl,
   cocotb, nextpnr, amaranth, kfactory, xyce, xschem, cace, openvaf,
   meep, openems, palace, gmsh, femwell, elmer_fem, devsim,
   vlsirtools).
3. **Deferred list needs the same split.** Of 26 deferred, only 15 are
   frontends (opensta, xyce, openems, meep, palace, gmsh, meow,
   femwell, devsim, nextpnr, openvaf, elmer_fem + csxcad? no —
   csxcad is internal). Recount: frontend-deferred =
   opensta, xyce, openems, meep, palace, gmsh, meow, femwell,
   devsim, nextpnr, openvaf, elmer_fem (12); the other 14 deferred
   rows are internals that should never have read as tool gaps
   (abc, yices, cvc4, icestorm, trellis, oxide, apicula, csxcad,
   meshwell, scikit_fem, gplugins, cudd, trilinos, miniforge).
4. **Provisioning follows frontends.** SMT engines, chip DBs, and
   build libs ride along with their frontend (bundle, flow closure,
   or pip transitive) and need no per-tool provision story.
5. Done 2026-11-02: per-tool dissection (`docs/tools/`, 21 reports)
   landed; deferred re-triaged per the provisioned-but-unstaffed
   rule; LibreLane run-dir shapes documented in
   `docs/tools/librelane.md` (clone == pin 3.0.17 @ 64ef8080).
   Remaining: rewrite the API-V1-ADAPTERS provider-gap list to the
   20 above.
