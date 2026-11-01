# SYMBOL-CELL-EDIT: Editable symbol and physical-cell libraries

*Status: Ready · Depends: LAYER-CATALOG, LAYOUT-EDIT, SCHEMATIC-EDIT, CELL-LINK · Size: L · Roadmap: editor core*

## Why

The product needs KiCad-like schematic symbol and footprint/cell editors so engineers can create reusable components whose schematic and layout views stay linked. Existing byte-serving and `CellLink` resolution provide references, not authoring or synchronized view editing.

## What

- Add project-owned symbol definitions with editable graphics, pins, names, electrical pin types and properties; preserve upstream PDK symbol files as read-only inputs.
- Add project-owned physical cell definitions using the `LAYOUT-EDIT` geometry operations, with explicit ports, pin locations, properties and hierarchy.
- Define a durable component identity linking symbol, cell, source/model views and explicit symbol-pin-to-cell-port mapping; preserve `CELL-LINK` resolution semantics.
- Give schematic pins and physical ports/pads stable endpoint identities and locations. The frontend renders persisted mappings as visible pin-link strings, shows unmatched/conflicting pins, and cross-probes between the symbol and cell editors; this is a KiCad-style view feature layered over Magic-style layout operations.
- Pin symbol/cell definitions, physical port anchors/orientations and the mapping revision in I28 whenever a run or check consumes them.
- Support create/copy/rename/revision operations for reusable symbols/cells and references from block instances; do not duplicate geometry across links.
- Keep user-authored library files versioned, portable and covered by I28 when consumed by a run.
- Split symbol schema, cell schema, linkage and library persistence by responsibility, below the 3,000-line limit.

## Acceptance

- Create a component from scratch, edit its schematic symbol and layout cell, draw/map/cross-probe visible pin links between symbol pins and cell ports, instantiate it in a hierarchical schematic and place it in layout.
- Symbol and cell edits preserve the shared component identity and report unmatched or incompatible pins explicitly.
- Project-owned definitions save/reload and can be reused by another project through versioned references; PDK files are never modified.
- IDE, MCP and script clients can invoke the same documented operations; referenced views and mappings are included in I28 snapshots.
