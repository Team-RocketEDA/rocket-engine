# Editor and testbench contract review

Review date: 2026-11-01. This note records design recommendations and their
evidence. The API contract artifact, once adopted, owns wire field names and
payload shapes; examples and semantic names here are not a second schema.

## Existing constraints that the contract must preserve

- [ADR-008](../../adr/008-per-entity-cas.md) uses per-entity compare-and-swap for
  editing. The global project revision remains a snapshot and event cursor.
  Independent entity edits must not conflict solely because this cursor moved.
- [ADR-011](../../adr/011-one-runtime-durable-admission-and-client-neutral-operations.md)
  requires one runtime, client-neutral operations, durable accepted requests,
  immediate dispatch when capacity permits, coalescing on identical pinned
  inputs, and unit/canvas targets with explicit dependency closures.
- [ADR-013](../../adr/013-magic-aligned-technology-driven-layout.md) requires a
  resolved technology profile for useful physical painting, stable layer IDs,
  preserved authored geometry, and explicit process capabilities.
- [SCHEMATIC-EDIT](../../tickets/SCHEMATIC-EDIT.md),
  [SYMBOL-CELL-EDIT](../../tickets/SYMBOL-CELL-EDIT.md), and
  [CELL-LINK](../../tickets/CELL-LINK.md) require editable hierarchical views,
  canonical pins, physical anchors, explicit mappings and cross-probing.
- [ENGINE-ECS](../../tickets/ENGINE-ECS.md) establishes stable entity identity
  and generic attribute CRUD. It does not yet specify every domain invariant
  needed by an editor, source-view resolver or testbench.

## Common editor model

A reusable circuit component has one stable identity and links an interface,
parameters, source/model views, schematic, symbol and physical cell. A placed
instance refers to a component definition and supplies parameter values and
connections. Repeated placements are distinct occurrences even when they share
the same definition. Circuit components, block instances and ECS attributes must
be distinguishable in query results.

`spice_block`, `gdsf_component`, and `hdl_component` can be creation archetypes
over that common model. They initialize suitable sources, editors and operation
capabilities without creating separate identity systems. An HDL source set may
span several files. A SPICE block declares a subcircuit/top and positional port
order. A GDSFactory component declares a Python entry point, parameter schema
and canonical/materialized ports, and publishes project-owned geometry.

