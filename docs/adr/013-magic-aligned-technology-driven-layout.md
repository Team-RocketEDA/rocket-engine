# ADR-013: Magic-aligned, technology-driven layout editing

*Status: accepted (2026-11-01) | Supersedes: no-PDK/default-palette clauses of [ADR-012](012-always-editable-layer-catalog-and-process-bindings.md) | Related: [ADR-011](011-one-runtime-durable-admission-and-client-neutral-operations.md) | Evidence: [Magic tutorial workflow blueprint](../../../PRD/tools-research/magic-layout-editor-workflows.md), [Magic source dissection](../../../PRD/tools-research/magic-vlsi-source-dissection.md)*

## Context

The user withdrew the requirement that a new layout canvas must provide a paintable physical layer palette before a PDK is selected. The editor itself remains a required product feature: RocketEDA is still intended to provide interactive layout, schematic, symbol and cell editors.

Magic's tutorials teach a mature flow around an active technology: paint and edit geometry, work in reusable cell hierarchy, wire and route, check design rules, extract connectivity/devices, then exchange GDS/CIF. Its source and technology reference establish that the active technology defines paintable types and their process behavior. Magic ships usable example technologies, but its empty `minimum` fallback does not provide a useful physical paint vocabulary. A foundry PDK is not the only possible technology profile; however, the tutorials do not promise process-aware editing without a usable profile.

ADR-012 correctly requires durable geometry edits, stable identities, explicit process capabilities, I28 provenance, shared client operations and extensible catalogs. Its promise of a universal baseline palette usable before selecting any PDK is withdrawn.

## Decision

1. **The layout editor remains first-class and editable.** It must support geometry creation/editing, cell placement and hierarchy, labels/ports, selection/transforms, grid/snap, checks, connectivity, extraction and exchange through the shared engine vocabulary.
2. **A layout canvas resolves a versioned technology profile.** The profile defines which physical types can be painted and any supported paint composition, contacts, connectivity, process grid/scaling, design rules, extraction behavior and GDS/CIF/OASIS output recipes. The profile may represent a PDK or another explicitly supported technology. RocketEDA does not promise a useful physical paint palette for a project with no resolved profile.
3. **Keep project identity separate from profile names.** Persist stable IDs for authored layers/types and geometry. Names, aliases, colors, toolbar positions and external GDS layer/datatype numbers are metadata or mappings, not object identity. A technology profile may define a familiar alias such as `metal1`, but the alias alone does not provide electrical or manufacturing semantics.
4. **Allow explicit user/project extensions without inventing process meaning.** If a project adds a layer/type, keep it editable and visible when supported by the data model. Mark it process-unmapped until an explicit profile binding supplies the relevant semantics. Never infer conductivity, connectivity, DRC validity or fabrication output from its display name.
5. **Missing or changed profiles are visible state.** Preserve project geometry and make it inspectable. Disable or report operations that require unavailable profile semantics; never silently load the same name against a different profile and reinterpret the design.
6. **I28 pins the full technology and linked-view context.** Every check, extraction, generated view or export records the project revision plus the exact profile identity/revision/hash and any consumed layer bindings, grid/scaling, rules, recipes, decks, models, tools and resolved settings. When linked views are consumed, pin the symbol/cell revisions, physical pin-anchor coordinates/orientations and symbol-pin-to-cell-port mapping revision too. `canvas.toml` remains design-intent/tool settings, not a geometry container.
7. **Keep the Magic workflow, not its implementation ceiling.** Geometry edits remain revisioned, durable, and client-blind under ADR-011. Stable extensible layer IDs are required; Magic's fixed type/plane limits and corner-stitched storage are not.
8. **Schematic authoring remains a separate editor domain, with explicit cross-view links.** Magic is the reference for physical layout workflows only; schematic and symbol requirements continue to draw from KiCad/Xschem research. The frontend shows KiCad-style pin-link strings from schematic symbol pins to physical cell ports/pads and cross-probes either endpoint. The engine persists those mappings and exposes counterpart queries; the visual connector itself is frontend state, not a second design authority.

## Consequences

- RocketEDA no longer requires a universal default physical palette or drawing before a technology profile is selected.
- Project setup and layout canvases must identify the active technology and clearly show when it is missing, incompatible or incomplete.
- Layer catalog and geometry CRUD remain unimplemented work; removing the no-PDK condition does not make stackup serving or GDS generation equivalent to an editor.
- Technology, geometry, hierarchy, selection/editing, checks, connectivity, extraction and export are separate responsibilities and should stay in cohesive modules below 3,000 lines.
- The same operation contract continues to serve the IDE, MCP and scripts. I28 protects replay from profile drift.
- No change is made to the rule that unsupported process checks and exports must be reported honestly.
