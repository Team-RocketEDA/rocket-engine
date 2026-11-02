# Tool matrix double-check (synthesis)

*Date: 2026-11-02 · Branch: GREEN-the-tests · Prior: `docs/tool-frontends-review.md` (34F + 36I + 1D, 71 rows). This doc is a PROPOSAL — no verdicts applied.*

*Method: five review-only researchers double-checked the matrix group by
group against live provision scripts, lockfiles, bundle listings, and
adapter sources. All 10 researcher refs (text + summary × 5 groups)
read fully — zero MISSING. This agent owns all synthesis writes.*

*Outcome: 69 roles CONFIRMED, 2 CHALLENGED (both FRONTEND → INTERNAL).
Primary provisioning: 47 AUTO, 23 MANUAL, 1 none (DEAD). Redundancy
cuts proposed: 1.*

## (a) Per-tool table — all 71 rows

Role legend: CONFIRM = prior role holds · **CHALLENGE** = change proposed
(see §b). AUTO = covered by `install.sh` / `provision_toolchain.sh`
(bundle fetch, source-build recipe, or default `uv sync`).
MANUAL = needs an extra step (group sync, unpinned install, ambient
host dep, or no recipe at all).

### digital-rtl (23) — all CONFIRMED, all AUTO primary

| tool | prior → recheck | runtime bins + source (AUTO/MANUAL) | redundancy |
|---|---|---|---|
| yosys | FRONTEND CONFIRM | `yosys`, `yosys-abc`, `yosys-smtbmc`, `yosys-witness` — bundle manifest `yosys` pkg. AUTO (pin 20261025, banner-asserted) | UNIQUE — RTL synth + RTLIL hub |
| abc | INTERNAL CONFIRM | none standalone (`yosys-abc` only, no `abc` bin) — driven via yosys pass. AUTO (rides bundle) | Owned by yosys; no catalog role |
| slang | FRONTEND CONFIRM | `slang`, `slang-hier`, `slang-reflect`, `slang-tidy` — manifest `yosys` pkg. AUTO | UNIQUE — full IEEE-1800 lint w/ diagnostics |
| yosys_slang | INTERNAL CONFIRM | none (share/yosys/plugins/slang.so, `read_slang`). AUTO | Owned by yosys |
| sby | FRONTEND CONFIRM | `sby` + aiger suite + solvers (`yosys` runtime dep). AUTO | UNIQUE — property/formal orchestration |
| eqy | FRONTEND CONFIRM | `eqy`, `imctk-eqy-engine`, eqy_*.so (needs yosys+sby). AUTO | UNIQUE — partitioned combinational equiv |
| mcy | FRONTEND CONFIRM | `mcy`, `mcy-dash` (needs yosys+iverilog+sby). AUTO | UNIQUE — mutation coverage |
| z3 | INTERNAL CONFIRM | `z3` — manifest `z3`. AUTO | Mutual substitute w/ 5 engines under sby; kept, not cut |
| boolector | INTERNAL CONFIRM | `boolector`, `btormc`, `btorsim`. AUTO | Same as z3 |
| bitwuzla | INTERNAL CONFIRM | `bitwuzla` (eqy default partition engine). AUTO | Same as z3 |
| yices | INTERNAL CONFIRM | `yices`, `yices-sat`, `yices-smt`, `yices-smt2`. AUTO | Same as z3 |
| cvc4 | INTERNAL CONFIRM | `cvc4` (legacy upstream, ships+works → NOT dead). AUTO | Same as z3 |
| cvc5 | INTERNAL CONFIRM | `cvc5`. AUTO | Same as z3 |
| icarus | FRONTEND CONFIRM | `iverilog`, `vvp`, `iverilog-vpi`. AUTO | UNIQUE — zero-build interpreted Verilog loop |
| verilator | FRONTEND CONFIRM | `verilator`, `verilator_bin[_dbg]`, `verilator_coverage*` + share. AUTO. MANUAL secondary: ambient gcc+make for `--build` (no bundle C toolchain) | UNIQUE — compiled-cycle sim + SARIF + coverage |
| ghdl | FRONTEND CONFIRM | `ghdl`, `ghdl1-llvm`, `ghwdump`. AUTO. MANUAL secondary: ambient gcc for elaboration/linking | UNIQUE — only VHDL |
| cocotb | FRONTEND CONFIRM | `cocotb-config` + egg (bundle) AND uv.lock cocotb 2.1.0 (pip). AUTO. MANUAL secondary: ambient make for sim builds | UNIQUE — Python/coroutine testbench |
| nextpnr | FRONTEND CONFIRM (off_mvp) | 6× `nextpnr-<arch>` + chipdbs. AUTO | UNIQUE — only FPGA P&R |
| icestorm | INTERNAL CONFIRM | `icepack`, `iceprog`, `icetime`, `iceunpack`, `icebox_*` — manifest `icestorm`. AUTO. Borderline kept: nextpnr-exclusive formats, no standalone task; promote iff bitstream task staffed | UNIQUE per arch (iCE40) |
| trellis | INTERNAL CONFIRM | `ecppack`, `ecpunpack`, `ecppll`, (+`ecpprog`, `ecpdap` on box). AUTO | UNIQUE per arch (ECP5) |
| oxide | INTERNAL CONFIRM | `prjoxide` — manifest `prjoxide`. AUTO | UNIQUE per arch (Nexus) |
| apicula | INTERNAL CONFIRM | `gowin_pack`, `gowin_unpack`, `gowin_pll` + apycula. AUTO | UNIQUE per arch (Gowin) |
| amaranth | FRONTEND CONFIRM | `amaranth-rpc` + site-packages amaranth 0.6.0.dev140 (manifest `pyhdl`). AUTO via bundle. GAP: zero uv.lock hits — UNPINNED for engine venv | UNIQUE — Python-RTL design+sim+vendor-build |

