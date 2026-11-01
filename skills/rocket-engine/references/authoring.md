# Project and component authoring

Use the project explicitly bound to the request; do not infer it from a mutable
active tab. Read the affected hierarchy occurrence, canonical ports, source/view
owners and revision before mutation. Query sources can be a PDK, IP library,
installed package such as GDSFactory, component, project hierarchy or entity.
Distinguish an uninstantiated factory from a placed circuit instance.

Circuit component presets share canonical identity:

- `spice_block`: pure SPICE subcircuit source with explicit ordered terminals;
  simulation-only by default, with physical views attached deliberately.
- `gdsf_component`: saved Python/GDSFactory factory, parameters, interface,
  symbol and managed layout. Generation materializes ports/geometry; discovery
  reads declarations without executing arbitrary factory code.
- `hdl_component`: digital source set/top in `canvas.toml`'s selected authored
  HDL, with elaborated ports and qualified synthesis/implementation support.

The HDL selection governs authored sources. Generated downstream Verilog is a
separate view, and does not mean the canvas has mixed authored languages.
Amaranth needs a qualified frontend; Hardcaml remains future capability.

Every circuit component has an honest SPICE-model availability slot. Primitive
device models, standard-cell subcircuits, Liberty timing and LEF/GDS physical
views serve different purposes. Missing SPICE can block relevant simulation
without blocking editing. Never create a placeholder model and call it real.

Use atomic typed edits with CAS for all touched/read mutable dependencies.
Create temporary IDs/references only where the request schema permits them;
the engine resolves these before storage. Stable port IDs and explicit bit/pin
maps connect symbol and physical cell ports. Source edits that invalidate an
interface must preserve/report stale connections, not silently delete them.

Graphics such as text, arrows, images, plots and measurements are annotations.
They never become electrical devices merely by touching a wire. Actual layout
geometry belongs to its physical cell and pinned technology/layer semantics.
Manual, generated and native-source views have explicit ownership.

## Testbench blocks

A bench has type `spice`, `hdl`, or `cocotb` and an explicit primary DUT. At
bench occurrence `P + [B]`, legal targets are `P + [circuit sibling] + descendants`.
Use stable instance IDs, not names, proximity or source filenames. Additional
DUT targets must be explicitly declared and their subtrees must not overlap.
Probes stay within a selected DUT. Do not silently include the parent circuit.

Placement and bench kind select a template using the materialized DUT interface.
The engine saves editable source, target-port bindings and template/interface
provenance. Unknown reset, power or port semantics are diagnostics, not guessed
stimulus. A regenerated template creates new source for explicit adoption; it
must preserve the user's edited bench. Hierarchy/interface/language drift marks
bindings stale and blocks execution until resolved. Test-only stimulus is
excluded from production netlisting and physical implementation.

## Full geometry scripting

Use real installed GDSFactory through the permitted local Python profile.
A scratch `gf.Component()` is ordinary native data; it becomes managed project
geometry only after explicit attachment/publication. A managed
`project.layout.edit(cell)` handle exposes a native component and commits at
its documented `publish()`/successful-context-exit checkpoints. Granular
project drawing helpers can issue immediate typed edits. Arbitrary mutations
to unmanaged Python/C++ objects are not automatically durable.

Saving reusable Python source and script entities keeps the work in the project.
Earlier committed edits remain after a later exception/cancellation; inspect
returned effects and child run identities rather than claiming whole-script
rollback. Do not write trusted result/verdict files from a script.
