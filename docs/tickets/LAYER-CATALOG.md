# LAYER-CATALOG: Technology-resolved editable layer catalog

*Status: Ready · Depends: ENGINE-ECS, LAYOUT-SCHEMA, PDK-STORE · Size: L · Roadmap: editor core*

## Why

The completed `LAYER-SERVING` work supplies read-only PDK stackup data for display and 3D; it does not provide authorable project layers. Magic's tutorials and source show that the active technology supplies the paintable layer types and their process semantics. The user withdrew the requirement for a usable physical palette before a technology profile is selected. See ADR-013 and the Magic workflow blueprint.

## What

- Define stable, extensible layer/type identities with display name, aliases, purpose/category, color, order and visibility kept separate from identity.
- Resolve the paintable layer vocabulary from the canvas's versioned technology profile. The profile may represent a PDK or another explicitly supported technology; a process-like palette with no resolved profile is not a requirement.
- Allow explicit project-layer extensions where supported, but do not infer electrical, design-rule or fabrication semantics from their names. A profile may bind those layers to process purposes, rules, coordinate/grid limits and capabilities.
- Report each binding/capability as supported, missing or incompatible. Preserve project geometry if a binding is absent; process operations that need missing semantics report unsupported/incomplete.
- Pin layer-catalog and binding revisions with project state and I28 run ingredients; keep `canvas.toml` as targets/tool settings, not a container for geometry.
- Split schema, persistence, mapping and queries into cohesive modules below the 3,000-line module ceiling.

## Acceptance

- A canvas with a resolved technology profile can list and edit that profile's layer vocabulary and any project extensions.
- A missing profile is visible during project setup and never causes saved layer/geometry data to be silently reinterpreted.
- A user-defined layer has a stable identity across rename, save/reload and geometry edits.
- Adding a PDK exposes its additional layers and mapping status without hiding or changing existing project geometry.
- A process operation with an unmapped layer returns explicit unsupported/incomplete evidence; drawing and saving still succeed.
- The run/project snapshot pins the layer-catalog revision and any consumed PDK binding; drift is named on replay.
- All exposed operations use shared Engine/MCP/client schemas and expected-revision conflict behavior.

## Verdict: GREEN (2026-11-03)

- Implemented `src/project/layers/catalog.py` (stable lids across rename/save/reload, revision pinning, missing-profile `setup_visible`, `attach_profile` never moves geometry), `presets.py` (built-in viewer presets), `bindings.py` (supported/missing/incompatible per-layer states, loud unsupported verdicts that leave geometry intact).
- Proved by `tests/project/test_layers_catalog.py`: 5 passed.
- Engine-wiring seam for the surface lane: bind catalog revision + profile pin into I28 run ingredients and `canvas.toml` targets; surface `list_layers`/`rename_layer`/`bind_layers` through the same Engine/MCP/client envelope with `expected_revision` conflict behavior.