### physical (10) — 9 CONFIRMED, 1 CHALLENGE

| tool | prior → recheck | runtime bins + source (AUTO/MANUAL) | redundancy |
|---|---|---|---|
| openroad | INTERNAL CONFIRM (flow-engine) | `openroad` inside LibreLane closure only (zero provisioner mentions; arrives via AppImage/nix-eda). AUTO-via-librelane, devshell-only. Python wheel MANUAL/unprovisioned (`openroad -python` now hard error) | UNIQUE P&R/CTS/router engine; agent access via librelane only |
| opendb | INTERNAL CONFIRM (bundled lib) | none (`import odb` inside wheel env only). AUTO (rides closure) | UNIQUE .odb reader |
| opensta | FRONTEND CONFIRM (deferred) | `sta` — source build install_opensta + CUDD. AUTO recipe. BOX: prefix empty, no `sta` on PATH → rebuild needed | UNIQUE standalone STA |
| openrcx | DEAD CONFIRM | none (clone 2020, absorbed into OpenROAD) | Superseded by openroad SPEF extract |
| magic | FRONTEND CONFIRM | `magic` — source-build recipe. AUTO. BOX: ambient 8.3.685 (MANUAL provenance, accepted family) | UNIQUE extraction; DRC overlaps klayout |
| netgen | FRONTEND CONFIRM | `netgen` — source-build recipe. AUTO (`-batch` verified; bare `-h` needs Tk/display) | UNIQUE wired LVS |
| klayout | FRONTEND CONFIRM | `klayout` — .deb-extract recipe. AUTO. BOX: pinned 0.30.12 OK; ambient 0.28.16 MISMATCH. Python via locked wheel 0.30.12, AUTO | UNIQUE .lyrdb DRC, layout-xor, GDS/OASIS I/O |
| gdsfactory | FRONTEND CONFIRM | none (pure Python; locked 9.51.0). AUTO via install.sh | UNIQUE PCell/routing framework; strictly easier than kfactory |
| kfactory | **CHALLENGE FRONTEND → INTERNAL** | none used (`kf` CLI never invoked). AUTO (transitive via gdsfactory, locked 3.0.4) | COVERED by gdsfactory — CUT PROPOSED |
| librelane | FRONTEND CONFIRM | `librelane` + closure + `ciel` — AppImage recipe. AUTO. MANUAL: binary not on PATH (devshell/shim/PATH step missing) | UNIQUE RTL-to-GDS orchestrator |

