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

## Agent verdict (schematic lane, 2026-11-03)

Landed, TDD RED->GREEN (42 failures on missing modules -> 42 green
in the owned set; `tests/project` + wire suites: 171 passed,
1 skipped, no regressions; docstring guard exit 0):

- `src/project/schematic/sheets.py` — Sheet entities ({name,
  title}); unique names; delete refuses `sheet_in_use`.
- `src/project/schematic/instances.py` — Instance entities
  ({sheet, symbol, x, y, rotation, mirror, properties, ref});
  bare symbols must exist (`unknown_symbol`), scoped
  `pdk:/lib:/pkg:` refs pass through untouched.
- `src/project/schematic/hierarchy.py` — Hierarchy bindings
  ({parent_sheet, child_sheet, instance, port_map}) plus
  children/parent/tree/path navigation queries.
- Tests: `tests/project/test_schematic_{sheets,instances,
  hierarchy}.py` (FakeEntityStore seam, same shape as the
  WIRE-PLACE fake).

Connectivity reuses the WIRE-PLACE net authority — no second
implementation. I28 pinning (symbol/cell revisions, port-map
revision in run closures) belongs to the surface lane.

Engine-wiring seam (NOT edited here — surface lane owns
`composition.py`/`vocabulary.py`): wire ops `create_sheet`,
`rename_sheet`, `delete_sheet`, `place_instance`,
`move_instance`, `rotate_instance`, `mirror_instance`,
`set_instance_properties`, `set_instance_ref`,
`delete_instance`, `bind_block`, `set_port_map`,
`unbind_block` as submit-immediate CRUD-style ops, and queries
for sheet/instance/hierarchy reads.
