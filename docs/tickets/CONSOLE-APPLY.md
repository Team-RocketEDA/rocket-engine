# CONSOLE-APPLY: Session apply-context (strategic pivot)

*Status: Ready · Design: [ADR-016](../adr/016-console-apply-context.md) · Created: 2026-11-03*

*Strategic pivot: do this first, before further console/editor
slices. It replaces the bespoke exfil matrix with one route all
later scripting work rides on.*

CONSOLE-APPLY work ticket for the atomic session apply-context
(ADR-016): explicit with-block, atomic exit, scratch outside,
shared per (console, generation). Replaces
ConsoleTools/ConsoleNamespace exfil matrix.

## Goal

One explicit, session-owned apply-context through which every
scripted edit lands: `with project.edit(label):` records
intents via ~6 sink primitives and commits them atomically on
clean exit; exceptions drop everything; outside the block all
script output is scratch.

## Scope

- Context object owned per (console, generation), bound into
  the prelude for all clients (MCP, stdio, IDE); reset retires
  it. Nesting bubbles inward-out, outermost exit submits.
- Sink set (fixed) with pinned argument types
  (gdsfactory 9.51, verified; see ADR-016):
  - `project.cell(component: gf.Component, name: str)` — the
    only component sink. Hierarchy preserved via
    `insts`/`each_inst`, shapes via `get_polygons`, layers via
    `layers`, pins via `component.ports` with names.
    `gf.Instance` is never a direct argument (always
    parent-bound — pass the parent `Component`).
  - `project.place(cell, x, y, ...)` / `project.instance(...)`
    take a cell handle or name plus transform, never a gf
    object graph.
  - `project.rect(layer: LayerSpec, bbox)`,
    `project.path(points, width, layer)` (also accepts a
    `gf.Path`), `project.wire(...)` take plain data plus
    `gdsfactory.typings.LayerSpec`.
  - Every `LayerSpec` resolves against the canvas PDK's layer
    catalog at exit; unknown layers fail loudly. Unit asserts
    sit at the sink boundary (schematic units in, asserted
    once; dbu conversion asserted inside the engine).
- Canvas PDK auto-activated at context entry and exposed as
  `project.pdk` (dev convenience that kills the side-venv
  habit: without activation even `gf.components.straight()`
  raises `No active PDK`). Every landed intent records PDK +
  model provenance, feeding the IpLink/per-PDK chain.
- Exit submits one `apply_transaction`-shaped batch (envelope
  identity, one revision). Exception path returns error plus
  discarded intents. Outside-block sinks return scratch shape
  + one-line hint, never persist.
- Approval binds the batch at exit (I22). Read-only sessions
  refuse block entry loudly.
- Migrate prelude content and route/console tests to the
  context path in-slice; remove the replaced route modules
  (no parallel exfil paths left behind).

## Non-goals

- No vocabulary change (internal route change only).
- No worker/runner/sandbox change (Step 9 substrate untouched).
- No mid-cell streaming upgrade (block-exit apply first; sink
  API stays streaming-compatible for later).
- No new PDK/gdsfactory bindings (sinks take gf objects as-is).
- Out of scope (consumers of landed data, separate engine
  work): netlister differentials, extraction clicks.

## Acceptance (TDD RED first)

- RED: entering + clean exit lands one revision containing
  exactly the recorded intents; exception lands nothing
  (store diff empty) while returning error + discarded intents.
- RED: outside-block sink calls persist nothing and keep
  return shape; nested blocks submit once at the outermost
  exit; reset retires the context (entry afterwards fails).
- RED: exit batch carries the console envelope identity;
  approval binds the batch, never the entry.
- RED: sink type table enforced — `cell()` takes a
  `gf.Component` (hierarchy preserved via `insts`, shapes via
  `get_polygons`, pins via `ports` with names); `Instance` as
  a direct argument is refused; unknown `LayerSpec` fails
  loudly; unit asserts fire at the sink boundary.
- RED: canvas PDK auto-activated at entry and exposed as
  `project.pdk`; every landed intent records PDK + model
  provenance; exit receipt carries entity ids + revision +
  per-intent results (oracles, not bare OKs).
- Full suite + gate green; `git diff --check` clean; replaced
  modules removed with their tests migrated, none orphaned.

## What this replaces

See ADR-016 (evidence-backed inventory): `ConsoleTools`,
`ConsoleNamespace`, tier-2 verb tables, per-call admission in
`console/route.py`, exfil-shaped prelude content. Kept:
envelopes, ledger admission, lifecycle rules, worker substrate.

## Design influence

`waveform-generator/docs/layout-engine-feedback.md` (agent
tapeout review) ranks the hurdles this answers: verifiable
exit evidence, provisioned-env-only consoles, sink-boundary
unit asserts, named pin capture, PDK+model provenance,
catalog-resolved layers, escape-hatch console with
atomicity + `rewind` as the undo story. Details in ADR-016.