### analog (6) — all CONFIRMED (4 AUTO, 2 MANUAL)

| tool | prior → recheck | runtime bins + source (AUTO/MANUAL) | redundancy |
|---|---|---|---|
| ngspice | FRONTEND CONFIRM | `ngspice` — SourceForge rework-47 build. AUTO (ambient 4* family also accepted; ngspice-42 on PATH) | UNIQUE-as-primary — only staffed SPICE sim |
| xyce | FRONTEND CONFIRM (deferred) | `Xyce` (capital) — Release-7.10.0 + Trilinos source build. AUTO in principle. BOX: prefix dir EMPTY | UNIQUE parallel sim + HB/PCE/SENS/MPDE/TRADJ + Touchstone; basic TRAN/DC/AC easier via ngspice |
| xschem | FRONTEND CONFIRM | `xschem` + `rawtovcd` (both installed). AUTO. MANUAL secondary: tclsh/wish + X libs (host prereqs, apt) | UNIQUE schematic-capture frontend |
| cace | FRONTEND CONFIRM | `cace` (pip entry; needs xschem/magic/netgen/ngspice on PATH). AUTO-VIA-SCRIPT-ONLY: `uv pip install cace==2.13.0`, zero uv.lock entries — plain `uv sync` never installs it. BOX: missing | UNIQUE spec-driven characterization/datasheet flow |
| openvaf | FRONTEND CONFIRM (deferred) | `openvaf` (reloaded fork renames to `openvaf-r`). MANUAL: zero provision footprint, unpinned, not in lock. BOX: missing | UNIQUE Verilog-A→OSDI compiler |
| pyspice | INTERNAL CONFIRM (bundled lib) | none (Python lib). MANUAL in practice: analog group opt-in, not in venv; libngspice.so exists NOWHERE (provision builds binary only, no --with-ngshared) | Unique CFFI driver + raw→numpy; sim half unrunnable today, parse-only works |

### photonic-em (15) — 14 CONFIRMED, 1 CHALLENGE (5 AUTO, 10 MANUAL)

