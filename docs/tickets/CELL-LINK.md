# CELL-LINK: Symbol↔cell linkage contract (CellLink component + resolvePin)

*Status: Ready · Size: M · Roadmap: convergence (MVP track)*

## Why

A custom block is useless until its schematic symbol binds the
layout cell that implements it — KiCad's symbol↔footprint
relationship, and the seam our custom-cell story stands on.
Today the engine has symbols (via `.sym` bytes) and cells
(via gdsfactory) but no link between them: no contract says
which cell implements a symbol, how pins map, or which cells
are legal for a picker. Without this, the symbol editor and
cell editor are two disconnected toys, and hierarchical
custom components cannot be built from the ground up.
PRD `frontend-requirements` §0 locks the shape and §13 Round 2
records the KiCad-derived design: copy KiCad, where the link
is plain text on the symbol, filters are advisory, and
variants alter resolution, never storage.

## What

- RED-first: `CellLink` component schema on the Block entity
  alongside `SymbolRef`: `cell: "pdklib:cell"` opaque string
  (LIB_ID analog, no write-time existence check),
  `pinMap: [{symPin, cellPin}]` ordered explicit with
  identity default for unlisted pins (single-target only),
  `cellFilters: [glob…]` (KiCad chooser semantics: OR, empty
  matches all, case-insensitive anchored wildcard, `:` splits
  lib from cell, space sanitized to `_`), `variantOverrides:
  {name: {cell?, pinEdits}}` sparse differentials with one
  default variant and REFERENCE immutable.
- Single resolution chokepoint `resolvePin(block, variant)
  -> cellPin`; run/export resolves `(cell, pinMap, variant)`
  per block instance and emits only when non-empty.
- Unknown/missing cell is a run error, never an edit error.
- Filters stored on the library symbol, advisory in the cell
  picker only; ERC collects `{cell text, filters}` for checks
  only, never enforcement.

## Acceptance

- Link → resolve → run round-trip green on a sky130A block
  with explicit, identity, and variant-overridden pins.
- Unknown cell fails the run with a named reason; editing
  stays free.
- Contract + api_spec regen; full suite + gate green.
