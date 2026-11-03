# rocket-engine

`rocket-engine` is RocketEDA's headless Python engine for chip-design projects. It owns the shared operation surface, project revisions and events, tool dispatch, capability reporting, and verification evidence used by manual clients and the agent harness.

The product serves digital, analog, photonic, and mixed-domain work. The engine coordinates existing EDA tools through adapters; it does not implement an agent loop or physics solvers. Product direction lives in the sibling [PRD](../PRD/README.md). The agent harness is in [rocket_fuel](../rocket_fuel/README.md), the current workbench is in [UIUX](../UIUX/README.md), and [RocketIDE](../RocketIDE/README.md) is the planned packaging layer.

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
