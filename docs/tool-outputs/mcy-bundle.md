# mcy (oss-cad-suite bundle) — sqlite DB plus output.txt (run_mutation)

Version provenance: `mcy` on PATH (oss-cad-suite bundle); no
`--version` banner (click CLI). Adapter
`src/adapters/mutation/__init__.py`.

## Report inventory

One phase per job: `mcy run` under the job timeout. Primary
results come from `database/db.sqlite3` via stdlib sqlite3
(verbatim SQL from mcy.py stats/tags/coverage readers);
`tasks/<uuid>/output.txt` `<idx> <RESULT>` rows stream
per-task verdicts before DB commit.

## Grammar

DB tables: `mutations`, `options`, `sources`, `results`,
`tags`, `queue`, `files`. output.txt: `^(\d+) (\S+)$`,
idx task-local joined via sibling input.txt. Parsed result:
`{total, violations[], coverage, source}` with `source` `db`;
uncovered rows yield `mutation_uncovered` errors.

## Exit states

- No results: `runner_unavailable`.
- mcy absent: `missing_dependency` with BLOCKED-needs-host.
- Exit 1 on any error incl. unexpected test value or bad
  output.txt line.

## Out of scope

`mcy list/source/status` stdout scraping (same data, weaker
typing); `[report]` stdout (user-defined, unparseable).
