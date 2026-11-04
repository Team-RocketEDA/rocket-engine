# ADR-018 (Draft): Job-named tool adapters, driver layer, button-driven engine API

**Status:** Draft — Q1 settled by owner; Q2+ open. Interview ongoing under
the grill skill; implementation is NOT authorized by this record.

## Settled (owner-confirmed)

1. **Tools are named by the job/measurement, not the library.** `sax/`
   today is a wavelength-sweep transmission spot-check wearing a
   library's name; it cannot do phase, group delay, S-export or
   transient. Names must promise what the module delivers
   (e.g. `tools/optical/sweep.py`, `tools/spice/tran.py`).
2. **Two layers.** Measurement tools assemble the deck, run it, and
   return data + verdict, inheriting the `ToolAdapter` port. Raw
   libraries (sax, PySpice, meep-Python) drop to a shared `drivers/`
   layer with no verdict logic. Sweep and transient stop duplicating
   circuit-building; PySpice replaces ngspice stdout-parsing in one
   place.
3. **Raw libraries need no adapters.** A library gets a driver iff two
   or more measurement tools share it; otherwise the tool calls the
   library directly. No one-file-per-library shims.
4. **Bespoke runs stay in the execution console.** Anything that is not
   a repeatable one-off measurement is a user/agent script against the
   project context (proposed: `with project.run...`), not a new tool
   module. This is what stops the tools tree regrowing.

## Scope of this interview (owner-widened)

- `adapters/` + `clients/` + `interfaces/` taxonomy and naming.
- kicad-dissection button list → engine API shaping (which buttons earn
  engine operations).
- SDK-deployability principle (importable engine, zero-backend-cost
  PyQt6 in the far future).
- Queued after acceptance (NOT authorized yet): (1) augment
  `PRD/tools-research/frontend-requirements.md` + sitemap against the
  wireframe; (2) engine tickets from the insights.

## Unresolved

- U1: Deck-sourcing rule — PDK-supplied vs repo-pinned vs
  user-scripted decks per tool (klayout DRC already answers two ways;
  nothing else answers at all).
- U2-settled: Hybrid — DRC, LVS, UpdateLayoutFromSchematic are
  hardcoded non-negotiables; simulation runs live in the
  data-driven simulation tab; the deck registry is the catch-all.
  Actions carry placement tags (importance, editor, toolbar slot)
  plus in-engine SVG art; toolbar flavors: left = editor shell,
  right = drawing enablers + placers, top = translation + project
  management. "Get S-params" is a deck. (Evidence: docs/cre/ tab,
  template picker, Add-Model flow.)
- U2b-settled: Two-layer gating. Hardcoded slots are
  frontend-owned and gated by frontend-known project state
  (LVS is the only button blocked without a layout — no
  layout means no LVS, and the frontend knows that). Engine
  readiness governs at admission, not at the button: press
  with structural state present but inputs missing and the
  engine rejects with reason. Buttons never consult readiness
  to render.
- U2d: Every dissection button is a must-have; every drawing
  operation has a frontend-gesture → engine-commit (MUT) path.
  No draw op is gesture-only at rest.
- U2e: Buses carry mixed analog + digital members. Member refs
  need a domain tag; bit positions apply to digital members
  only; analog members carry role/label. Netlist export splits
  by domain (yosys JSON covers digital members).
- U2c: In-engine SVG art vs ADR-015 "engine never ships
  presentation" — reference or bytes? (Queued.)
- U3: SDK-deployability principle wording (what it forbids).
- U4: Whether `interfaces/` (contracts + schemas) becomes `ports/`,
  and where `clients/runtime.py` (existing shared `RuntimeClient`)
  sits relative to `adapters/clients/`.

## Context read

- `kicad-dissection.md` (78 lines): Global/Schem/Layout toolbar
  button inventory + hierarchy-nesting invariant (one canvas
  template, nested canvases).
- `PRD/tools-research/frontend-requirements.md` §§0–15 + wireframe
  `frontend-wireframe.html` v0.3: persistent schematic/layout
  canvases; on-demand code/GDS/plot tabs; DRC modal; sim page with
  deck buttons; `get_capabilities` readiness gating.
- `PRD/tools-research/frontend-tooling-spec.md` §§1–10: one
  `EngineRuntime`, `Engine.submit` admission boundary, coalescing,
  `deck.tool` solver selection, event log, `.sym`/generated-types
  handover, §10 status table.
- Code: `src/adapters/{sax,circulax,meep,ngspice,drc,lvs_netgen,
  hdl_sim,...}`, `src/clients/runtime.py` (`RuntimeClient` shared by
  all transports), `src/interfaces/` (ports + schemas).
