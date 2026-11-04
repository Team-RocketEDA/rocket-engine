# gdsfactory GUI abstraction (FULL / PARTIAL / NONE)

*Date: 2026-11-04 · Method: 8 parallel researchers over live docs
(gdsfactory 10.0.0rc1, gplugins 2.1.5, kweb 2.0.4, kfactory
latest-docs) vs reviewed v9.51.0 baseline, critic-falsified.
Companions: [Plus parity](gdsfactory-plus-parity.md),
[replacement map](gdsfactory-replacement-map.md).*

Headline: every gdsfactory surface is embeddable as a **viewer**;
none is an editor with save-back. RocketEDA must build its own
canvas on the data APIs. Three maximalist claims were tested and
all three falsified (details §4).

## Version baseline

Live docs track 10.0.0rc1/main vs our v9.51.0 baseline. Notable
deltas: native-kfactory cross-sections, `BendPortTypeError`
pre-route, `ExtrudeConfigConflictError` with generated-code preview,
PDK activation explicitly clears registered cross-sections /
enclosures / extrude configs. PDK wrapper pins diverged (CSPDK
~=9.51.0 vs SKY130 ~=9.48.0, no overlap → separate runner envs).

## Verdicts

**FULL: none** as an editor (FULL only as a viewer).

**PARTIAL** — embed as preview, build editing ourselves:

- Matplotlib plotting → read-only figure panel fed by
  `Component.plot()` / `to_dict` / `get_polygons`.
- KWeb browser viewer → embed FastAPI app in iframe for viewing
  only (`get_app(editable=False)`; save endpoint commented out
  upstream, no write handler).
- GFViz HTML schematic → embed `schemedit_html` preview; no code
  path back to netlist/YAML.
- Netlist graphs → render `plot_netlist()` figures; hierarchy
  navigation stays our work.
- Jupyter/ipywidgets → notebook-only; desktop builds its own
  canvas (pan/zoom/layer toggles exist, zero edit/save methods).
- Roundtrip-verify → safe for tapeout geometry, unsafe as editable
  source (arbitrary GDS doesn't reconstruct generators/intent —
  GUI must banner read-only import).
- Core primitives → cross-sections, LayerStack, polygons/booleans,
  `to_dict`, hierarchy, `@cell` factories all need code escape.
- Routing → 5 of 11 rows FULL-capable, 6 PARTIAL with explicit
  code escapes (raw router kwargs, all-angle tuning, tapers,
  obstacles, path-length sequences, global CONF strictness).

**NONE** — layout editing with save-back (core or plugins). No
surface ships write-back; build on `to_dict` / `get_polygons` /
`get_paths` / `write_gds` / `get_netlist` / YAML round-trip.

## Direct-GDS-editing answer

Safe GUI edits: geometry edits on our own canvas backed by data
APIs; export with `with_metadata`; write-then-reimport verified
by `gf.diff` XOR. Unsafe: treating imported arbitrary GDS as
editable source (generator intent lost). Diff/export story:
`gf.diff` metrics + metadata sidecar + auto-diff fidelity report;
generic DRC/LVS helpers as verification panel, foundry signoff
external.

## What must stay code

Own-canvas engine work; routing escapes (above); core-primitive
escapes (custom cross-sections, LayerStack semantics, scripted
booleans, complex params, `@cell` bodies, model callables, PDK env
separation); process rules (per-project isolated workers — PDK
activation is global state; PEX external; VLSIR Verilog disabled).

## GUI build order

1. Data-API canvas foundation (browser, hierarchy tree, draw /
   transform / layer tools). 2. Read-only preview panels
   (matplotlib, KWeb, GFViz, netlist graphs). 3. Import/export +
   roundtrip-verify + diff view. 4. Schematic/YAML/forms +
   extraction picker + kfnetlist viewers. 5. Routing dialogs,
   FULL-first, PARTIAL escapes with code-preview hatches.
6. PDK/version isolation last (browser, single-active switcher
   with clears-configs confirmation, isolated workers).
Throughout: failure-policy radio, requested-vs-completed
checklist, never treat exception-free return as success.

## Gaps

kfactory docs version number; `LayoutView(editable=True)`
persistence (no upstream path); schemedit WASM edit capability;
v9.51.0→10.0.0rc1 signature deltas; obstacle-avoidance runtime
beyond upstream discussion #2980.
