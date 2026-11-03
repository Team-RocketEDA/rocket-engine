# gdsfactory API map (engine module decisions)

What our pinned layout closure actually contains, so we know which
module to reach for — and which jobs live outside it. Sourced from
the v9.51.0 / v3.0.4 / 0.3.0 trees on 2026-10-28 (not memory).
Re-census on any bump; v10 reshapes gdsfactory entirely.

Env: `gdsfactory 9.51.0` + `kfactory 3.0.4` + `kfnetlist 0.3.0` +
`klayout 0.30.12` wheel (all via pip `layout`).

## gdsfactory 9.51 — framework + libraries (no LVS, no deck runner)

Top modules: `component`, `components/` (large PCell library),
`cross_section`, `routing`, `boolean`, `pack`, `grid`, `path`,
`pdk`, `technology/`, `generic_tech/`, `gpdk` (generic PDK),
`get_netlist`, `schematic`, `labels/`, `read/`, `export/`,
`write_cells`, `serialization`, plus utils (`snap`, `pack`,
`containers`, `difftest`, `watch`, `cli`).

Not present in the tree: no `lvs`, no DRC-deck runner.
`get_netlist` builds the *schematic-side* netlist from placed
components; nothing here compares it against extracted layout.

## kfactory 3.0.4 — layout backend (geometry, no LVS module)

Top modules: `kcell` (KCell/DKCell), `layout`, `layer`,
`instance*`, `port(s)`, `pin(s)`, `routing`, `enclosure`,
`cross_section`, `geometry`, `shapes`, `boolean`-via-regions,
`checks` (kdb DRC *helpers* for writing custom rules),
`technology/`, `schematic`, `serialization`, `merge`, `packing`.

Not present: no `lvs` module in 3.0.4. (Latest kfactory 3.5
advertises more LVS integration, but our env pins 3.0.4 via
gdsfactory — do not assume 3.5 APIs.)

## kfnetlist 0.3.0 — the connectivity-LVS piece

Rust-backed netlist schema + verification (zero Python runtime
deps): `Netlist` (instances/nets/ports, JSON ser/de),
`kfnetlist.extract` (hierarchical netlists from kfactory/klayout
cells — needs klayout), `detect_opens()`,
`find_net_difference()` (layout-vs-schematic compare),
`detect_shorts()` (geometric, needs klayout).

## Decision table: engine needs X → reach for Y

| Need | Module | Notes |
|---|---|---|
| Instantiate PDK PCells (gpdk, cspdk) | `gf.components`, PDK packages | generation-side, often dev-time fixtures |
| Read/write GDS/OASIS | kfactory, `gf.read`, `gf.export` | |
| Booleans, fill prep, XOR prep | `gf.boolean`, kfactory regions | |
| Custom (non-PDK) DRC rules | kfactory `checks` (kdb) | helpers only, not a deck runner |
| Schematic-side netlist | `gf.get_netlist` | from placed components |
| Layout connectivity extract | `kfnetlist.extract` | needs klayout |
| Opens / shorts / net diff | kfnetlist verify fns | connectivity LVS, no device params |
| PDK-deck DRC | NOT HERE → KLayout batch | stock binary, native |
| Device-level LVS compare | NOT HERE → Netgen | fed by Magic `.ext` (CMOS) |
| Photonic "LVS" | kfnetlist diff suffices | no transistors to recognize |

Rule of thumb: Python-importable geometry/netlist work lives in
this closure; anything executing a *foundry deck* or comparing
*device parameters* lives in a native batch tool (KLayout, Magic,
Netgen) behind an adapter.
