# ADR-012: Always-editable layer catalog with separate process bindings

*Status: accepted; partially superseded by [ADR-013](013-magic-aligned-technology-driven-layout.md) (2026-11-01) | Refines: [ADR-011](011-one-runtime-durable-admission-and-client-neutral-operations.md) | Evidence: [Magic VLSI source dissection](../../../PRD/tools-research/magic-vlsi-source-dissection.md), [vision alignment review](../work/E2E-REREVIEW/vision-alignment.md)*

**Amendment note:** ADR-013 records the user's withdrawal of the no-PDK/default-palette requirement. The editor, durable geometry operations, stable identities, I28 provenance and shared client operations remain required; only the promise of a paintable process-like palette before resolving a technology profile is superseded.

## Context

RocketEDA's product is an editable schematic and layout workbench for ASICs, combining familiar KiCad, Xschem and Magic workflows. Users must be able to draw physical geometry and create/edit schematics, symbols and cells before selecting a foundry PDK. The same operations must be available to the IDE, MCP and scripts through one engine runtime.

The current engine has PDK-derived stackup/layer-serving and cell-placement foundations, but it has no general editable layer catalog or typed geometry CRUD. Its current layer surface is not a layout editor.

Magic VLSI source was reviewed at commit `eeb10525abfd1c1d06fad8f2270f2b4c6864de06`. Magic's usable bundled SCMOS technology allows editing without a foundry PDK, but physical layer types and process behavior come from the selected technology file. Its `minimum` fallback has no physical layer types. Magic therefore validates the no-foundry-PDK requirement while also showing that the usable technology profile and process semantics are separate from the editing database. RocketEDA's process-independent layer identity is a deliberate product choice, not a direct copy of Magic's technology lookup model.

## Decision

1. **Every project has a usable, editable baseline layer catalog.** The engine provides a baseline palette for layout drawing and saving even when no PDK is selected. Projects may add named layers. Layer identities are stable, versioned project data; names, colors, display order and aliases do not serve as object identity.
2. **PDK data extends and binds process meaning; it never gates drawing.** A PDK may contribute additional layer definitions and versioned bindings from RocketEDA layer identities to process layer/purpose. Existing project layers and geometry remain editable if a binding is absent. A binding may add process semantics without silently replacing the authored identity.
3. **Process capabilities are distinct from drawing capability.** Connectivity/contact semantics, paint-overlap rules where required, DRC, extraction, manufacturing grids, derived mask geometry, and GDS/OASIS export are enabled only by the relevant pinned process data and tool capabilities. A simple output layer/datatype mapping is sufficient only for direct mappings; profiles may need derived geometry recipes and other technology rules. Unsupported or unmapped work is reported explicitly.
4. **The shared engine owns layout mutations.** IDE, MCP and scripts use the same documented, revisioned operations for shape creation/edit/deletion, layer management, placement and transforms. The vocabulary includes at least rectangles, polygons, paths and labels. Scripted GDSFactory calls may be an additional route, but cannot substitute for interactive editor operations.
5. **I28 pins all consumed design and process inputs.** Project revisions include the layer catalog, authored geometry, view links and cell identities. A replayable operation/run pins its project revision, the versioned `canvas.toml` and contained references, resolved settings, and any PDK binding/profile revisions, grids, rules or export recipes it consumed. `canvas.toml` remains the design-intent/tool-settings file; this decision does not move geometry into that TOML file.
6. **Coordinate systems are explicit and extensible.** Store authored geometry in a stable integer or exact internal coordinate system. Keep display snap/grid separate from process/manufacturing grid and feature-size scaling. A PDK may constrain or convert coordinates for process operations; it does not make the geometry uneditable.
7. **Layer counts are not a small fixed enum.** RocketEDA uses stable extensible identifiers and documented practical resource limits. Magic's current 256 tile-type and 64 plane limits are its implementation choices, not RocketEDA requirements.

## Alternatives considered

1. **Show only PDK-enabled layers.** Rejected because layout drawing is a required editor capability and must work before a PDK is selected.
2. **Use the active PDK's names as permanent design identity.** Rejected because this makes project geometry technology-dependent and complicates multiprocess projects, migration, and generic user layers.
3. **Treat the layer map as only a GDS layer/datatype lookup.** Rejected because process behavior may also need connectivity, contacts, grids, DRC/extraction rules and derived geometry.
4. **Require GDSFactory scripts for layout authoring.** Rejected because scripts and generated layouts do not provide interactive shape editing, selection, move/transform/delete, or equivalent operations from every client.
5. **Copy Magic's technology type tables and limits directly.** Rejected because RocketEDA needs stable project identities and an extensible catalog across multiple PDKs and domains.

## Consequences

- Positive: users can create/save layout geometry without a foundry PDK, and PDK selection adds process capability without disabling the editor.
- Positive: every adapter acts on the same project-owned layer identities, geometry revisions, and validation path.
- Positive: replay can identify exactly which catalog, geometry, `canvas.toml` settings and process semantics a run consumed.
- Negative: the engine must implement layer catalog persistence, geometry CRUD, coordinate/unit contracts, client-neutral editing operations, and migrations before the layout editor is ready.
- Negative: PDK integration needs richer versioned capability data than a layer stackup or direct GDS mapping alone.
- Current readiness: not implemented. Existing layer serving and `place_cell` do not fulfill this decision. See the [source-based comparison](../../../PRD/tools-research/magic-vlsi-source-dissection.md) and [vision alignment review](../work/E2E-REREVIEW/vision-alignment.md).
