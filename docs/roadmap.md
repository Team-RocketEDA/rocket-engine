# Engine roadmap to November 4

Status: implementation roadmap, 2026-11-01. Target date: **2026-11-04, Asia/Dubai**. This plan is a delivery boundary and dependency order, not evidence that unfinished work is complete. [ADR-015](adr/015-local-desktop-results-and-roadmap.md) records the product direction; the [canonical v1 contract](../contracts/engine-v1.schema.json) owns wire/task/data shapes.

## Capability and release boundary

Ship a local Electron/React ASIC workbench backed by one headless EngineRuntime. Users and their agent edit the same hierarchical circuit/layout source, run the qualified digital/analog/photonic circuit fixture paths, and inspect typed datasets and actual violations. The presentation layer renders declared data views; terminal subscribers receive verbose native output. No cloud-hosted IDE is part of this product.

| Track | Work | November 4 requirement |
|---|---|---|
| `mvp` | Shared local runtime, canonical API/data types, project/edit correctness, dataset/result delivery, output terminal, source/testbench/editor contracts and client integration | Required on the selected supported fixture/PDK/profile combinations; unsupported combinations report precise reasons. |
| `mvp` | Existing ASIC digital flow, HDL testing, DRC/LVS/ERC/connectivity, qualified timing/extraction; SPICE operating point/DC/AC/transient; optical compact-model circuit response | Prove the selected end-to-end paths and returned data shapes with representative fixtures. Native solver/process availability is a gate, not a reason to invent PASS. |
| `post_mvp` | FEM, EM/FDTD/EME/mode/field solvers, thermal/electrothermal and semiconductor device-field work | Define typed study/result contracts and keep explicit RED provider acceptance work; do not provision or complete these to unblock the November 4 release. |
| `off_mvp` | FPGA place/route, device families/databases, bitstream delivery and device programming | Separate future roadmap. HDL simulation/synthesis for ASIC work remains in MVP. |
| Outside current product | Cloud-hosted IDE, multi-tenant service, browser-owned execution | No release dependency and no implied future hosting promise. Local HTTP is a transport, not a hosting plan. |

The required SPICE analyses remain `run.start(task="simulate.spice")` with analysis selectors `op`, `dc`, `ac`, and `tran`. Their data contracts include operating-point values, DC sweep coordinates, AC complex frequency response and transient time traces. Other named SPICE modes stay defined and independently qualified; they are not silently removed or implied ready by the presence of ngspice. Corners/sweeps/Monte Carlo are campaigns over analyses, with explicit dimensions and conditions in results.

SAX/Circulax compact circuit results remain in the MVP lane where qualified. MEOW EME, optical mode/FEM/FDTD and other spatial field studies are post MVP even if an earlier import/smoke ticket is Done. An optical spectrum is a trace; a heatmap requires matrix/spatial data. Historical proofs are retained without turning them into a delivery obligation.

## Dependency roadmap

The dates below are target handoffs. A failed exit gate stays open and visible. Contract and provider evidence have separate states; a schema can be GREEN while its future provider suite remains RED.

| Slice | Target handoff | Scope and context | Dependencies | Exit evidence |
|---|---|---|---|---|
| R0: freeze data boundaries | Nov 1 | Complete task inputs/outputs, datasets, views, provenance, chunk/bulk refs and terminal events in the canonical bundle; generate TypeScript and Pydantic boundaries. Keep the domain independent from these framework adapters. | ADR-014/015, API-V1-CONTRACT | Canonical accepted/rejected cases pass, generated outputs are current and Python/TypeScript round trips preserve the agreed fields/units/complex values. No duplicate handwritten payload definition. |
| R1: shared core and bounded edits | Nov 2 | Strangle the legacy facade into small feature/use-case packages and ports. Preserve one runtime, per-entity CAS, immediate durable admission, responsive edit/control lanes, explicit resume and I28. | R0; API-V1-CORE, ENTITY-CAS, CANVAS-CST | Transport parity, idempotency, atomic rollback, same-entity conflicts, disjoint-edit concurrency, capacity pause/resume and cursor recovery. Source modules remain below 3,000 lines. |
| R2: native result adapters | Nov 2 | Map current DRC/LVS, SPICE DC/AC/transient, HDL and optical circuit output into typed results. Publish datasets once; downstream stages bind declared dataset/artifact refs and never scrape the terminal stream. | R0; API-V1-TOOLS, DECK-XSCHEM, DIGITAL-FLOW/TIMING-STA where relevant | Representative known-good/known-bad fixtures retain waveform/violation data, units, stage identity, native evidence and target/input lock. Missing solvers/models/decks stay typed unavailable. |
| R3: editor and presentation consumers | Nov 2–3 | Complete typed source, schematic, symbol/cell/layout changes and scoped bench templates. React renders traces/tables/matrices/fields/markers from descriptors; raw logs stay in the output terminal. Keep dense docked editors/chat/settings without promotional prose or decorative telemetry. | R0 for rendering; R1 for edits; API-V1-EDITORS, TESTBENCH-COMPONENT, API-V1-CLIENTS | Type-valid data fixtures render by generic data/view kind, each sim gets an independently closable run view, DRC opens actual violations, linked selections cross-probe stable IDs, source edits never silently overwrite/rebind. Actual rendered UI evidence is required before claiming visual acceptance. |
| R4: whole local workflows | Nov 3 | Join button workflow DAGs, source/config resolution, native adapters, datasets and result events on selected digital/analog/photonic/mixed fixtures. Agent skill instructions use discovery and the same calls as UI. | R1, R2, R3; WORKFLOW-COVERAGE, API-V1-CONFORMANCE | Required stage failures/unsupported/skipped states prevent completion; I28 pins every consumed source/model/profile/config/tool and bench binding. No client-written verdicts or implied check success from exit zero. |
| R5: installed release gate | Nov 4 | Qualify the selected MVP tool/profile/PDK closure on supported local desktop packaging. Verify restart, cancellation, startup, persisted edits and results. Leave all deferred work out of the release gate. | R4; MVP subset of PROV/BUILD-LOCAL, API-V1-CONFORMANCE | Fresh installed representative journeys, actual parser/data validation, truthful coverage report, no accepted work loss, and a recorded list of unsupported/deferred capabilities. If this gate is incomplete, report an incomplete release rather than declaring deployment-ready. |

