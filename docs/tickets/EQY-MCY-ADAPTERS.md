Problem: MVP tasks check.equivalence and check.mutation have ZERO adapter (eqy/mcy are provider gaps; frontends #4/#5).
Expected-per: contracts/v1/catalog/tasks.json (mvp); TOOL==FRONTEND review. Audit MC-07.
Actual-per: no eqy/mcy adapter anywhere in src/adapters/.
Fix: staff both — structured escapes already known (eqy DONE grammar + partition JSON per docs/tools/eqy.md; mcy SQLite db per docs/tools/mcy.md; audit KEEP-STRUCTURED rows). Highest-value adapter gap. Dump-first acceptance + good/bad fixtures.

## Verdict (adapt lane, 2026-11-03) — eqy/mcy Done

`src/adapters/equivalence/` (EqyAdapter, run_formal/tool eqy: V1
verdict filename plus DONE line plus partition rows; never imports
eqy.py) and `src/adapters/mutation/` (McyAdapter,
run_mutation/tool mcy: db.sqlite3 via stdlib sqlite3 plus
output.txt streaming rows) land dump-first with good/bad fixtures
in `tests/adapters/test_equiv*.py` and `test_mutation*.py`. eqy
v0.70 and mcy both present on PATH. Notes
`docs/tool-outputs/eqy-bundle.md`, `mcy-bundle.md`. Wiring seam
recorded, untouched.