| tool | prior → recheck | runtime bins + source (AUTO/MANUAL) | redundancy |
|---|---|---|---|
| sax | FRONTEND CONFIRM | none (pure Python; sax 0.18.2/jax locked). MANUAL: needs `uv sync --group photonic` (install.sh syncs dev only) | UNIQUE freq-domain photonic compact-model solver |
| circulax | FRONTEND CONFIRM | none (circulax 0.2.5/jax/diffrax/optimistix/kfnetlist locked). MANUAL: same group sync | UNIQUE JAX time-domain/mixed-signal sim |
| meep | FRONTEND CONFIRM | conda-env `python` + `meep` binary. AUTO via install_pymeep (miniforge + pymeep 1.35.0). BOX: env python MISSING (pkgs cache only) | UNIQUE nanophotonic FDTD w/ in-API Harminv/LDOS/flux |
| openems | FRONTEND CONFIRM | `openEMS`, `nf2ff` — source build CSXCAD+v0.37.0. AUTO. BOX: present and verified | UNIQUE EC-FDTD w/ ports/SAR/nf2ff |
| csxcad | INTERNAL CONFIRM | none standalone (C++ lib + Cython ext in openEMS prefix). AUTO (rides build) | Rides openems |
| palace | FRONTEND CONFIRM (deferred: unsourced) | `palace`. MANUAL: no pin/recipe anywhere; user builds. Upstream alive → NOT dead | UNIQUE 3D full-wave FEM eigenmode/driven + statics + ROM |
| gmsh | **CHALLENGE FRONTEND → INTERNAL** (mesh backend) | `gmsh` bin and/or wheel. MANUAL: no recipe anywhere (provisioner, groups, lock, catalogue all absent). BOX: absent | INTERNAL mesh backend; no other mesher in matrix |
| meow | FRONTEND CONFIRM | none (meow-sim 0.15.0 + tidy3d LOCAL + sax, locked). MANUAL: group sync. No-cloud rule constrains `tidy3d.web` only | UNIQUE EME propagator + local-FDE modes |
| femwell | FRONTEND CONFIRM | none (`compute_modes` API). MANUAL, fully unpinned: absent from lock/groups/provisioner/catalogue (needs scikit-fem, gmsh wheel, meshwell, pygmsh) | UNIQUE vectorial FEM waveguide modes + 2D multiphysics |
| meshwell | INTERNAL CONFIRM | none (gmsh wrapper). MANUAL unpinned | Rides femwell/gmsh |
| scikit_fem | INTERNAL CONFIRM | none (FEM assembly via femwell). MANUAL unpinned | Rides femwell |
| scikit_rf | INTERNAL CONFIRM (borderline stands) | none (scikit-rf 1.13.0 locked). MANUAL: `uv sync --group analog` | UNIQUE RF math/Touchstone lib; INTERNAL by invocation shape |
| gplugins | INTERNAL CONFIRM | none (meta-package + extras). MANUAL unpinned; tidy3d extras under same local-only rule | Umbrella over backends, never standalone |
| elmer_fem | FRONTEND CONFIRM | `ElmerSolver` + `ElmerGrid` — CSC PPA apt. AUTO-modulo-sudo. BOX: bare `ElmerSolver` ABSENT (only Grid + _mpi) → check fails | UNIQUE 3D thermal/multiphysics FEM |
| devsim | FRONTEND CONFIRM | none (C-extension `import devsim` 2.11.2 via provision `uv pip install`). AUTO, outside uv.lock | UNIQUE TCAD device solver w/ circuits |

### infra-libs (17) — all CONFIRMED (6 AUTO, 11 MANUAL)

| tool | prior → recheck | runtime bins + source (AUTO/MANUAL) | redundancy |
|---|---|---|---|
| oss-cad-suite | INTERNAL CONFIRM (bundle, not a tool) | n/a — IS the bin provider (155 bins verified). AUTO (pinned tarball) | UNIQUE distribution role |
| cudd | INTERNAL CONFIRM (build-only) | none (static lib in sta build). AUTO with opensta | UNIQUE BDD backend for STA |
| trilinos | INTERNAL CONFIRM (build-only) | none runtime (bin/ holds kokkos wrappers only). AUTO with xyce | UNIQUE Xyce linear-algebra backend |
| miniforge | INTERNAL CONFIRM (bootstrap) | conda binary, bootstrap-time only. AUTO. GAP: URL still `latest`, unpinned, no checksum | UNIQUE-as-provisioned; pip-pymeep route could obsolete (unverified) |
| connectgraph | INTERNAL CONFIRM (engine-owned) | none (stdlib-only, in-process). AUTO (ships in src/) | UNIQUE net-name authority + ERC; networkx is adjacency, not redundancy |
| numpy | INTERNAL CONFIRM (plumbing) | none (locked 2.5.4). MANUAL: group opt-in only | UNIQUE numeric base |
| scipy | INTERNAL CONFIRM | none (locked 1.18.1). MANUAL. BOX: absent | UNIQUE sparse/optimize/signal |
| pandas | INTERNAL CONFIRM | none (locked 3.1.0). MANUAL. BOX: absent | UNIQUE DataFrames/parquet |
| matplotlib | INTERNAL CONFIRM | none (locked 3.11.2). MANUAL | UNIQUE plotting path |
| pint | INTERNAL CONFIRM | none. MANUAL ONLY: no lock, no venv, no pyproject/provision entry (triple-absent) | UNIQUE unit-safe quantities |
| networkx | INTERNAL CONFIRM | none (locked 3.7). MANUAL. BOX: absent | UNIQUE graph algorithms |
| pyvista | INTERNAL CONFIRM | none. MANUAL ONLY: triple-absent like pint | UNIQUE VTK rendering path |
| trimesh | INTERNAL CONFIRM | none (locked 5.2.0). MANUAL. BOX: absent | UNIQUE mesh file IO |
| jax | INTERNAL CONFIRM | none (locked 0.9.2 CPU). MANUAL. BOX: absent | UNIQUE autodiff/JIT arrays |
| vlsir | INTERNAL CONFIRM (schema) | none. MANUAL ONLY: needs pip vlsir==7.0.0 + lock action open | UNIQUE circuit protobuf schema |
| vlsirtools | FRONTEND CONFIRM | none own; needs sim backends on PATH for live sim. MANUAL: pip 7.0.0, not in lock/venv | UNIQUE Package→netlist + unified SimResult; plain sims easier via ngspice/xyce directly |
| gtkwave | INTERNAL CONFIRM (excluded viewer) | `gtkwave` ships in bundle (AUTO as file) but NEVER an engine dep by headless policy. NOT dead (usable upstream) | Viewer role intentionally uncovered (`surfer` equally excluded) |

