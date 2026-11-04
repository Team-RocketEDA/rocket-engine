# gdsfactory maximal replacement map

*Date: 2026-11-04 · Method: 7 parallel researchers, maximalist
hypothesis steelmanned then falsified per tool-class against live
docs + [deep-dive](../../PRD/tools-research/gdsfactory-api-deep-dive.md)
+ [tool-matrix-recheck](tool-matrix-recheck.md). Companions:
[Plus parity](gdsfactory-plus-parity.md),
[GUI abstraction](gdsfactory-gui-abstraction.md).

Verdict: gdsfactory absorbs ~4 narrow roles outright (~10–15% of
engine tool roles), usefully augments ~10–12 more, and can never
touch the load-bearing verdict roles.

## REPLACE (absorbed outright)

- **SPICE netlist export/format conversion** — vlsir to
  Spectre/Xyce/ngspice + `get_netlist`/`get_l2n` extraction.
  Conversion only, never simulation.
- **Scripted polygon/GDS libs** (gdspy/phidl-style) — faster via
  KLayout C++ backend; `write_gds`/`import_gds`/booleans.
- **GDS-diff evidence** — `gf.diff`/`DiffResult` per-layer XOR/IoU +
  `gf diff` CLI rendering in KLayout.
- **Photonic circuit solvers** — SAX (freq-domain) + Circulax
  (transient/HB), pip-installable, shared API.

## AUGMENT (backend still required)

Schematic intent (code-driven only; capture stays Xschem);
scripted layout + generic DRC/XOR/density authoring (foundry decks
stay KLayout); connectivity compare (toy-demo grade, not device
LVS); top-level die/mask assembly + PnR-block import (no
legalize/CTS/PDN/fill); viewer panels (KWeb/GFViz preview-only);
Pdk registry object (dict only, no persistent catalog); EM/FEM
adapter prep (solvers/meshes/accounts external).

## NO (hard boundaries)

- Numerical solvers: ngspice, Xyce (parallel/HB/PCE/SENS), CACE
  corners/MC/datasheets, PySpice driver.
- Digital implementation: Yosys, Verilator/Icarus/GHDL, OpenSTA/RCX,
  OpenROAD/LibreLane, sby/eqy formal (VLSIR: `NotImplementedError`
  for Verilog).
- Foundry authority: Magic extraction, Netgen device LVS, PEX,
  antenna/density, signoff.
- Interactive editors with save-back (headless policy).

## Consolidation moves (engine)

Collapse onto gdsfactory: SPICE export (vlsir standard, drop
bespoke converters); scripted-geometry helpers (retire gdspy/phidl
APIs); diff evidence (`gf.diff` + CLI); photonic solvers (SAX +
Circulax defaults); generic pre-check helpers. Keep native: all
simulators/solvers of record, synthesis/PnR/STA/formal, foundry
authority, interactive capture/edit, EM/FEM backends + accounts,
persistent IP catalog/evidence layer.

## Potentials (unexploited)

Code-driven schematic-intent → layout compilation; LayerStack as
unified assembly path; `gf.diff` + `count_drc` as CI regression
evidence per stream-out; vlsir multi-target fan-out; SAX +
ray-tune/PSO optimizers for photonic sizing; dataprep + preview
panels for browser review.

## Gaps

KWeb save-back; GFViz license/hierarchy fidelity; vlsir ngspice-matrix
blanks; SKY130 SPICE-helper FIXME; antenna/ERC coverage; live pin
drift (gplugins 2.1.5 vs inspected pins).
