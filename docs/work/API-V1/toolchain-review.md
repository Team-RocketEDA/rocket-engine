# API v1: toolchain call points and model availability

Research date: 2026-11-01. This note informs the proposed contract. It does not
qualify an installed solver, approve a tool version, or claim an adapter exists.
The canonical v1 contract owns task shapes; this note records the reasoning and
upstream evidence behind the task catalog.

## Inventory authority and current implementation

The desired full bundle is recorded in [the selected technology stack](../../../../PRD/tech-stack.md).
Its native-tool/profile inventory is newer and broader than the solver table in
[the older operation proposal](../../../../PRD/tools-research/tooling-operations.yaml):
the latter still puts openEMS, Elmer FEM and FEMwell under `watch`, although the
selected stack includes them. Reconcile that catalog with the v1 registry; do not
advertise the old table's status as current installed/qualified support.

Current implementation evidence is the generated [engine API](../../engine-api.md)
and [adapter tree](../../../src/adapters/README.md). The existing adapters cover
ngspice, Icarus, Slang, Yosys, SBY, LibreLane, OpenSTA, Magic, KLayout, Netgen,
GDSFactory, SAX, Circulax, MEOW and graph/view checks in varying qualified scopes.
The presence of a package or adapter is insufficient to qualify every mode below.
In particular, current HDL simulation is the Icarus source/bench contract, and
current co-simulation samples analog results into an HDL-side handoff. A general
bidirectional live coupling solver remains a distinct qualification requirement.

## Small API, explicit task catalog

One run submission boundary can accept a registered task, a selected tool/profile
and closed typed task options. Analysis and stage selectors avoid a new transport
endpoint for each simulator command or binary. The catalog must expose input
schemas, outputs, descriptions and target/readiness limits for each registered
task. Normal task options do not contain arbitrary shell commands or argument
vectors. Full native library/tool access belongs to the managed scripting boundary.

Distribution packages, subordinate solvers, database libraries and numerical
helpers are discoverable dependencies. They do not all require standalone RPC
endpoints: ABC participates in synthesis; SMT engines participate in formal
verification; PySpice is a simulator interface; Gmsh prepares a physical mesh;
GTKWave consumes waveform artifacts. The tool registry records those relationships.

| Task | Explicit call points | Tools and libraries |
|---|---|---|
| `workflow.asic` | Full pinned implementation/check plan | LibreLane and its distribution closure |
| `workflow.analog` | Netlisting, circuit analyses, characterization, physical checks and configured extracted comparison | Xschem, ngspice/Xyce, CACE, Magic, Netgen, KLayout |
| `workflow.photonic` | Generated layout, circuit response, geometry checks, selected field study | GDSFactory/KFactory, SAX/Circulax, KLayout, MEOW/FEMwell/Meep |
| `generate.views`, `generate.netlist` | Component views, interfaces, geometry and target-format netlists | GDSFactory, KFactory, KLayout, Xschem, vlsir/vlsirtools, graph adapter; qualified HDL frontends |
| `check.syntax` | Parse/lint the selected HDL and supported subset | Slang/yosys-slang, Verilator, GHDL, Icarus |
| `check.connectivity`, `check.erc`, `check.view_sync` | Connectivity, electrical rules and canonical-to-native mapping checks | Engine graph adapter and qualified native adapters |
| `check.drc`, `check.lvs`, `check.antenna`, `check.layout_xor` | Process rules, independent circuit comparison, antenna and stream-out equivalence | Magic, KLayout, Netgen, OpenROAD/OpenDB |
| `check.formal` | Prove, bounded check and cover with recorded assumptions/bounds | SBY/Yosys/ABC with pinned Z3/Boolector/Bitwuzla/Yices combinations |
| `check.equivalence`, `check.mutation` | Golden/candidate equivalence and verification-effectiveness mutation campaigns | EQY, MCY, Yosys/ABC |
| `simulate.spice` | Explicit circuit analysis modes below | ngspice, Xyce, compatible model closure |
| `simulate.hdl`, `simulate.cosim` | HDL/cocotb testing and specifically qualified analog/digital coupling | Icarus, Verilator, GHDL, cocotb, circuit solver |
| `simulate.optical` | Compact-model wavelength/frequency S-parameters and qualified time/mixed-domain modes | SAX, Circulax, calibrated model libraries |
| `synthesize.hdl` | Elaboration, logic optimization, technology mapping and netlist serialization | Yosys/ABC, Slang, qualified GHDL or Amaranth frontend |
| `implement.asic` | Full flow or synthesis/floorplan/placement/CTS/routing/signoff stage | LibreLane/Yosys/ABC/OpenROAD/OpenDB/OpenSTA/OpenRCX/Magic/Netgen/KLayout |
| `implement.fpga` | Device-qualified implementation and bitstream production | nextpnr and shipped IceStorm/Trellis/Oxide/Apicula targets; programming excluded |
| `analyze.timing`, `analyze.power` | Static timing, characterized power and qualified physical IR-drop study | OpenSTA, OpenROAD |
| `extract.layout` | Device/netlist extraction, interconnect RC and physical connectivity | Magic, OpenRCX, qualified KLayout/KFactory/GDSFactory adapters |
| `characterize.circuit` | Saved measurement/specification plans across sweeps, corners and statistical samples | CACE, ngspice/Xyce, PySpice and numerical helpers |
| `simulate.em` | FDTD, FEM frequency/eigenmode, eigenmode expansion | Meep, openEMS/CSXCAD, Palace, MEOW, FEMwell, Gmsh, meshwell, scikit-fem/scikit-rf, qualified gplugins subset |
| `simulate.thermal`, `simulate.device` | Declared thermal and semiconductor-device studies | Elmer FEM, DEVSIM and mesh preparation |
| `analyze.measurements` | Saved measurements, FFT/spectra, comparisons and plots | NumPy, SciPy, pandas, matplotlib, scikit-rf |
| `compile.model` | Supported Verilog-A to compatible OSDI artifact | OpenVAF |
| `export.design` | Supported native/stream/netlist exchange and project bundles | Format adapters, preserving conversion/loss reports |