## (b) VERDICT CHANGES PROPOSED vs docs/tool-frontends-review.md

None applied — this doc is the proposal.

1. **kfactory: FRONTEND (#17) → INTERNAL.** Zero `import kfactory`
   in src/tests; arrives only as gdsfactory's dependency (locked
   3.0.4, transitive); no adapter; tasks.json lists it but nothing
   wires it. Same engine-centric logic as the openroad demotion:
   upstream entry points exist, but in-engine every result surfaces
   through gdsfactory. Caveat: keep FRONTEND only if the group counts
   upstream entry points rather than in-engine wiring.
2. **gmsh: FRONTEND (#28) → INTERNAL (mesh backend).** Only one of
   34 frontends that is NEVER a task provider (tools[]-only, same
   catalog position as internals csxcad/meshwell/scikit_fem/gplugins);
   no task outputs a mesh; consumed THROUGH solver drivers (femwell
   requires it, devsim parses it, ElmerGrid converts it, palace reads
   it); no adapter shape exists. Dissent: re-promote iff engine adds
   a standalone mesh/inspect step with mesh outputs.

If both accepted: 34F + 36I + 1D → **32F + 38I + 1D**; coverage
14/34 → **14/32** (neither has an adapter); provider-gap list
20 → **18** (drop kfactory, gmsh); frontend-deferred 12 → **11**
(drop gmsh).

Explicitly NOT proposed (genuine challenge attempts, priors stand):
abc stays INTERNAL (no `abc` binary, only `yosys-abc`); arch packers
stay INTERNAL (promotion condition recorded: staff a bitstream task);
cvc4 stays INTERNAL (ships+works, not DEAD); openvaf stays FRONTEND
(reloaded fork active, not DEAD); palace stays FRONTEND (upstream
alive, unsourced ≠ dead); scikit_rf stays INTERNAL (borderline
stands); gtkwave stays INTERNAL (usable upstream, excluded by
headless policy, not DEAD).

Doc errata found (not verdict changes): review header says
"Internals (35)" but kind table counts 36; provision-sources.md §1
"Covers" omits amaranth (ships in bundle); audit verilator row cites
dead `--xml-only` (only `--json-only` exists since 5.046).

## (c) PROVISION GAPS — binaries needed but MANUAL

No recipe at all: `openvaf`/`openvaf-r` (unpinned, fork split);
`palace` (unsourced); `gmsh` bin/wheel (absent from provisioner,
groups, lock, catalogue — still needs a recipe as INTERNAL mesh
backend); femwell stack (femwell, meshwell, scikit-fem, gmsh wheel,
pygmsh, meshio — fully unpinned); gplugins[extras] (unpinned);
pint, pyvista, vlsir, vlsirtools (triple-absent: no lock, no venv,
no provision entry).

Lock-pinned but opt-in group sync (install.sh syncs dev only):
sax, circulax, meow (`--group photonic`); PySpice, scikit-rf
(`--group analog`); numpy, scipy, pandas, matplotlib, networkx,
trimesh, jax (group opt-in; scipy/pandas/networkx/trimesh/jax
absent from current venv).

Provision-script-only (bypasses uv.lock, plain `uv sync` misses):
cace 2.13.0 (`uv pip install`, zero lock entries); devsim 2.11.2
(same pattern).

Ambient host deps the provisioner never installs: gcc+make for
verilator `--build`, ghdl elaboration, cocotb sim builds (bundle
has no C toolchain); tclsh/wish + X libs for xschem; libngspice.so
exists nowhere (provision builds the ngspice binary only,
no --with-ngshared) so the PySpice CFFI sim path is unrunnable —
analog sim is parse-only end to end today.

Resolvability gaps on AUTO recipes: `librelane` not on PATH
(devshell/shim/PATH step missing); openroad Python wheel
Bazel-only/unprovisioned; miniforge URL still `latest` (unpinned,
no checksum); amaranth unpinned for engine venv (bundle-only).

Box-state gaps (AUTO recipe exists, artifact absent): opensta
prefix empty; xyce prefix dir empty; pymeep conda env missing
(pkgs cache only — openEMS is today's runnable FDTD); bare
`ElmerSolver` absent (only Grid + _mpi → provision check fails);
ambient klayout 0.28.16 mismatches pinned 0.30.12.

## (d) REDUNDANCY CUTS PROPOSED

One cut: **kfactory** — no unique in-engine use; every result
reaches the engine through gdsfactory (PCells + routing + netlists
atop the same KCell backend), which is strictly easier. Demote to
INTERNAL; gap if ever needed directly: KCell/DKCell + .l2n helpers
for non-gdsfactory flows (currently unused).

Deliberately not cut: 6 SMT engines (mutual substitutes under sby,
kept as selectable backends — bitwuzla most load-bearing via eqy
default template); xyce vs ngspice (overlap on basic sims, but xyce
alone has parallel/HB/PCE/SENS/MPDE/TRADJ — deferred, not dead);
magic vs klayout DRC (klayout unwired for LVS; magic alone does
extraction); sax vs circulax (freq-domain vs time-domain —
complementary); meep vs openEMS (different FDTD schools, different
result shapes); meow vs femwell modes (FDM vs FEM, EME uncovered
elsewhere); gplugins umbrella (never standalone, kept as
meta-package); connectgraph vs networkx (different jobs — schematic
net authority vs graph math; connectgraph is stdlib-only and does
not import networkx); gtkwave/surfer (viewer role intentionally
uncovered by headless policy).

## (e) Weak-evidence gaps

- cace output evidence verified at clone 2.5.6, ~8 minors behind
  the 2.13.0 pin — re-verify grammars at pin before staffing a
  normalizer. cace also absent from venv on the recheck box.
- openvaf fork pin must name fork + rev + OSDI minor together
  (binary `openvaf` vs `openvaf-r`; ngspice ≤42 accepts OSDI 0.3
  only — matches the 2023 clone lineage, constrains the pin).
- kfactory/gmsh demotions rest on in-engine wiring, not upstream
  capability — both have real CLIs/APIs a human could drive.
- miniforge: audit claims official PyPI pymeep wheels exist
  (conda-only claim was wrong) — unverified; one spike could
  obsolete the conda bootstrap before pinning a conda URL.
- meow hard-requires the tidy3d PACKAGE (non-optional dep);
  no-cloud compliance rests on never touching `tidy3d.web`
  (local FDE path proven in driver + check_no_cloud.py).
- Stale bundle metadata: `amaranth-0.5.10.dist-info` alongside
  active 0.6.0.dev140; trellis bin/ has `ecpprog`/`ecpdap` beyond
  the manifest files list — cosmetic, unverified against upstream.
- All box-state findings (empty prefixes, missing envs, ambient
  versions) are single-box probes on the recheck host, not CI truth.