Canonical port IDs survive view edits. Each view maps its native ports to those
IDs. Parsing/elaboration may propose HDL or SPICE ports; it must report changed,
removed and unmatched ports instead of silently rewiring existing connections.
The need for explicit SPICE port ordering is demonstrated by
[Xschem's external-subcircuit workflow](https://xschem.sourceforge.io/stefan/xschem_man/tutorial_use_existing_subckt.html),
which binds a symbol to an existing netlist and documents the order used for
subcircuit calls.

A standard SPICE model slot should report whether a model is provided,
derivable, unavailable or inapplicable. References retain terminal order,
compatible dialect/simulator, conditions/corners and provenance. A nonempty
SPICE implementation is not an edit-time requirement for optical, abstract,
interface-only or unelaborated HDL components. Authored SPICE, synthesized
cell-level SPICE and extracted SPICE remain distinct views or artifacts.

Annotations are stored entities with graphical properties and explicit
non-circuit participation. Lines, arrows, images, text, plots and measurement
graphics do not become circuit connections by touching a pin. Physical layout
shapes receive electrical meaning from the technology/extraction model; each
polygon is not independently a circuit component with its own SPICE model.

The direct editor needs typed shape creation, paint/erase where supported,
selection, transforms, copying/arrays, hierarchy, labels and physical ports.
Geometry CRUD alone does not define Magic-like technology paint composition.
View navigation and display gestures remain client state; durable geometry,
connectivity and cross-view mappings remain engine state.

## Discovery and language selection

The common query surface should accept a typed source selector covering a
project, hierarchy occurrence, PDK, shared/user library or installed package
provider. It can return definitions/factories, instances, descendants, ports,
nets, layers, counterpart mappings and capabilities. GDSFactory factories are
catalog definitions, not already placed ECS instances. Queries need bounded
predicates, stable ordering and cursor pagination, and must not execute arbitrary
referenced project code to discover its contents.

`canvas.toml` replaces `canvas.cst` as the design-intent and tool-settings file.
Legacy migration must reject ambiguous conflicting copies rather than silently
choosing one. The selected HDL names the canvas's authoring language. Generated
Verilog produced by an Amaranth compiler is a downstream artifact and does not
turn the source canvas into mixed-language authoring. A new dialect is available
only after its compiler/profile and operation path are qualified. Python used
for cocotb tests or layout generation does not alter the selected HDL.

## Script publication and revisions

The [console specification](../../../../PRD/tools-research/python-console-spec.md)
already states that explicit project API mutations commit independently and a
later script exception does not roll them back. An explicit edit change set can
be atomic; an entire arbitrary Python execution is not implicitly atomic.

An installed GDSFactory API can operate on real worker-local objects. Managed
project layout handles publish changed cells/hierarchy at documented checkpoints
such as a console statement, explicit publication or edit-context completion.
Do not promise reliable interception of every mutation inside arbitrary native
library objects. Plain scratch components become project geometry only after
attachment/publication. Long scripts can publish intermediate changes. Every
publication uses the same ownership and CAS checks as a frontend edit.

## Testbench placement and target containment

The following is the proposed normative containment rule. It is a product
decision, not an upstream tool limitation.

Let an exact testbench occurrence have absolute instance path `P + [B]`, where
`P` is the path of its containing circuit scope and `B` is the testbench instance
ID. A legal target has absolute path:

```text
P + [S] + D
```

`S` must be a direct circuit-instance child of `P`, `S` must differ from `B`,
and `D` is an ordered path of zero or more circuit-instance descendants of `S`.
Thus a bench may target its circuit siblings or descendants of those siblings.
It cannot target itself, its owner/parent, an ancestor, an ancestor's sibling,
another project, an annotation or another testbench. Descending through a
testbench-only hierarchy is not a circuit-target route.

Instance paths are arrays of stable engine IDs, never strings split on dots or
slashes. The engine derives `P` from the bench occurrence and resolves every
path segment against the same pinned snapshot. Names, labels, drawing distance,
selection order and screen coordinates do not establish scope or targeting.
Sheets affect containment only when they represent a real circuit hierarchy
boundary; a cosmetic page/view arrangement does not change legal target scope.

For reusable component definitions, store target paths relative to the bench's
containing circuit scope. The first segment identifies `S`. Running a concrete
bench occurrence expands the path with its resolved `P`; evidence records the
absolute occurrence path. This prevents a bench definition reused under two
parent instances from accidentally selecting only one of those occurrences.

At project root, `P` is empty and the legal targets are root circuit instances
and their descendants. Targeting the entire owning canvas is not a special
exception to the sibling rule. A whole-design DUT can be represented as a
component instance alongside the bench. Independent whole-canvas verification
workflows continue to use their ordinary canvas target contract.

### One or more targets

Start with exactly one primary DUT target. If multiple targets are exposed,
additional targets must be explicitly listed and independently satisfy the same
containment rule. Avoid an implicit all-siblings mode. Reject duplicate targets
and ancestor/descendant overlap among separately instantiated DUT targets so a
child circuit cannot be instantiated twice. Deep observations within a primary
DUT belong in explicit probe bindings, subject to adapter support.

The harness contains selected target instances with their resolved parameters
and the explicit bench bindings needed to connect them. Additional sibling DUTs
require explicit harness interconnections. The engine must not silently widen
execution to the entire enclosing circuit or infer harness wiring from graphical
proximity. Missing clocks, supplies, models, bindings or unsupported observation
paths produce named readiness diagnostics.

### Bench kind and participation

Supported bench kinds should be `spice`, `hdl`, and `cocotb`, with operation
availability reported separately. A SPICE bench selects one or more supported
analyses and owns test-only sources/loads, stimulus and measurement statements.
An HDL bench uses the canvas's selected, qualified HDL. A cocotb bench is Python
test source attached to a qualified HDL simulator and DUT interface. Upstream
[cocotb's Quickstart](https://docs.cocotb.org/en/v2.0.0/quickstart.html) separately
identifies HDL design sources/top and Python test modules, supporting distinct
DUT and bench source roles.

A testbench is a verification participant, not part of the fabricated circuit.
Ordinary production netlisting, synthesis and layout exclude the bench, its
test-only supply sources and stimulus devices. A verification run assembles a
harness containing the chosen DUT closure plus those test-only elements. Merely
placing the bench symbol or drawing a decorative connector never injects it
into production connectivity. The engine owns actual target/port bindings.

### Template generation and saved source lifecycle

1. Keep unfinished testbench placement as transient client state. Commit the
   configured bench, saved source and legal target in one atomic edit transaction.
2. Choose bench kind and explicit target occurrence(s). The generator resolves
   their parameterized canonical interfaces and relevant view mappings in the
   current snapshot, then offers a suitable source template. Missing supported
   mappings are diagnostics, not guessed port order.
3. Save the adopted template as an ordinary editable project-owned source asset
   linked to the bench. Store generator identity/version/digest, target
   occurrence/interface signature and source revision as provenance.
4. Engineers edit that saved code in the general text editor. A run consumes
   the saved source revision. It does not silently regenerate source first.
5. Regeneration produces a preview or a new candidate asset/revision. Replacing
   the saved asset requires an explicit adopt action with its expected source
   revision. Never overwrite user edits merely because a target or parameter
   changed.

An adopted generated template is authored project source. Its generator origin
does not make the editable saved file disposable run exhaust. Generated solver
configs, temporary wrappers and derived netlists remain run artifacts.

### Target evolution, structural edits and replay

Target references follow stable working instance identities; a normal new run
resolves and freezes their current revisions. Template provenance records the
interface used when the source was created, not a permanent instruction to run
an old DUT revision. Existing run records/replay use their original input lock.

Renaming an instance does not alter a stable-ID binding. Deleting or moving an
instance can make a bench target unresolved or out of scope. Preserve the bench
and its saved source, expose the invalid binding state, and reject execution
until the engineer explicitly repairs it. Do not select a replacement instance
with the same name, silently clear source code or widen scope. An explicit
retarget operation validates containment against the proposed post-edit graph.

Interface changes mark affected template/binding signatures stale and report
the exact removed/changed pins, widths or terminal order. A revision change with
an unchanged compatible interface does not itself require rewriting the bench.
Moving a bench to another scope cannot silently reinterpret its relative target
path; the move must preserve a still-legal binding or expose the need to retarget.

For I28, each admitted run freezes the exact testbench occurrence, source files
and their executable dependencies, resolved DUT occurrence paths/configuration,
canonical interface and port mappings, selected source/model views, harness
bindings, `canvas.toml` and references, PDK/technology/decks, seeds and complete
compiler/simulator/profile identities. Child-target closure is exact; absent
scope support fails instead of becoming a parent-canvas run. A saved result is
current only for its consumed inputs; changing the bench or DUT never rewrites
the old evidence.

### Required contract probes

- A sibling target and a nested target under a sibling resolve successfully.
- Self, parent, cross-project, annotation, bench and ancestor-peer targets fail.
- Two occurrences of one reusable definition resolve their own relative paths.
- A rename preserves binding; a delete/reparent exposes an invalid binding.
- Regeneration cannot overwrite edited source without explicit revision-checked
  adoption; replay continues to use the original source and DUT snapshots.
- SPICE terminal order, HDL width changes and missing physical/model mappings
  produce precise diagnostics; no drawing operation creates hidden connectivity.
- Production synthesis/netlisting excludes bench stimulus; bench execution
  includes only the declared DUT/harness closure and returns its pinned target.


Final-contract clarification: unfinished placement is transient client state. The committed testbench requires an explicit target; returned records require saved source, interface digest, binding state and bindings. Presets fill only missing source/view slots and preserve supplied links. The shared SPICE analysis schema also includes qualified Xyce harmonic balance.
