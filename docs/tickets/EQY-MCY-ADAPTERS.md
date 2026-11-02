Problem: MVP tasks check.equivalence and check.mutation have ZERO adapter (eqy/mcy are provider gaps; frontends #4/#5).
Expected-per: contracts/v1/catalog/tasks.json (mvp); TOOL==FRONTEND review. Audit MC-07.
Actual-per: no eqy/mcy adapter anywhere in src/adapters/.
Fix: staff both — structured escapes already known (eqy DONE grammar + partition JSON per docs/tools/eqy.md; mcy SQLite db per docs/tools/mcy.md; audit KEEP-STRUCTURED rows). Highest-value adapter gap. Dump-first acceptance + good/bad fixtures.
