# Engine v1 contract

Status: **design frozen for implementation, 2026-11-01; provider migration and deployment qualification pending.**

The [canonical contract bundle](engine-v1.schema.json) owns v1 wire shapes, typed entity/editor inputs, task options, results, errors, events, canvas configuration and discovery metadata. It is one boundary contract split into cohesive schema/catalog/example files. Generated expansions, TypeScript types, help and examples are outputs. Current v0 handler/docstring contracts remain the description of the running provider until migrated. [ADR-014](../docs/adr/014-contract-first-editor-and-tool-api.md) records authority and the decisions below.

Provider owner: the engine maintainer. Consumers: UIUX/RocketIDE, rocket-fuel/MCP, stdio/HTTP clients and managed Python proxies. The product owner approves semantic changes; affected providers/consumers review any contract change before implementation. Adding an enum does not qualify a tool or language.

## Six methods

| Method | Consumer job |
|---|---|
| `describe` | Learn every method, task, component type, tool, template, schema, side effect and contextual requirement. |
| `query` | Read project state, hierarchy, components/factories from any registered catalog, source content, capabilities or run evidence. |
| `edit` | Commit project/editor transactions, including source saves and managed layout publication. |
| `run` | Start a button workflow or individual tool task; cancel/resume/discard unfinished work. |
| `script` | Open/reset a prepared workspace and execute full installed Python/library APIs with managed project access. |
| `watch` | Read/subscribe to ordered edits, run evidence, script output, capacity and recovery events. |

These are domain methods shared by MCP, framed stdio and HTTP; they are not six independent engine implementations. HTTP bindings use catalog/queries/edits/runs/executions/events resources. MCP exposes the six names. Method, task and tool descriptions come from the same registry. An adapter translates transport framing/correlation and supplies trusted audit context; it cannot replace semantics or create another EngineRuntime.

The [generated catalog](generated/CATALOG.md) lists every task/tool. The [generated examples](generated/EXAMPLES.md) demonstrate discovery, PDK/GDSFactory/IP catalogs, hierarchy queries, editor transactions, every registered task, SPICE analyses, testbench creation, scripting and responses. Schemas reject unknown payload fields. The provider additionally validates relational invariants, dimensions, tool readiness and dependency graphs; valid JSON alone cannot prove these.

## Workflows are the button boundary

`run.start` names a task such as `workflow.asic`, `workflow.analog`, or `workflow.photonic`. The engine resolves the required coverage plan from the target, `canvas.toml`, technology and PDK; freezes inputs; and expands a parent run into a prerequisite DAG. It dispatches independent stages concurrently and gates dependents using real results. Each child run retains its identity and evidence. A required skipped, unavailable or failed check blocks full completion. Stopping after synthesis or routing is explicitly partial completion.

The same `run` boundary exposes individual stages and analyses. The catalog includes syntax, connectivity/ERC, DRC/LVS, antenna, view checks/XOR, proof/bounded/cover, equivalence/mutation, HDL/cocotb, mixed-signal, SPICE, optical response, synthesis, ASIC/FPGA implementation, timing/power, extraction, characterization, fields, thermal/device equations, model compilation, measurements, generation and export. ASIC stages include floorplan, macro/I/O placement, PDN, global/detailed placement, CTS, global/detailed routing, fill and signoff. Registered upstream step IDs are discoverable within a pinned tool profile; they are not arbitrary shell strings.

SPICE call points explicitly include operating point (`op`), DC sweep (`dc`), small-signal frequency sweep (`ac`), transient (`tran`), noise, transfer function (`tf`), pole-zero (`pz`), sensitivity (`sens`), distortion (`disto`), and qualified Xyce harmonic balance. Modes are independently qualified per backend/model/version. Sweeps, PVT corners and Monte Carlo are characterization campaigns; FFT and measurements are post-processing. Photonic tasks distinguish SAX frequency-domain models and qualified Circulax analyses; field tasks distinguish FDTD, FEM/modes and EME. No universal multiphysics result is implied.

A task descriptor reports its schema, accepted target kinds, input views, outputs, required tools and qualification. Installed/qualified/ready are distinct. ABC/SMT engines, meshing libraries, Python helpers and viewers appear as dependencies/capabilities; each need not become its own transport verb. Full library/native functionality remains available through `script` in its prepared worker.

## Circuit components and editable views

A circuit component is a reusable design definition, with instances placed in hierarchy. An ECS component is an internal typed attribute; public discovery calls these definitions, instances, entities or factories explicitly to avoid ambiguity.

