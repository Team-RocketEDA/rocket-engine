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

## Agent verdict (symbol/cell lane, 2026-11-03)

Landed, TDD RED->GREEN (owned-set failures -> green;
`tests/project` + wire suites: 171 passed, 1 skipped;
docstring guard exit 0):

- `src/project/symbols/symbols.py` — Symbol entities ({name,
  pins[{name, pin_type, x, y}], graphics, properties,
  revision}); create/copy/rename/revise; rename refuses
  `symbol_in_use` while instances reference the name.
- `src/project/symbols/cells.py` — Cell entities ({name,
  ports[{name, x, y, layer}], properties, revision}); same op
  shape; rename refuses `cell_in_use` while linkage
  references the name. No geometry duplicated across links.
- `src/project/symbols/linkage.py` — Linkage entities
  ({symbol, cell, pin_map, revision}) with CELL-LINK
  resolution semantics (explicit wins, identity default);
  `check_mapping` reports unmatched/conflicting pins
  explicitly; `pin_link_strings` renders visible
  `SYM.pin -> CELL.port` strings for the frontend;
  `resolve_mapped_pin` is the pin chokepoint.
- Tests: `tests/project/test_symbol_{defs,cells,linkage}.py`.

PDK bytes are never written — only project entities. I28
pinning of symbol/cell revisions plus the mapping revision
belongs to the surface lane.

Engine-wiring seam (NOT edited here): wire ops
`create_symbol`, `copy_symbol`, `rename_symbol`,
`revise_symbol`, `create_cell`, `copy_cell`, `rename_cell`,
`revise_cell`, `map_pins` as submit-immediate ops, plus
symbol/cell/linkage read queries and the pin-map/cross-probe
query surface.
