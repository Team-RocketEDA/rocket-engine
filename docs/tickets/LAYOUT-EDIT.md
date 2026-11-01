# LAYOUT-EDIT: Shared geometry create/edit operations for the layout editor

*Status: Ready · Depends: LAYER-CATALOG, ENGINE-ECS, CELL-LINK · Size: L · Roadmap: editor core*

## Why

The current engine can place cells and serve a PDK stackup, but has no general operation vocabulary for drawing or changing mask geometry. A generated GDS or viewer does not give users a layout editor. Geometry edits must use the active technology profile and pass through the same engine runtime from every client.

## What

- Add typed geometry records and revisioned operations for rectangles, polygons, paths and labels on stable layer identities.
- Support create/read/update/delete, copy, move, rotate, mirror, array/placement and property updates with explicit units and transforms.
- Keep project coordinate storage, UI snap grid and profile manufacturing grid separate. A profile's manufacturing grid may constrain process checks/export without silently changing authored geometry.
- Preserve cell hierarchy, stable object identities, cell-port/pin links, actor attribution, expected-revision conflicts and I28 provenance.
- Store physical cell-port/pad anchor coordinates and orientation so the frontend can place pin-link strings and cross-probe to the associated schematic symbol pin.
- Expose selection/query support sufficient for editors and cross-probing; keep rendering and gesture state in clients.
- Treat GDSFactory recipes and scripts as optional generation/back-end operations, never the only geometry-authoring route.
- Split shape schemas, geometry operations and cell placement responsibilities into modules below 3,000 lines.

## Acceptance

- With a resolved technology profile, a client can create, query, edit, save and reload rectangle, polygon, path and label geometry; project revisions and object identities remain stable.
- A missing or changed profile is reported explicitly; stored geometry remains inspectable and is never reinterpreted by layer name alone.
- IDE, MCP and scripts issue the same operation and receive equivalent validation, effects and evidence.
- Mapped and unmapped layers both accept geometry; process checks/export report missing mappings explicitly.
- Cell placement and transforms preserve ports, hierarchy and links to symbol/cell views.
- A stale expected revision fails without overwriting another edit; rewind/replay restores the geometry and provenance.
