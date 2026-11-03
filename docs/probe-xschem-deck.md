# Xschem schematic deck probe (DECK-XSCHEM, 2026-11-03)

Adapter: `src/adapters/xschem/` (`XschemAdapter`, operation
`run_xschem`, tool `xschem`). Verified against XSCHEM V3.4.8RC
(`/usr/local/bin/xschem`, sharedir `/usr/local/share/xschem`).

## Recipe (what the adapter runs)

`xschem -x -q --rcfile <wrapper> -s -n <sch> -o <outdir>
-N <name>` plus `-f` (flat), `-S` (schematic-owned sim),
`--command/--script`. `DISPLAY` is scrubbed (forced text mode);
the wrapper pins `XSCHEM_SHAREDIR` to the real install, sources
the project rcfile, and re-pins. Version assert on `xschem -v`
(`XSCHEM V3`, else `missing_dependency`); init failure
(`Tcl_AppInit() err` / unloadable `xschem.tcl`) and missing
output both refuse loudly — never fake-green. Verdicts come
from artifacts and logs, never the exit code (xschem exits 0 on
silent init failure and nonzero-with-output on netlist errors).

## Byte-compare fixture

`** sch_path` / `** sym_path` headers embed the checkout path,
so `normalize_netlist` reduces them to basenames before compare.
A minimal self-contained schematic netlists byte-identically
across runs (`test_xschem_netlists_mini_to_recorded_bytes`;
normalized output contains no checkout paths). No PDK symbols
are needed for the pin.

## Sim seam (`-S`, schematic-owned)

Implemented and parsed: `-S` output logs scan for sim failures
as `xschem_sim_fail` violations. PDK-owned sims (sky130 models)
are BLOCKED on this host (no PDK store) — the seam is pinned
by log-parse units, not by a live PDK sim.

## Open seams (not this wave)

Vocabulary operation + composition/MCP wiring (`run_xschem`
is not in `src/interfaces/vocabulary.py`); contract/api_spec
regen (blocked on another agent's in-flight `composition.py`
breakage — recorded, not caused here). Engine wiring belongs to
the owning surface; the solver + fixtures + probes are done.
