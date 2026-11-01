# SCHEMATIC-EDIT: Hierarchical schematic authoring operations

*Status: Ready · Depends: ENGINE-ECS, WIRE-PLACE, CELL-LINK · Size: L · Roadmap: editor core*

## Why

`WIRE-PLACE` supplies wire/junction and connectivity foundations, while `CELL-LINK` supplies symbol-to-cell linkage. Neither provides the complete project-owned editing contract needed for an Xschem/KiCad-style schematic editor. The engine must own durable model changes while any client owns its drawing gestures.

## What

- Define persistent schematic sheets, symbol instances, pins/ports, wires, junctions, labels, properties and hierarchy references with stable identities.
- Add shared revisioned create/edit/delete, move/rotate/mirror, property, wire endpoint and hierarchy operations; build on `WIRE-PLACE` net identity rather than a second connectivity implementation.
- Support project-authored symbols and references to immutable PDK/library symbol bytes without forcing edits into upstream libraries.
- Preserve block/subcircuit identity, symbol↔cell links, pin mapping and unit/canvas target scope under I28.
- Expose queries for hierarchy navigation, stable pin lookup, connectivity and symbol↔cell cross-probe so the frontend can draw/select visible pin-link strings; no adapter-specific drawing state.
- Keep modules cohesive and below the 3,000-line limit.

## Acceptance

- Create and save a multi-sheet hierarchical schematic with placed symbols, pins, named nets, junctions and port mappings through typed engine operations.
- Editing operations update connectivity through the shared net authority, and invalid/dangling connections are reported explicitly rather than dropped.
- Project-authored changes survive save/reload and are revisioned, attributed and replayable; PDK source symbols remain unmodified.
- IDE, MCP and script clients use identical validation and operation semantics.