The user-facing presets expand into the same canonical circuit identity:

- `spice_block`: saved pure SPICE subcircuit source, ordered terminals and symbol; simulation-only by default. A physical implementation can be attached explicitly later.
- `gdsf_component`: saved Python/GDSFactory factory, parameters, declared interface, generated symbol and managed physical cell. Full installed GDSFactory is available. Generation materializes layout/ports through a qualified run and project publication.
- `hdl_component`: saved digital source set/top in the canvas's selected authored HDL, parameter/generic declarations, elaborated canonical ports and a qualified implementation path. Several files may form one implementation.
- `assembly` and `primitive`: hierarchical composition or qualified PDK/library device/cell.

Each view declares its authoring authority. Schematic, symbol, layout, source and model views share stable component/port identities and explicit mappings. A view can have multiple qualified variants; a run selects a unique view or fails as ambiguous. Generator output cannot overwrite a manually owned layout without an explicit ownership/adoption edit. Source parsing can propose interfaces; the engine preserves canonical port IDs and flags changes that invalidate connections. Parameter-dependent HDL interfaces are elaborated per hierarchy occurrence.

Every circuit component has `models.spice`, with explicit `provided`, `derivable`, `unavailable`, or `not_applicable` state and provenance. Provided models identify simulator dialect, subcircuit, terminal ordering, canonical mapping and model/corner dependencies. RTL generally needs mapping against a standard-cell library before useful cell-level SPICE can be derived. Pure optical or abstract components must not receive invented electrical models. Missing models block relevant operations, not editing.

PDKs/SCLs can supply both primitive device models and cell subcircuits. LibreLane separately uses Liberty, LEF, GDS, SPICE/CDL, process rules and extraction data. Model presence does not mean every checker is implemented as SPICE simulation. See the [sourced toolchain review](../docs/work/API-V1/toolchain-review.md).

Text, lines, polylines, arrows, images, measurement graphics and linked plots are annotation entities. They are excluded from circuit netlisting, ERC and manufactured device counts. Physical cell geometry is owned by the layout and does not make each polygon a circuit component. Testbench harness devices are included only when constructing the test harness, never silently in production output.

## Editors and transactions

`edit` operates on typed projects, components, instances, ports, nets, sheets, symbols, physical cells, pins/maps, shapes/layers, sources, scripts, testbenches and annotations. Create/replace/delete, connect/disconnect, transforms, source writes, geometry actions and explicit artifact adoption share one atomic transaction boundary. Geometry includes shapes, paint/erase, boolean operations, arrays and routes with a pinned technology/grid/recipe. Specialized paint/contact semantics follow the Magic-informed technology model; geometry authoring is a core editor feature.

New entities receive engine IDs. A transaction may use temporary `@keys` and `{local: "@key"}` references, which resolve before commit and never appear in stored state. Existing changes require per-entity CAS, including mutable relationship owners and read dependencies. Duplicate/missing preconditions are errors. Different-entity edits do not conflict merely because another global project revision advanced. Failed transactions leave source bytes, entity revisions and events unchanged. One successful design transaction advances the global snapshot cursor once and returns all affected IDs/revisions.

Working project source links follow stable IDs, so saving a source is reflected in the next project snapshot. Explicit pinned links remain pinned. Before execution, every working reference resolves to an immutable revision under I28. Code saves never execute code; invalid source remains editable, with the last valid interface marked stale rather than silently deleting pins/wires.

Project create/open/close/fork/archive, snapshot restoration and configuration migration are explicit operations. Open/close changes attachment state rather than pretending to edit design truth. Restoration creates a new revision; prior history is retained. Reusable scripts are ordinary saved source plus script entities, callable later through `script`.

## Testbench components

A `testbench` is an explicitly linked harness entity with type `spice`, `hdl`, or `cocotb`. The HDL bench inherits the canvas dialect; an Amaranth canvas generates Python for a qualified native Amaranth simulator, while cocotb can use a separately qualified generated-Verilog path. A SPICE bench declares its analysis, including transient. One primary DUT is required; any additional DUTs and harness wiring are explicit.

If the bench's hierarchy occurrence is `P + [B]`, a legal DUT is `P + [S] + descendants`, where `S` is a direct circuit sibling. Paths use stable instance IDs. The bench cannot target itself, parents/ancestors, another scope, another testbench, or annotations. Additional DUT subtrees must not overlap. Deep probes are relative to a selected DUT and never instantiate its internals twice. Graphical position does not pick the DUT. Targeted child tests use explicit harness inputs/models/loads; they do not silently include the containing circuit.