R1 and R2 may run in parallel after R0 if ownership stays separate: core/contracts are not rewritten independently by tool agents. Presentation work can begin from canonical result fixtures after R0, but a fixture render does not prove a live adapter. Editor consumers must wait for their mutation semantics and revision contract before integration.

## Ticket mapping and scope corrections

The board is managed through `scripts/sprint.py`; board status is authoritative when a ticket body's older header disagrees. Existing Done tickets preserve history and narrow evidence, not an assumption that v1 or every mode already conforms.

| Existing work | Required interpretation |
|---|---|
| API-V1-CONTRACT | Design artifact complete; new typed data refinements regenerate the same bundle. It does not prove current v0 providers implement v1. |
| API-V1-CORE / EDITORS / CLIENTS / CONFORMANCE | MVP work, qualified through the data and runtime boundaries above. Local stdio/MCP are the product paths; local HTTP remains a compatible test/optional transport. |
| API-V1-TOOLS | MVP native adapter subset plus complete contract descriptions. Move FPGA/EM/FEM/modes/thermal/device implementation and qualification to separate deferred tickets. |
| PROV | Split the selected MVP pack/profile closure from full-inventory provisioning. FPGA and advanced physics packages do not keep the November 4 gate open. A distribution used for ASIC tooling may contain collateral binaries without advertising an FPGA product feature. |
| PHOTONIC-WIRE / MEOW-LIVE / MEOW-STDOUT | Preserve completed historical wiring/smoke evidence. Compact-model circuit simulation remains MVP; EME/mode/field expansion is post MVP. |
| API-V1-CONFORMANCE | Contract/serialization checks can be GREEN. Live provider and installed-native checks require their own measured evidence. Opt-in deferred RED probes are recorded separately and do not pollute the default MVP unit-test target. |
| REMOTE-EXEC / CLOUD-AUTH / DOCKER-DEPLOY | Reconcile with a local desktop product. A server/container/cloud requirement cannot become a hidden MVP dependency. Agent model-provider connectivity is a separate client setting. |

## Hexagonal handoff and code ownership

Adapters translate Electron/stdio/MCP/HTTP, native formats, storage and plot data at the edge. Application ports own typed task execution, dataset publication/read, source revisions, events and clocks/IDs. Use cases orchestrate them; domain rules import none of the transport, solver, UI or validation frameworks. Generate Pydantic DTOs at the boundary and map to domain value types where necessary.

Migrate by a vertical slice and retain a reversible legacy facade until conformance passes. Do not reorganize the whole repository in one untested move. Use short nested module names, one cohesive responsibility per file and small shared low-level modules only where semantics are genuinely reused. Avoid a new giant utility module or hidden service locator. The detailed rule belongs in AGENTS.md and its refactor tickets.

## Deferred RED lane

Run the explicit suite from the engine repository:

```sh
.venv/bin/python -m pytest -q contracts/conformance/deferred/test_delivery.py --tb=short
```

At the November 1 baseline it has eight intended failures: the current HTTP adapter rejects the canonical v1 envelopes before it can describe deferred tasks or return their typed pre-admission refusal. This proves a missing boundary implementation, not solver numerical behavior. It uses no native solver and has no skip/xfail. See the [deferred evidence](../contracts/conformance/deferred/README.md).

Later work must separately qualify native FPGA/EM/thermal/device execution against representative sources, mesh/material/port/boundary data and real tools. Once a feature is promoted beyond its delivery gate, change that release profile explicitly and add native output/convergence/known-bad coverage; do not reinterpret these refusal probes as solver qualification.
