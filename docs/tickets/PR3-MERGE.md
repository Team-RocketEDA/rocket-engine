# PR3-MERGE: Merge fuel-mcp-fixes (PR #3) with consolidation

*Status: Doing · Size: M · Roadmap: codesign*

## Why

A friend's PR #3 ("MCP agent path", branch `fuel-mcp-fixes`,
against 7h-old main) aimed the MCP surface at rocket_fuel's
repair loop. Half is now superseded by the sprint (submit
honesty, ProjectError catch, real revisions, some queries);
the other half targets holes still open today (caller-set
targets, measurements on PASS, four queries, server binding,
workdir hygiene). Merging blind would regress the sprint;
ignoring it wastes aimed work. So: merge with per-item
consolidation, in an isolated worktree, integrated after the
sprint lands.

## What

- In `/tmp/merge-fuel-mcp` (branch `merge/fuel-mcp`, NEVER
  the sprint tree): merge `origin/fuel-mcp-fixes`, resolving
  per the verified comparison (parent's verdict table):
  KEEP HEAD for submit honesty, ProjectError catch,
  revisions/ledger, wired queries, hand-written MCP schemas
  (generation wins); TAKE friend's caller-target guard,
  measurements-on-PASS, get_job_status/get_check_results/
  get_logs/list_job_kinds, `--project` binding, workdir
  hygiene, `mcp<3` pin, ExecutionError catch.
- Design tension to resolve, not dodge: friend's auto-drain
  (jobs run before reply) vs our explicit `run_job`. Land
  one coherent semantic with tests; record the call.
- Run tests with `PYTHONPATH=<worktree>/src` + the main
  `.venv` binaries; NEVER cp-sync into the main installed
  copy (sprint children own it). Focused + neighbor suites
  green before reporting.
- Commit the merge on `merge/fuel-mcp`; never push; never
  touch `/home/alrida-ismail/github/rocketEDA/rocket-engine`
  or the GREEN-the-tests branch. Final integration onto
  post-sprint HEAD happens separately.

## Acceptance

- Merge branch green (focused + neighbors, PYTHONPATH-run);
  every conflict resolved per the guidance above with the
  disposition recorded; drain-vs-run_job decision made +
  tested; report lists per-item take/keep with evidence.
