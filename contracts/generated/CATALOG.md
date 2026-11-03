# Generated v1 API catalog

Generated from engine-v1.schema.json; runtime qualification is separate.

| Method | Job | HTTP |
|---|---|---|
| `describe` | Inspect methods, tasks, tools, entity schemas, templates and requirements. | `GET /api/v1/catalog` |
| `query` | Read any registered project, PDK, library, hierarchy, package or evidence catalog. | `POST /api/v1/queries` |
| `edit` | Commit atomic editor/project changes with typed entities and per-entity CAS. | `POST /api/v1/edits` |
| `run` | Start workflows or individual tool tasks and control unfinished runs. | `POST /api/v1/runs` |
| `script` | Execute full prepared Python/library APIs with managed project publication. | `POST /api/v1/executions` |
| `watch` | Read or stream ordered events including edits, results and capacity transitions. | `GET /api/v1/events` |

## Tool tasks

Every task below has a closed options schema. Registration does not claim installed/qualified support.

| Task | Purpose | Providers/backends |
|---|---|---|
| `workflow.asic` | Run a pinned ASIC implementation and verification plan; completion requires every applicable configured check and complete evidence. | librelane |
| `workflow.analog` | Generate/netlist, simulate, characterize, verify physical views, and optionally compare extracted behavior according to the saved plan. | ngspice, xyce, cace, magic, netgen, klayout, xschem |
| `workflow.photonic` | Run a saved photonic construction, circuit response, geometry verification, and qualified device-solver plan. | gdsfactory, kfactory, sax, circulax, klayout, meow, femwell, meep |
| `check.syntax` | Parse and lint the selected source language and supported language subset. | slang, yosys_slang, verilator, ghdl, icarus |
| `check.connectivity` | Check canonical circuit connectivity and interface mappings. | connectgraph |
| `check.erc` | Apply electrical rules to circuit participants and declared electrical semantics. | connectgraph |
| `check.drc` | Check physical geometry against the selected pinned technology rule deck. | magic, klayout |
| `check.lvs` | Compare independently selected layout extraction and reference circuit netlists. | netgen, klayout |
| `check.antenna` | Check process antenna ratios and routing antenna properties. | openroad, opendb, klayout |
| `check.view_sync` | Compare selected source/native/extracted views using canonical identity and pin mappings. | connectgraph, gdsfactory, kfactory |
| `check.layout_xor` | Compare two layout stream-outs using geometric XOR. | klayout |
| `check.formal` | Prove, bound, or cover formal properties, preserving assumptions, bounds, solver status, and counterexamples. | sby, yosys, abc, z3, boolector, bitwuzla, yices |
| `check.equivalence` | Compare golden and candidate implementations under explicit mapping and assumptions. | eqy, yosys, abc |
| `check.mutation` | Evaluate test/property effectiveness against controlled source mutations. | mcy, yosys |
| `simulate.spice` | Run the explicitly selected SPICE analysis with compatible circuit/model views; every mode is qualified separately per backend and device model. | ngspice, xyce |
| `simulate.hdl` | Compile/elaborate and simulate the canvas-selected HDL language using an HDL bench or qualified Python cocotb test source. | icarus, verilator, ghdl, cocotb, amaranth |
| `simulate.cosim` | Run the selected analog/digital coupling contract. A sampled one-way handoff and a live feedback solver are distinct qualified coupling capabilities. | ngspice, xyce, icarus, verilator, ghdl |
| `simulate.optical` | Simulate a circuit using calibrated optical/mixed-domain compact models; advertise each model and analysis compatibility independently. | sax, circulax |
| `synthesize.hdl` | Elaborate the canvas-selected HDL/frontend and synthesize a logic netlist, optionally mapping into a pinned standard-cell library. | yosys, abc, slang, yosys_slang, ghdl, amaranth |
| `implement.asic` | Run a full qualified ASIC flow or a registered stage from a pinned compatible prior state. | librelane, yosys, abc, openroad, opendb, opensta, openrcx, magic, netgen, klayout |
| `implement.fpga` | Perform synthesis/place-and-route and architecture-specific bitstream generation for an explicitly qualified FPGA device; programming is outside this task. | yosys, nextpnr, icestorm, trellis, oxide, apicula |
| `analyze.timing` | Perform static timing with explicit clocks, constraints, libraries, corners and optional extracted RC; report missing constraints and coverage. | opensta, openroad |
| `analyze.power` | Estimate characterized digital power or calculate a qualified physical IR-drop study from declared activity and supplies. | openroad, opensta |
| `analyze.measurements` | Evaluate saved measurements, spectra/FFT, comparisons and plots against pinned result artifacts and measurement definitions. | numpy, scipy, pandas, matplotlib, scikit_rf |
| `extract.layout` | Extract devices/circuit connectivity or parasitic RC from a selected physical view using a compatible technology/extraction deck. | magic, openrcx, klayout, kfactory, gdsfactory |
| `characterize.circuit` | Repeat supported simulations across explicit parameter/corner/statistical samples and evaluate a saved characterization specification. | cace, ngspice, xyce, pyspice, numpy, scipy, pandas |
| `simulate.em` | Solve a saved physical field study with explicit geometry, materials, ports, boundaries, mesh and convergence settings; electromagnetic compliance requires its own modeled limits. | meep, openems, csxcad, palace, gmsh, meow, femwell, meshwell, scikit_fem, scikit_rf, gplugins |
| `simulate.thermal` | Solve a saved thermal study with explicit materials, power sources, boundaries and mesh; coupled electrothermal behavior requires a separately qualified study. | elmer_fem, gmsh, meshwell |
| `simulate.device` | Solve declared semiconductor-device equations and physical boundary conditions in a saved qualified DEVSIM study. | devsim, gmsh |
| `generate.views` | Generate selected component views from pinned sources/factories, producing candidate artifacts and canonical mappings; project adoption uses the shared revision-checked edit contract. | gdsfactory, kfactory, klayout, xschem, vlsir, vlsirtools, amaranth |
| `generate.netlist` | Emit a circuit netlist for the selected schematic/component closure with explicit canonical-to-native terminal ordering. | connectgraph, xschem, gdsfactory, kfactory, vlsir, vlsirtools |
| `export.design` | Export a pinned design view or project bundle, retaining supported native properties and reporting any lossy conversion. | gdsfactory, kfactory, klayout, magic, xschem, yosys, vlsir, vlsirtools |
| `compile.model` | Compile a pinned Verilog-A source closure into a compatible OSDI model artifact in the isolated worker. | openvaf |

