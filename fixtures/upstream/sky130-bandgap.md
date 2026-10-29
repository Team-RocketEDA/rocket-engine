# Vendored fixture: sky130-bandgap

- upstream: https://github.com/2amlogic/sky130-bandgap
- pinned rev: `1f470499ca83acd8d2a6a133e5a7f0878f158666`
- license: Apache-2.0
- domain: A

## Documented results (what 'correct' means)

sky130 bandgap reference; claims spec + xschem + ngspice + GDS + DRC/LVS reports. Correct = ngspice sims reproduce the spec'd reference voltage across corners; verify the claimed artifacts exist on fetch (efabless RDAC is the fallback if this canary is immature).

Fetched by `scripts/fetch_fixtures.py` (FIXTURE-FETCH). Do not hand-edit the tree under `sky130-bandgap/`; re-pin by updating `FIXTURES` and re-running the fetch.
