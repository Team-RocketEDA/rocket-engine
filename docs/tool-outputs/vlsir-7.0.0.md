# vlsir/vlsirtools 7.0.0 — netlists plus SimResult (generate_views)

Version provenance: vlsir==7.0.0 + vlsirtools==7.0.0 pins
verified upstream; not in the provision script (audit pin+lock
stands). Adapter `src/adapters/vlsir/__init__.py`.

## Report inventory

Bindings for READING: `vlsirtools.netlist(pkg, dest, fmt)` emits
deterministic text (fixed header, no timestamps); sims arrive as
SimResult proto or numpy dataclasses. Execution of sim backends
stays subprocess; backends needed on PATH only for live sim.

## Grammar

SPICE: `.SUBCKT <name>` / `+ <ports>` / instances / `.ENDS`;
Xyce `;` comments plus `PARAMS:`; spectre `simulator lang`
plus analyses. Parsed result: `{total, violations[], source}`
with `source` `netlist` or `simresult`.

## Exit states

- Nonzero sim rc surfaces only inside SimError
  (.stdout/.stderr/.rundir) — never parsed into results on
  success.
- Unknown fmt: `invalid_command`.

## Out of scope

Simulator stdout scraping (unparsed by design); sweep/monte/
custom analyses (NotImplementedError in all drivers).