## Tools and packages

| ID | Kind | Purpose |
|---|---|---|
| `librelane` | adapter | Pinned ASIC flow distribution and registered flow/stage orchestrator. |
| `yosys` | adapter | RTL elaboration, synthesis, netlist transformation and serialization. |
| `abc` | backend | Logic optimization/technology mapping and supported formal backend inside a pinned flow. |
| `slang` | adapter | Qualified SystemVerilog parsing, elaboration and diagnostics. |
| `yosys_slang` | backend | Qualified Slang frontend integration for the pinned Yosys distribution. |
| `openroad` | adapter | Physical implementation, timing, power-grid and routing tasks through registered schemas. |
| `opendb` | library | OpenROAD physical database and registered geometry/netlist utility backend. |
| `opensta` | adapter | Static timing and supported characterized-power analysis. |
| `openrcx` | backend | Technology-qualified interconnect parasitic RC extraction. |
| `magic` | adapter | Technology-bound layout operations, DRC, extraction and native layout exchange. |
| `netgen` | adapter | Technology-configured circuit/netlist comparison for LVS. |
| `klayout` | adapter | Geometry/format processing, rule-deck DRC, qualified LVS and stream-out comparison. |
| `ngspice` | adapter | SPICE circuit solver with analysis/model/dialect-specific qualification. |
| `xyce` | adapter | Alternative circuit solver; its supported analyses and model dialect are qualified separately. |
| `xschem` | adapter | Native schematic import/export and netlisting; Rocket owns its graphical editor. |
| `cace` | adapter | Saved circuit characterization-plan orchestration and specification evaluation. |
| `openvaf` | adapter | Verilog-A-to-OSDI model compilation for a compatible target simulator. |
| `icarus` | adapter | Icarus Verilog compilation and event-driven simulation. |
| `verilator` | adapter | Qualified SystemVerilog lint, compiled simulation and supported coupling backend. |
| `ghdl` | adapter | VHDL analysis/simulation and separately qualified Yosys synthesis integration. |
| `cocotb` | library | Python testbench integration against a qualified installed HDL simulator. |
| `sby` | adapter | SymbiYosys property proof, bounded checking and cover orchestration. |
| `eqy` | adapter | Yosys implementation-equivalence orchestration. |
| `mcy` | adapter | Mutation-based evaluation of digital verification effectiveness. |
| `z3` | backend | Pinned SMT solver used through a registered formal-engine combination. |
| `boolector` | backend | Pinned SMT solver used through a registered formal-engine combination. |
| `bitwuzla` | backend | Pinned SMT solver used through a registered formal-engine combination. |
| `yices` | backend | Pinned SMT solver used through a registered formal-engine combination. |
| `nextpnr` | adapter | FPGA place-and-route for specifically qualified device/database targets. |
| `icestorm` | backend | iCE40 device data and bitstream utilities where shipped and qualified. |
| `trellis` | backend | ECP5 device data and bitstream utilities where shipped and qualified. |
| `oxide` | backend | Nexus device data and bitstream utilities where shipped and qualified. |
| `apicula` | backend | Gowin device data and bitstream utilities where shipped and qualified. |
| `sax` | adapter | Frequency/wavelength-domain photonic compact-model circuit solver. |
| `circulax` | adapter | Qualified mixed-domain compact-model circuit analyses with a version-bound API. |
| `gdsfactory` | library | Full installed GDSFactory component, geometry, routing, ports and generation API inside managed workers. |
| `kfactory` | library | KLayout-backed component, geometry, port and connectivity library. |
| `gplugins` | library | Qualified solver integration subset; importing a plugin does not qualify its backend. |
| `meep` | adapter | Qualified local electromagnetic FDTD studies. |
| `openems` | adapter | Qualified local electromagnetic FDTD and RF/antenna studies. |
| `csxcad` | library | Geometry/material definition library associated with openEMS. |
| `palace` | adapter | Qualified finite-element electromagnetic field/eigenmode studies. |
| `gmsh` | library | Physical geometry and mesh generation under the selected study contract. |
| `meow` | adapter | Qualified eigenmode-expansion and mode-solver integration. |
| `femwell` | library | Qualified finite-element mode/field modeling APIs. |
| `meshwell` | library | Qualified geometry-to-mesh preparation APIs. |
| `scikit_fem` | library | Finite-element assembly library used by qualified modeling workflows. |
| `scikit_rf` | library | RF network/S-parameter processing and analysis library. |
| `elmer_fem` | adapter | Qualified finite-element thermal studies; coupling is study-specific. |
| `devsim` | adapter | Qualified semiconductor-device equation solves. |
| `gtkwave` | viewer | Optional native waveform artifact viewer; inspection/launch is a frontend capability, not a computational run task. |
| `pyspice` | library | Python circuit/simulator convenience API; it is not an independent solver. |
| `vlsir` | library | Circuit/interchange data library used by qualified generation and exchange tasks. |
| `vlsirtools` | library | Circuit/interchange and simulator integration helpers in prepared workers. |
| `numpy` | library | Numerical array APIs in the prepared scripting/analysis profile. |
| `scipy` | library | Numerical/signal-analysis APIs in the prepared scripting/analysis profile. |
| `pandas` | library | Tabular characterization/result processing APIs. |
| `matplotlib` | library | Engine-artifact plot generation APIs. |
| `pint` | library | Unit-aware numerical helpers in prepared workers; the public API uses Quantity. |
| `networkx` | library | Graph-analysis helpers in prepared workers; canonical topology remains engine-owned. |
| `pyvista` | library | Qualified physical-field visualization/mesh inspection APIs. |
| `trimesh` | library | Qualified mesh/geometry processing APIs. |
| `jax` | library | Pinned CPU numerical/autodifferentiation runtime used by qualified compact-model profiles. |
| `amaranth` | library | User-requested Python HDL frontend and native simulator; add, pin and qualify profile first. Generated Verilog may use other qualified downstream tools. |
| `connectgraph` | adapter | Engine-owned canonical connectivity, electrical-rule and identity-mapping operations. |
