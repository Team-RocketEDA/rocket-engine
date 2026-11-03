# DECK-XSCHEM: schematic to netlist to sim execution deck

*Status: Ready · Depends: none · Size: M ·
Roadmap: execution decks (MVP track)*

## Why

Execution decks are adapters that run a fixed
multi-step flow behind one button (digital_flow and
cosim are the pattern). The schematic side has no
deck: xschem is provisioned and headless-capable
(`-x` no-X, `-n -s` batch SPICE netlist,
`-N/-o` output control, `-S` batch simulate,
`--command/--script` Tcl, `--rcfile` pinned config,
man page verified on XSCHEM V3) but no adapter
exists. MIXED-TOP-TRIAGE's "xschem top-LVS" waits
on it.

## What

- `xschem` adapter: schematic → SPICE netlist
  (project-pinned rcfile, explicit output paths),
  feeding ngspice/Xyce runs and schematic-side LVS.
- `--command` seam for scripted flows; `-S` where
  the schematic owns the sim.
- Duplex like every deck: findings + measurements
  + native log excerpts back through the verdict
  path; version-assert the binary (V3 family).
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- A project schematic netlists to byte-comparable
  SPICE vs the recorded fixture (test pins).
- Deck mode reachable via submit/MCP like every
  other deck; missing xschem fails loud with the
  PROV remedy, never fake-green.

## Verdict (Wave-2, 2026-11-03) — Ready, Engine wiring to Wave-3

Adapter complete: run_xschem with wrapper-rcfile seam, V3 assert,
loud failures, normalized byte-compare; ota_top.sch netlists live
(3260 B). Engine wiring (vocabulary/composition/MCP + regen)
carries to the Wave-3 surface lane.
