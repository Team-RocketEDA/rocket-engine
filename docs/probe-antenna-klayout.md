# KLayout-DB antenna path probe (ANTENNA-KLAYOUT, 2026-11-03)

Adapter: `AntennaKlayoutAdapter` in `src/adapters/drc/klayout.py`
(operation `run_antenna`, tool `klayout`). No foundry deck, no
`klayout` binary gate at check time — pure layout-DB region
math (`pya`/`klayout.db`, both importable in the project venv).
Openroad-standalone is deliberately NOT staffed (ticket
demotion; see `docs/tickets/ANTENNA-KLAYOUT.md`).

## Method

Islands = merged metal-region polygons over the resolved cell
(`cell` honored by scoping the walk; single-top default;
multi-top without a cell refuses loudly via the shared
`_resolve_cell_or_raise`). Per island: `ratio =
metal_area / gate_overlap_area`. No gate overlap ->
`antenna_floating`; ratio over `max_ratio` -> `antenna_ratio`
with the metric `bbox_um`. In-process, no artifacts written.

## Fixtures (runtime-generated, pya — no binary blobs)

Crafted one-cell GDS in `tmp_path`
(`tests/adapters/test_mixed_top_antenna.py`): balanced
metal-over-gate stays clean (ratio 1.0, cap 100); a 100000x100000
dbu island on a 100x100 gate violates with ratio and bbox; a
gateless island flags `antenna_floating`; a mixed cell reports
only the violator. Preflight pins bad ratios, missing GDS, and
the operation gate. All run hermetically — no skips on this
host.

## Boundary

A heuristic ratio check, not signoff: it names suspect islands
for the foundry deck to confirm (the deck itself is absent on
this host). Engine wiring (vocabulary/composition) belongs to
the owning surface, as with `run_xschem`.