The user-requested Amaranth frontend is an addition to the previously selected
profile list. Register its planned call points, then add/pin/qualify the actual
frontend and canvas-language conversion path before reporting it available.
Hardcaml remains future extensibility rather than an installed promise.

NumPy, SciPy, pandas, matplotlib, pint, NetworkX, CPU JAX, PyVista and trimesh are
prepared scripting/modeling helpers. Their full Python APIs can be exposed in
managed workers, while persisted edits and consumed outputs retain engine revision
and provenance ownership. Import success never qualifies a physical workflow.

## SPICE analyses: name the "etc."

The initial catalog explicitly names `op` (operating point), `dc` (DC sweep),
`ac` (small-signal frequency sweep), `tran` (transient), `noise`, `tf` (transfer
function), `pz` (pole-zero), `sens` (sensitivity), and `disto` (distortion).
These are registered modes whose actual availability depends on backend, device
model, dialect and version. AC/noise/distortion require a frequency specification;
DC requires sweep variables; transient requires a time specification. Additional
parameters and prerequisites come from the selected task/tool capability schema.
[ngspice documentation](https://ngspice.sourceforge.io/docs.html),
[ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-44-manual.pdf).

Xyce supports DC operating point, transient, AC and noise plus specialized methods
including harmonic balance. The contract registers `harmonic_balance` explicitly; its availability still
requires a qualified Xyce profile/model path. Corners, parameter sweeps and
Monte Carlo are campaigns over analyses; FFT and waveform measurements are
post-processing. Do not advertise experimental ngspice PSS as baseline support.
[Xyce analysis overview](https://xyce.sandia.gov/about-xyce/).

Circulax exposes DC, transient, harmonic balance and small-signal/S-parameter work.
Its v0.2.3 release deprecates `Circuit.ac()` in favor of `sp()`. Stable engine task
names should resolve to the pinned native API in the adapter rather than leak
upstream method churn to every client.
[Circulax](https://github.com/gdsfactory/circulax),
[versioned release notes](https://github.com/gdsfactory/circulax/releases).

## What a PDK supplies and how LibreLane checks

The user is correct that PDK/model libraries provide the physical device models
needed for useful transistor-level simulation. Distinguish primitive device
models from cell SPICE subcircuits that connect those devices. A standard-cell
library can also provide functional Verilog, timing/power Liberty, physical LEF
and full GDS. Their different roles remain explicit and pinned together.

LibreLane's current PDK contract requires corner-selected `LIB` Liberty files,
`CELL_LEFS` and `CELL_GDS`; `CELL_SPICE_MODELS` and `CELL_CDLS` are optional. Thus
PDK compatibility does not prove SPICE availability for every cell or operation.
Its documented `Macro` interface likewise supports multiple views of one block.
[PDK variables](https://librelane.readthedocs.io/en/stable/reference/common_pdk_vars.html),
[macro API](https://librelane.readthedocs.io/en/stable/reference/api/config/).

LibreLane's verification uses several distinct mechanisms: static timing,
process-deck DRC, antenna checks, extraction/Netgen LVS, stream-out XOR, and
equivalence where enabled. It does not validate every property through circuit
simulation. Each applicable check must preserve its own status and evidence.
[LibreLane flow catalog](https://librelane.readthedocs.io/en/stable/reference/flows.html),
[step catalog](https://librelane.readthedocs.io/en/latest/reference/step_config_vars.html).

The public component model can give every circuit participant a uniform SPICE
slot with explicit availability/provenance: authored, PDK reference, generated,
extracted, unavailable, or not applicable. Missing data is not an empty model or
a fabricated simulation pass. RTL requires a compatible mapped cell design and
cell model closure before meaningful cell-level SPICE can be resolved. Pure
optical components may have optical compact models without an electrical SPICE
representation. Graphical decorations never participate in circuit extraction.

## Qualification and I28 requirements

Each task/tool descriptor in the proposed fragment requires qualification; the
registry must separately report installation, task/mode support, tested profile
coverage, and readiness for this target. Selection pins source and view revisions,
canonical interface/mapping revisions, PDK/library/model/deck closure, settings,
tool/profile versions, seeds and consumed artifacts under I28. Replays report
missing or drifted ingredients explicitly. Generated native configs and results
remain artifacts rather than source authority.

The scratch task fragment is `/tmp/rocketeda-v1-tasks.json`; it is an integration
input for the canonical contract and is not a second authoritative repository
contract. Validation here checked JSON parseability, closed task object schemas,
and tool/task cross-reference consistency. Runtime adapters and full consumer/
provider workflow conformance remain future implementation gates.

Amaranth includes native Python simulation/testbenches as well as export to Verilog. The contract registers its native HDL-test role separately from cocotb on generated Verilog; both require installed qualification. [Amaranth simulator](https://amaranth-lang.org/docs/amaranth/latest/simulator.html). Development documentation is research evidence, not a chosen release pin.
