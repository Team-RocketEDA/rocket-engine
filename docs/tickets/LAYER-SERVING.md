# LAYER-SERVING: Layer stackup + preset serving for viewer + 3D

*Status: Ready · Size: M · Roadmap: convergence (MVP track)*

## Why

The layout editor's layer viewer and the GDS/3D tab can only
render what the engine serves: which layers exist, their
order, colors, stackup heights, and which are PDK-enabled.
Today the engine serves none of this — no layer table, no
stackup, no preset schema — so the frontend would have to
invent fab data, which is exactly the fabrication the
contract-first posture forbids. KiCad's Appearance panel
reads board setup and the 3D viewer's Z heights come from
the stackup adapter; our PDK profile must serve the same
role. This ticket turns the PDK from a file tree into a
queryable rendering authority and gives layer presets a
versioned home.

## What

- RED-first: engine `Stackup` schema served per PDK
  (read-only from PDK in MVP): ordered layers, metal/tech
  grouping, enabled set, colors, Z heights/thicknesses for
  the 3D adapter's scale normalize.
- `LAYER_PRESET{layers, renderLayers, flip, active}`
  schema mirroring KiCad's, with built-ins (All/None/
  All-metal/Top/Bottom) + user save/overwrite/delete and
  explicit apply.
- Query surface for viewer rows (visibility + color +
  active) driven by the same schemas; PDK remains truth,
  no user fork of the stackup in MVP.

## Acceptance

- sky130A serves a complete stackup; viewer rows + presets
  round-trip; 3D heights derive from served data, never
  frontend guesses.
- Contract + api_spec regen; full suite + gate green.
