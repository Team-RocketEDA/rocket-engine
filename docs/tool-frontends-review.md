# Tool frontends vs internals review

*Date: 2026-11-02 · Branch: GREEN-the-tests · Source: `docs/tool-bindings-audit.md` (71 rows). Review only; no audit/ticket edits.*

## Rule

- **FRONTEND**: a tool an agent or user invokes directly to do a design
  task. Own CLI/API entry point, own results, appears in the task
  catalog as a provider. This is the list we staff, provision, and
  count coverage against.
- **INTERNAL**: only ever touched *through* another tool. Solver
  engines, sub-passes, plugins, arch backends, chip DBs, bundled
  libraries, build-only deps, bootstrap, the bundle itself, plumbing
  libs, engine-owned code, excluded viewers. Nobody runs these
  standalone for a design task (e.g. nobody runs `abc` without yosys).

## Counts

71 audited rows = **36 frontends + 35 internals**.

Internals by kind (35): SMT engines 6 · sub-pass/plugin 2 ·
arch-backend/chipdb 4 · bundled lib 8 · build-only 2 ·
bootstrap/dist/viewer 3 · plumbing 9 · engine-owned 1.

## Frontends (36) with adapter coverage

`+` = adapter exists today (14) · `·` = provider gap, no adapter (22).

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
| 12 | openroad (standalone) | · (flow-internal via librelane only) |
| 13 | opensta | + timing_sta (deferred per directive) |
| 14 | openrcx | · (usually flow-driven; own SPEF results) |
| 15 | magic | + drc, extract_magic |
| 16 | netgen | + lvs_netgen |
| 17 | klayout | + drc_kl |
| 18 | gdsfactory | + gdsfactory |
| 19 | kfactory | · |
| 20 | ngspice | + ngspice, postlayout, cosim |
| 21 | xyce | · (deferred per directive) |
| 22 | xschem | · |
| 23 | cace | · |
| 24 | openvaf | · (deferred: unpinned + fork split) |
| 25 | sax | + sax |
| 26 | circulax | + circulax |
| 27 | meep | · |
| 28 | openems | · (deferred per directive) |
| 29 | palace | · (deferred: unsourced) |
| 30 | gmsh | · |
| 31 | meow | + meow (task-scope deferred, tool ready) |
| 32 | femwell | · |
| 33 | elmer_fem | · |
| 34 | devsim | · |
| 35 | librelane | + digital_flow |
| 36 | vlsirtools | · (sim drivers; the schema `vlsir` is internal) |

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

## Borderline calls (recorded, disputable)

- **openrcx → FRONTEND.** Own binary, own SPEF results; usually
  flow-driven but invocable and verifiable standalone.
- **vlsir → INTERNAL / vlsirtools → FRONTEND.** The schema is a data
  format; the sim drivers run tools and are the frontend.
- **scikit_rf → INTERNAL.** Compute/IO lib (Touchstone, Network math),
  not a solver; used inside adapters, never "run" as a design step.
- **slang → FRONTEND.** A library too, but its lint driver is invoked
  directly with own diagnostics.
- **yosys_slang → INTERNAL.** A yosys plugin; results inherit yosys
  channels. (Dissection report still useful for `read_slang` behavior.)

## Consequences

1. **Coverage metric is 14/36 frontends**, not "19 adapters over 71
   tools". The 22 gaps are the real adapter-build backlog.
2. **Provider-gap list needs a rewrite**, not just additions: drop
   `vlsir` (schema) and `yosys_slang` (plugin) from the gap list, add
   `cocotb`, `gmsh`, `vlsirtools`. Net: 22 gaps.
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
5. Pending: per-tool dissection (`docs/tools/`, running) covers the
   disputed frontends; re-triage deferred + provider gaps then, per
   the provisioned-but-unstaffed rule.
