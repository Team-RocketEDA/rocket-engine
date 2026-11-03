# eqy (oss-cad-suite bundle) — verdict file plus DONE (run_formal)

Version provenance: `eqy --version` prints `EQY v0.70-1-gfb8b211`
on this host; no eqy-specific provision pin (ships in the
oss-cad-suite bundle). Adapter
`src/adapters/equivalence/__init__.py`.

## Report inventory

One phase per job: `eqy <config>` under the job timeout.
Gating is the V1 verdict filename (`PASS`/`FAIL`/`UNKNOWN`/
`ERROR`), confirmed by the DONE line
`DONE \((PASS|FAIL|UNKNOWN|ERROR), rc=N\)`; per-partition S1
status rows plus partition JSON carry the table. Never imports
eqy.py (exit-unsafe).

## Grammar

DONE regex plus exit map (0 expected-verdict; 1 config/usage/
midrun-fatal; 2 FAIL; 4 UNKNOWN; 16 ERROR; 8 dead). Parsed
result: `{total, violations[], verdict, partitions[], source}`
with `source` `verdict_file`. PASS with no failed partitions is
clean; anything else yields `equivalence_fail` plus per-partition
rows.

## Exit states

- No verdict file and no DONE line: `runner_unavailable`.
- Never trust exit 0 alone in `--setup` mode (UNKNOWN rc=0).
- eqy absent: `missing_dependency` with BLOCKED-needs-host.

## Out of scope

Yosys child-log scraping (reduced to S1 by run.sh already);
`partitions/*.sby` inputs (never results).
