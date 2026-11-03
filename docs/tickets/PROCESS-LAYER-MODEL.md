# PROCESS-LAYER-MODEL: Versioned technology semantics and export recipes

*Status: Ready · Depends: LAYER-CATALOG, LAYER-SERVING, PDK-STORE · Size: L · Roadmap: editor core*

## Why

An editable layer name or direct GDS layer number is not enough to establish process behavior. Magic models contacts, overlap/compose, connectivity, process grids, DRC/extraction and derived CIF/GDS geometry in technology data. RocketEDA needs a versioned technology-profile model that distinguishes editable project geometry from the process semantics needed for checks and fabrication output.

## What

- Define versioned technology-profile-to-project layer bindings, including process purpose, stack order, units/grid and supported drawing/export rules.
- Represent contact/residue and connectivity relations separately from visual grouping and layer visibility.
- Represent process-specific overlap/composition behavior and validation rules where the selected backend supports them.
- Support direct GDS/OASIS layer/datatype maps and declarative derived geometry recipes where a PDK/backend requires them; identify unsupported recipe operations.
- Bind DRC, extraction and export capabilities to exact technology-profile/deck/tool versions. No name-based guess or silent layer drop may imply a valid result.
- Show process capabilities per technology profile/canvas. Missing checks or export support must remain explicit, and every consumed profile capability is pinned into I28.
- Keep each parser, semantic model and exporter adapter below the 3,000-line module ceiling.

## Acceptance

- A layer map reports exact source, version/hash, unit/grid interpretation, destination layer/purpose and capability state.
- A design with mapped layers can run applicable connectivity/DRC/extraction/export paths and reports the exact process profile/deck used.
- A missing contact, rule, grid or output mapping produces a named unsupported/incomplete result and leaves authored geometry intact.
- Derived-output recipes are deterministic, revision-pinned and round-trip validated against a reference layout; unsupported transformations fail loudly.
- Source and generated output provenance are included in I28; no adapter may invent process semantics from display names.

## Verdict: GREEN (2026-11-03)

- Implemented `src/project/process/model.py` (versioned `TechProfile` with source-hash/deck pin, capability gates returning supported/unsupported/incomplete, `probe_tool` for binary-gated backends) and `recipes.py` (deterministic derived-output recipes, round-trip validation, unsupported ops raise `unsupported_transformation`).
- Proved by `tests/project/test_process_model.py`: 3 passed, 1 loud skip — `opensta`/`librelane`/`klayout` absent on PATH probe `BLOCKED-needs-host`, never faked green; no network/docker daemon used.
- Engine-wiring seam for the surface lane: pin profile label + source hash + deck into I28 ingredients; surface DRC/extraction/export as capability-gated Engine ops that return these verdicts verbatim.
