# Vendored fixture: cspdk

- upstream: https://github.com/gdsfactory/cspdk
- pinned rev: `3323b17b4d75c852ed2372d7d13239408cca0eb1`
- license: MIT
- domain: P

## Documented results (what 'correct' means)

CORNERSTONE photonics PDK (gdsfactory); ships cells + reference GDS + regression tests + design guidelines. Correct = the reference si340 MZI GDS (tests/gds_ref_si340/mzi.gds) passes the documented CORNERSTONE min rules (GDS 3/0: 350 nm feature, 200 nm gap; 49th-call guidelines section 5.3-5.4) under the engine KLayout DRC check; upstream test_gds difftests each cell against its reference.

Fetched by `scripts/fetch_fixtures.py` (FIXTURE-FETCH). Do not hand-edit the tree under `cspdk/`; re-pin by updating `FIXTURES` and re-running the fetch.