Placing a bench without source generates a saved editable template from its type, inherited language, legal target selection and materialized interface. The source, target-port bindings, interface digest and template provenance are returned as ordinary project revisions. SPICE templates declare the DUT and analysis/probes; HDL templates instantiate the DUT and connect ports; cocotb templates establish test/clock/reset/assertion skeletons appropriate to declared metadata. Unknown interface properties produce diagnostics or neutral placeholders, never guessed circuitry or reset semantics.

Rename preserves the link. Hierarchy moves/deletions, interface edits and authoring-language changes mark affected bindings stale/missing and block runs until corrected. Regeneration creates a new source/diff for explicit adoption; it never overwrites the user's edited bench. Every execution pins the bench source, target occurrence, interface/mapping, template when consumed, harness model/config and transitive DUT closure. See the [editor review](../docs/work/API-V1/editor-review.md).

## Discovery without hidden execution

`query.from` chooses a project, PDK, library, installed package/provider, entity, run, artifact, request or workspace. `relation` selects components, instances, hierarchy, children/descendants, ports, cells, layers, sources, models, capabilities, evidence or content. Reused/parameterized hierarchy targets include occurrence paths. Filtering and pagination are bounded and snapshot-consistent. Catalog results include stable references, descriptions, interface/parameter summaries, provenance and availability. Uninstantiated factories return interface templates rather than invented canonical entity IDs.

GDSFactory discovery uses prepared indexed provider metadata; full version-specific native help is labeled as such. Query/help never imports project Python, instantiates factories or installs packages. A dynamic interface is reported unresolved until an explicit qualified generation run. Engine IP can later be packaged in `src/ip/verilog`, `vhdl`, `amaranth`, or other modules, but public references use stable versioned catalog identities rather than implementation import paths.

## Scripting and publication

The worker exposes real installed libraries, including `gf`, and managed project/API proxies. Native GDSFactory methods operate normally on worker-local objects. `project.layout.edit(cell)` exposes a real editable GF component and publishes at explicit `publish()` checkpoints or successful context exit. Granular project drawing helpers can submit immediate typed `edit` transactions. Arbitrary mutation of an unmanaged native object stays scratch until attached/published; there is no claim to intercept every C++/Python mutation.

Each publication validates ownership, technology, ports, source revision and CAS, commits to project files, and emits the same events as an editor action. Previously committed mutations survive later script exceptions/cancellation. The console uses fresh prepared isolated workers per cell, retains code/output history, and does not promise persistent Python variables. Child tool runs remain independently tracked. Existing executable-input/host-access policy remains in the [console specification](../../PRD/tools-research/python-console-spec.md).

## Runtime, I28 and migration gates

One EngineRuntime owns both client paths. Heavy work is durably admitted before acknowledgment and dispatches immediately when ready. The FIFO only buffers bursts/recovery. Capacity events tell controlled clients to pause/resume. Saturation races return retryable `admitted:false`; the original request ID/payload can be retried. Accepted work never disappears. Coalescing applies only to equivalent in-flight snapshot/artifact tasks; scripts/edits never coalesce. A coalescing hit records every request ID without consuming another heavy slot. Cancelling that shared run affects attached callers.

Short edits, queries, help, watch and cancellation remain responsive while solvers read immutable snapshots. Restart reports unfinished survivors and executes none automatically; explicit resume/discard follows quarantine policy. Completed reruns use a fresh start, not a replay operation. Execution completion and electrical verdict remain distinct, and terminal records retain partial effects/failures.

I28 freezes `canvas.toml` and references, working-source resolution, canonical interfaces/maps, bench/DUT closures, layers/technology, PDK/model/deck hashes, executable dependencies, profile/tool versions, seeds and effective settings. Reproducibility means verdicts/findings/measurements, not byte-identical native output. Missing/drifted consumed ingredients fail with their identity. Generated native configs/results remain exhaust until explicit source adoption.

Run `.venv/bin/python scripts/check_v1_contract.py --write` to derive types/help/examples/expanded schema, then run it without `--write` to verify freshness. The check validates accepted/rejected contract fixtures and all registered task options. It does not claim the current provider implements v1. Refactoring agents must meet the [execution acceptance matrix](../docs/work/API-V1/execution-review.md), editor scenarios, native-tool qualification and cross-transport consumer/provider conformance before deployment. Current generated v0 docs remain unchanged until that migration passes.
