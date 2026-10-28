# rocket-engine

Headless shared tooling engine for chip design. It owns project revisions,
run state, and verification evidence. It renders nothing.

The UI lives in [RocketIDE](https://github.com/Team-RocketEDA/RocketIDE),
in the same organization. RocketIDE and AI/MCP clients invoke the same
engine operations and subscribe to the same project events. Product
requirements live in the [PRD](../PRD/README.md).

## What this is

- **One headless engine, and `src/` is its top level.** `src/` contains
  the engine modules directly (`interfaces/`, `project/`, `execution/`,
  `library/`, `workflows/`, `adapters/`, `interfaces/`) and installs as
  the `rocket_engine` package. There is no nested package directory and
  no UI code anywhere under `src/` — no React, no Electron, no viewers,
  no Playwright.
- One Python service behind headless protocols: framed stdio,
  HTTP + SSE, MCP stdio bridge, CLI.
- The authority for preflight, scheduling, state effects, evidence,
  and frontend notifications.
- A modular monolith: one deployable, hard module boundaries, one
  bounded context per top-level module.

## What this is not

- No agent loop. The bundled opencode harness consumes this engine
  over MCP; the engine never depends on it.
- No physics solvers of our own. Adapters wrap existing tools and
  report their evidence honestly.

## Assumption

I am just assuming you cloned all of Team Rocket's repos under one folder, such that all the repos are siblings.

## Where do I go?

| Goal | Read |
|---|---|
| Shapes, commands, events, ports | `src/interfaces/README.md` |
| Transports and tool wrappers | `src/adapters/README.md` |
| Revisions, snapshots, event log | `src/project/README.md` |
| Jobs, workers, evidence, verdicts | `src/execution/README.md` |
| PDKs, profiles, reusable IP | `src/library/README.md` |
| Process order and check plans | `src/workflows/README.md` |
| PRD amendments from this repo | `docs/prd-feedforward.md` |
| Product requirements (upstream) | `../PRD/README.md` |
| Engine API for frontend devs | `docs/engine-api.md` |

One-way references: module READMEs point up (here, the PRD). Rules
live once — here or in the owning module, never both.

## Contract first

The engine API is the authoritative machine-checkable contract between
`rocket-engine` and RocketIDE. It is defined in `interfaces/` (YAML
schemas, refs, units, errors, plus typed commands, events, and ports) and the proposed catalog in
[tooling-operations.yaml](../PRD/tools-research/tooling-operations.yaml),
with command/event semantics in
[frontend-tooling-spec.md](../PRD/tools-research/frontend-tooling-spec.md).
No implementation without a schema; no UI field without a typed engine
output. Protocol renames are breaking changes and must be pinned by
contract tests.

## Module map

| Module | Owns | Must not own |
|---|---|---|
| `interfaces/` | THE contract: YAML schemas + typed commands/events/ports. Single source of truth | Any I/O, any logic |
| `adapters/` | One duplex adapter per channel: `{api,ipc,mcp,cli}` + per-solver wrappers | Business rules, state, verdicts |
| `project/` | Revisions, snapshots, idempotent `request_id`, ordered events, cursors | Tool output parsing |
| `execution/` | Live Python env (IDE terminal backend) + jobs: queue, workers, cancel, evidence, verdicts | Solver CLIs, check planning, any UI |
| `library/` | PDK registry, profile catalog, IP search/register/instantiate | Geometry, simulation |
| `workflows/` | D/A/P/M step order and check plans as data | Solver invocation |

## Adapters vs interfaces (hexagonal: ports vs edges)

They are different architectural elements, not two names for I/O. The
rule is absolute.

- **`interfaces/` are the data contracts themselves (ports).** They
  define what the engine can do and what it needs, as types: the
  command envelope every transport speaks, the event envelope every
  subscriber receives, and the outbound ports (`ToolAdapter`,
  `IsolationRunner`, `CatalogProvider`) the application layer depends
  on. No bytes on wires, no subprocesses — pure contracts.
- **`adapters/` are the communication implementations (edges).** One
  duplex adapter per channel, each owning its full round trip. A
  transport adapter (`api`, `ipc`, `mcp`, `cli`) translates outside
  bytes → ports → engine effects → events back out. A solver adapter
  (future `<solver>`) translates engine jobs → tool CLI/API →
  normalized evidence back in. No inbound/outbound grouping: direction
  never splits what one owner keeps consistent.

One job end to end, `run_drc`:

```text
human click / MCP call
  → adapters/mcp/ parses JSON-RPC into the interfaces/ command
  → execution/ preflights, dispatches, evaluates (via interfaces/ ports)
  → adapters/magic/ runs the deck, parses the report database
  → execution/ commits evidence, project/ publishes check_updated
```

The MCP bridge and the magic wrapper never know about each other. A
new transport adds no check; a new solver adds no endpoint.

Enforcement, in dependency terms:

```text
adapters/mcp    → interfaces/ + project/ + execution/
execution/      → interfaces/ ports (never concrete adapters)
adapters/<tool> implements interfaces/ ports
```

No adapter imports another adapter. Test split follows the same line:
transports against a fake engine (I05, I12), solvers against real
native fixtures (I14), ports against contract tests (I01).

```
src/                          ← the engine; installs as `rocket_engine`
  __init__.py
  interfaces/                 ← THE contract: schemas, commands, events, ports
  adapters/{api,ipc,mcp,cli}/ + adapters/<solver>/
  project/  execution/{queue,workers,evidence,evaluator}/
  library/  workflows/
```

Each module ships `README.md` plus `tests/` (unit + contract tests,
fixtures under `tests/fixtures/`). A module boundary is an import
boundary, enforced in review.

## Tool & dependency decisions

<details>
<summary>Decided tool per verification job (click to expand). Rule: one tool per job; a second only on proven unique verification value.</summary>

### Engine-side (bundled or qualified by the engine)

| Job | Tool | Install |
|---|---|---|
| HDL regression, coverage, lint | Verilator | native (OSS-CAD-Suite) |
| SDF/timing GLS, X-prop sim | Icarus | native (OSS-CAD-Suite) |
| VHDL sim + synth frontend | GHDL | native (OSS-CAD-Suite) |
| Python testbenches | cocotb | pip `hdl` |
| Synthesis (+SMT backend) | Yosys/ABC | native (OSS-CAD-Suite) |
| SV parse/elaborate, style lint | Slang, Verible | native (OSS-CAD-Suite) |
| Formal proofs / equiv / mutation | sby, eqy, mcy (+yices/Z3) | native (OSS-CAD-Suite) |
| ASIC flow, STA, power | LibreLane closure | native pack (B10) |
| Analog sim (DC/AC/tran/noise/corners/MC) | ngspice (+PySpice binding) | native + pip `analog` |
| Analog characterization | CACE (drives ngspice+physical) | native |
| Schematic capture/netlists | Xschem (batch use) | native |
| Photonic freq circuits | SAX | pip `photonic` |
| Photonic transient/active/HB | Circulax | pip `photonic` |
| Eigenmode expansion + modes | MEOW | pip `photonic` |
| Layout-to-EM prep | GSIM | resolved at B7 profile lock |
| Photonic FDTD | Meep | resolved at B7 profile lock |
| RF/antenna FDTD | openEMS | resolved at B7 profile lock |
| 3D thermal/structural | Elmer | resolved at B7 profile lock |
| Waveguide modes/device heaters | FEMwell | resolved at B7 profile lock |
| Meshing, RF numerics | Gmsh, scikit-rf | native + pip `analog` |
| Layout generation | GDSFactory | pip `layout` |
| DRC (default), XOR, streamout | KLayout batch | native |
| LVS compare | Netgen (Magic/KLayout-extracted netlists) | native |
| Waveform evidence extraction | GTKWave batch mode | native |
| Plot artifacts | matplotlib | pip `analog` |

Native-tool acquisition (suite vs apt vs vendored) is decided at B10.
Until then tools are expected-but-unpinned: every run records the
exact tool+version+deck it used, nothing is assumed.

### Display-side (RocketIDE-owned — never engine dependencies)

Surfer (embedded waves), GTKWave GUI (desktop fallback), KLayout GUI,
KWeb (browser layout), Xschem GUI. The engine emits typed data plus
artifact references; RocketIDE renders. The full data contract lives
in [docs/engine-api.md](docs/engine-api.md) so UI work runs parallel.

### Backlog (kept out until a trigger fires)

Xyce (post-layout scale blowup or HB need), Palace (FEM-only
structure), DEVSIM (TCAD need), Magic-as-default (Magic-only deck).

### Dropped

Surelog (Slang supersedes), EMEPy (MEOW is native), nextpnr (FPGA,
no stages), Tidy3D-required paths (commercial must never be required).

</details>

- TDD, always: failing test first, watch it RED, smallest GREEN, then
  refactor. RED must be the intended missing behavior, not setup
  breakage. Checkpoint commits: `test:`, then `fix:`, then optional
  `refactor:`.
- Coverage floor: 80%+ for shared engine logic (`interfaces`,
  `project`, `execution`). Coverage never replaces real-solver fixture
  tests.
- Contracts first: new shapes land in `interfaces/` with strict parsing
  (reject duplicate keys, tags, aliases, merge keys, expressions,
  non-finite scalars) and unknown-field rejection before any caller
  uses them.
- Same semantics for every caller: a human UI action and an MCP call
  with identical saved inputs get identical preflight, evaluation, and
  effects. Actor and run IDs may differ; outcomes may not.
- Evidence honesty: exit zero is not PASS. Violations stay FAIL;
  missing/cancelled/unparsed stays NOT_RUN with a reason; unsupported
  stays UNSUPPORTED. Never invent values to fill a panel; paginate and
  reference raw artifacts instead.
- Isolation is the OS boundary, not an import blacklist. Python workers
  and EDA jobs run in prepared, read-only profiles with scoped scratch;
  venvs and `exec` globals do not count as isolation. Unavailable
  sandbox disables the feature; never host fallback.
- Approval binds code hash, console generation, history cursor,
  environment digest, project revision. Agent code cannot self-approve.
  Code, history, env, or project changes before admission invalidate
  approval.
- No secrets in git, logs, or client bundles. No dependency installs
  during runs. No shell strings, pickles, or base64 payloads in records.
  Native Python/RTL/SPICE files stay external, referenced by YAML,
  hashed into the run lock.
- SOLID at module scale: depend on `ToolAdapter`,
  `IsolationRunner`, `CatalogProvider` abstractions, not concrete
  solvers. New tools and transports extend; they do not edit the kernel.
- Smallest complete diff (ponytail): reuse helpers and stdlib before
  new code; no wrappers, options, or "for later" code. Deletion beats
  addition. A shortcut with a known limit gets a
  `shortcut: <limit>, <when to upgrade>` comment.
- Comment only the why the code cannot show, in one line.

## Working agreement

1. Pick the invariant (I01–I27 in
   [behavior-invariants.yaml](../PRD/tools-research/behavior-invariants.yaml))
   the change must prove.
2. Write the failing test under the owning module's `tests/`.
3. Implement the smallest change through the owning module's public port.
4. Run `uv run --locked pytest tests/<module>`; full suite before merge.
5. Record RED/GREEN evidence and fixture/tool hashes in the PR or TDD note.

Planned stack: CPython 3.12, Pydantic v2, ruamel.yaml, FastAPI +
Uvicorn, official MCP SDK, UV-locked profiles, pytest. See
[tech stack](../PRD/tech-stack.md),
[blueprint](../PRD/plans/rocketeda-project-blueprint.md),
[operations](../PRD/tools-research/tooling-operations.yaml),
[frontend contract](../PRD/tools-research/frontend-tooling-spec.md),
[verification process](../PRD/tools-research/verification-process.md).
