<p align="center">
  <img src=".github/assets/rocketide-logo.svg" width="72" height="72" alt="RocketIDE logo">
</p>

<h1 align="center">rocket-engine</h1>

<p align="center"><sub>Part of <a href="https://github.com/Team-RocketEDA/RocketIDE"><b>RocketIDE</b></a> · the engine</sub></p>

`rocket-engine` is RocketEDA's headless Python engine for chip-design projects. It owns the shared operation surface, project revisions and events, tool dispatch, capability reporting, and verification evidence used by manual clients and the agent harness.

The product serves digital, analog, photonic, and mixed-domain work. The engine coordinates existing EDA tools through adapters; it does not implement an agent loop or physics solvers. Product direction lives in the sibling [PRD](../PRD/README.md). The agent harness is in [rocket_fuel](../rocket_fuel/README.md), the current workbench is in [UIUX](../UIUX/README.md), and [RocketIDE](../RocketIDE/README.md) is the planned packaging layer.

## Install (SDK)

[![PyPI](https://img.shields.io/pypi/v/rocket-engine.svg)](https://pypi.org/project/rocket-engine/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

The engine ships as a versioned Python package — the **engine SDK**.
Current release: [`rocket-engine 0.0.2b1` (beta)](https://pypi.org/project/rocket-engine/)
on real PyPI. No final release exists yet, so this beta is what a plain
install resolves today.

```bash
pip install rocket-engine==0.0.2b1
rocket-engine --help
python -c "import rocket_engine; print('ok')"
```

`pip` ships the engine, not the tools: native binaries, PDK trees, and
cloud keys arrive via provision recipes, your own `PATH`, or explicit
opt-in — see [Requirements](#requirements) below, generated from the
setup catalogue. The engine resolves provisioned roots first, then
ambient `PATH`, then per-job `tool_dir`; `report_capabilities` tells
you exactly what resolved and the remedy for what did not. Requires
Python ≥ 3.12. The wheel is MIT-licensed and pure first-party code;
it depends on PyPI packages including GPL components (PySpice, klayout
via gdsfactory) — the combination is GPL-governed downstream, the
engine files stay MIT (see [LICENSE](LICENSE)).

## Requirements

<!-- REQUIREMENTS:START -->
pip ships the engine, not the tools. Native binaries, PDK trees,
and cloud keys arrive via provision recipes, your own PATH, or
explicit opt-in. The engine resolves provisioned roots first, then
ambient PATH, then per-job `tool_dir`; `report_capabilities` tells
you exactly what resolved and the remedy for what did not.

### Native tools (provision or PATH)

| Capability | Provides | How to get it |
|---|---|---|
| Digital bundle (oss-cad-suite) | `iverilog`, `vvp`, `verilator`, `slang`, `yosys`, `ghdl`, `sby` | scripts/provision_toolchain.sh: pinned tarball 20261025 + asserts (PROV phase 1). |
| LibreLane (RTL-to-GDS flow) | `librelane` | scripts/provision_toolchain.sh (PROV phase 1; upstream AppImage/Nix install docs). |
| OpenSTA (static timing) | `sta` | scripts/provision_toolchain.sh (PROV phase 1; upstream OpenSTA README source build). |
| ngspice (SPICE) | `ngspice` | docs/provision-plan.md: apt pin or source build (B10). |
| Netgen (LVS) | `netgen` | docs/tickets/NGSPICE-LIVE.md: opencircuitdesign source build (B10). |
| Magic (DRC + extraction) | `magic` | docs/provision-plan.md: source build with --prefix into the app-owned tools dir (B10). |
| KLayout (batch DRC) | `klayout` | docs/provision-plan.md: ambient install kept and version-asserted (B10). |
| Xyce (parallel SPICE) | `Xyce` | scripts/provision_toolchain.sh (PROV phase 2; Xyce building guide recipe). |
| Xschem (schematic) | `xschem` | scripts/provision_toolchain.sh (PROV phase 2; upstream xschem source build). |
| Bubblewrap (isolation) | `bwrap` | docs/probe-bwrap-isolation.md (B10). |
| cvc (SMT solvers) | `cvc4`, `cvc5` | scripts/provision_toolchain.sh: pinned tarball 20261025 ships cvc4/cvc5 (PROV phase 1). |
| OpenROAD | `openroad` | scripts/provision_toolchain.sh (PROV phase 1; LibreLane closure ships openroad). |
| openEMS (EC-FDTD) | `openEMS` | scripts/provision_toolchain.sh (PROV-DEFERRED; docs.openEMS.de recipe). |
| Elmer (thermal/FEM) | `ElmerSolver` | scripts/provision_toolchain.sh (PROV-DEFERRED; CSC PPA apt route). |
| Palace (full-wave FEM) | `palace` | docs/provision-sources.md §12 (unsourced — no recipe yet). |

### Python libraries (ride the wheel)

| Capability | Provides | How to get it |
|---|---|---|
| CACE (characterization) | `cace` | scripts/provision_toolchain.sh (PROV phase 2; pip into the engine venv). |
| SAX (photonic sim) | `sax` | pyproject.toml [project] dependencies: plain `uv sync` installs everything (core library). |
| Circulax (time-domain circuit sim) | `circulax` | pyproject.toml [project] dependencies: plain `uv sync` installs everything (core library). |
| Meow (EME mode/field solver) | `meow` | pyproject.toml [project] dependencies: plain `uv sync` installs everything (core library). |
| gdsfactory (layout views) | `gdsfactory` | pyproject.toml [project] dependencies: plain `uv sync` installs everything (core library). |
| pymeep (FDTD) | `meep` | scripts/provision_toolchain.sh (PROV-DEFERRED; conda-forge pymeep env). |
| DEVSIM (TCAD) | `devsim` | scripts/provision_toolchain.sh (PROV-DEFERRED; pip into the engine venv). |

### PDKs (registered trees, never in the wheel)

| Capability | Provides | How to get it |
|---|---|---|
| PDK sky130A | `sky130A` + 4 decks | scripts/install.sh --pdk-only (PDK_SOURCE/PDK_ID/PDK_REVISION; see docs/demo-runbook.md). |
| PDK ihp (IHP SG13G2 BiCMOS + RF) | `ihp` + 1 decks | docs/pdk/ihp/recipe.md (PDK-IHP lane). |

### Cloud (opt-in only, never default)

| Capability | Provides | How to get it |
|---|---|---|
| Tidy3D web (cloud) | BYOC: tidy3d web | CLOUD-AUTH (Backlog): OS keyring preferred, encrypted file fallback. |
| GDSFactory+ (cloud) | BYOC: gdsfactory+ | CLOUD-AUTH (Backlog): OS keyring preferred, encrypted file fallback. |
<!-- REQUIREMENTS:END -->

## Current shape

- `src/` is the package root and installs as `rocket_engine`.
- `composition.py` is the composition root. It binds project and execution services, operation/query handlers, and solver adapters.
- Transports use the same operation vocabulary. The live CLI and MCP server are implemented. HTTP and IPC currently provide JSON envelope handlers; listening servers, SSE delivery, and length-prefixed IPC framing are not implemented here.
- Project mutations are revision-gated and actor-attributed. A durable project ledger is available when an engine root is configured; an engine without one keeps project state in memory.
- Engine `submit` runs normal solver operations inline and returns their completion. `run_job` remains the explicit deferred/batch pump and idempotent completion fetch.
- Tool registration describes what the engine can route. Machine-specific availability and PDK/deck readiness come from `get_capabilities`; registration alone does not mean a flow is qualified or installed.

## Architecture

```text
UI / CLI / Rocket Fuel
        │
  adapters/{http,ipc,mcp,cli}
        │ commands and queries
  composition.Engine
        ├── project/     revisions, documents, components, events
        ├── execution/   dispatch, isolation, run state, verdicts
        ├── library/     PDK and cell catalogs
        └── workflows/   D/A/P/M check plans and completion gates
                │
       adapters/<solver> ──> native EDA tools and Python libraries
                │
        normalized findings, measurements, artifacts
```

`interfaces/` defines the shared vocabulary, data shapes, and ports. Transport adapters translate client requests into engine calls. Solver adapters preflight project inputs, invoke tools, and normalize their output. The engine evaluates findings and publishes project events; transports do not own verification rules.

| Module | Responsibility |
|---|---|
| [`src/interfaces/`](src/interfaces/README.md) | Operation/query vocabulary, contracts, ports, path and design-data types |
| [`src/project/`](src/project/README.md) | Revision-gated documents, ECS components, snapshots, and event ledger |
| [`src/execution/`](src/execution/README.md) | Run lifecycle, bounded dispatch, isolation, Python execution approvals, and verdicts |
| [`src/library/`](src/library/README.md) | PDK registration/readiness and reusable cell catalogs |
| [`src/workflows/`](src/workflows/README.md) | Digital, analog, photonic, and mixed-domain stage plans and completion checks |
| [`src/adapters/`](src/adapters/README.md) | CLI, MCP, HTTP/IPC envelope handlers, and solver integrations |

## Registered solver operations

| Operations | Adapter(s) |
|---|---|
| `run_drc` | Magic (default), KLayout |
| `run_hdl_test`, `run_syntax`, `run_formal`, `run_synth`, `run_timing` | Icarus, Slang, SBY, Yosys, OpenSTA |
| `run_spice`, `run_post_layout`, `run_cosim` | ngspice; co-simulation also uses Icarus |
| `run_optical`, `run_em` | SAX/Circulax, MEOW |
| `run_extraction`, `run_lvs` | Magic, Netgen |
| `run_connectivity`, `run_erc`, `run_view_sync` | connectgraph |
| `generate_views` | GDSFactory |
| `run_digital_flow` | LibreLane |

This is a routing map, not a support guarantee. Consult `get_capabilities` for installed tools, profiles, PDKs, and decks. The LibreLane adapter is registered and has hermetic coverage; its live RTL-to-GDS qualification is currently blocked on the pinned LibreLane distribution and a compatible PDK root. See the [DIGITAL-FLOW report](docs/work/DIGITAL-FLOW/report.md) and the [sprint board](docs/sprint-board.md) for current work status.

## API contract

**Next implementation contract:** the [v1 contract bundle](contracts/README.md)
freezes six methods (`describe`, `query`, `edit`, `run`, `script`, `watch`),
typed editors/components/testbenches, tool tasks and `canvas.toml`.
It includes generated client types/help and validated examples. Provider and
consumer migration is pending; the current running API below is v0.
[ADR-014](docs/adr/014-contract-first-editor-and-tool-api.md) records the
supersession and deployment gates. Check the design contract with
`.venv/bin/python scripts/check_v1_contract.py`.


The operation and query vocabulary is in [`src/interfaces/vocabulary.py`](src/interfaces/vocabulary.py). Handler docstrings are the source for the generated [`docs/engine-api.md`](docs/engine-api.md), [`docs/api-schema.json`](docs/api-schema.json), and [`docs/api-help.json`](docs/api-help.json). Do not hand-edit those generated files; regenerate them with `scripts/api_spec.py --write`.

Every accepted mutation checks `expected_revision`, advances the project revision, and records its actor. A stale revision returns `revision_conflict`; callers re-read and retry. Run verdicts are engine-owned. Exit status and tool process output alone never establish PASS.

The current MCP bridge derives descriptions from handler docstrings. Its wire input schemas are still generic for most tools; only `python_execute` currently has a specific schema. See [MCP-SCHEMA](docs/tickets/MCP-SCHEMA.md).

## Setup and common commands

Use the repository installer as the only supported Python environment setup. It creates the pinned Python 3.12 environment, installs the base and development dependencies, installs a sealed engine copy, registers the configured PDK, and probes selected host tools.

```sh
scripts/install.sh --install
.venv/bin/python -m rocket_engine --help
scripts/install.sh --check-only
```

Native tool provisioning is documented in [`docs/provision-plan.md`](docs/provision-plan.md) and managed by `scripts/provision_toolchain.sh`. `get_capabilities` reports what is usable on the current machine. After editing `src/`, rerun `scripts/install.sh --install` so the sealed package matches the source tree.

For operation docstring and generated-contract conventions, read [`AGENTS.md`](AGENTS.md). It also documents the test and fixture workflow. The [scenario guide](scenarios/README.md) describes live-tool prerequisites and the scenario CLI.

## Where to look next

- Project requirements and decisions: [`../PRD/README.md`](../PRD/README.md)
- Current engine work and open tickets: [`docs/sprint-board.md`](docs/sprint-board.md), [`docs/tickets/`](docs/tickets/)
- Fuel integration contract: [`docs/fuel-contract.md`](docs/fuel-contract.md)
- Generated engine API: [`docs/engine-api.md`](docs/engine-api.md)
- Storage ownership: [`docs/storage-policy.md`](docs/storage-policy.md) and [`docs/adr/`](docs/adr/README.md)
