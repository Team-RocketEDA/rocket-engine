# PR3-MERGE: Merge fuel-mcp-fixes (PR #3) with consolidation

*Status: Done · Size: M · Roadmap: codesign*

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

## Field notes (merged 2026-10-30, isolated worktree only)

- Merge `256b689` (resolution) + `e6ecc2d` (consolidation) on
  `merge/fuel-mcp`; never pushed; main tree and GREEN-the-tests
  untouched (ticket/board lines imported read-only from local
  GREEN-the-tests `f11b949`, which sits 1 ahead of
  origin/GREEN-the-tests).
- Dispositions: KEEP HEAD submit honesty/two-phase, ProjectError
  catch, revisions + durable ledger + run events, wired
  snapshot/events_since/list_projects/list_docs/read_doc queries,
  docstring-generated schemas (no hand-written inputSchemas).
  TAKE constraints min/max refusal (+ unknown-metric, + expr/
  control fill), measurements on PASS, four job queries, --project
  fill + --project-dir (constraints, confinement, evidence),
  --call one-shot, workdir hygiene at the MCP boundary,
  ExecutionError catch, mcp>=1.0,<3 (pin absent from the friend
  branch itself — friend pins nothing; applied here, lock checked).
- DRAIN DECISION: explicit run_job wins, no auto-drain. Auto-drain
  would collapse the admitted/executed distinction (two-phase over
  all transports) and bypass the ledger's request linkage. One
  semantic: submit ack run_id IS the execution id (queued, then
  verdict); run_job takes the ack run_id (agent-friendly) or the
  envelope request_id (HEAD compat). Tested by
  test_submit_leaves_job_queued_until_explicit_run_job (+ run_job
  by request_id / unknown run_id); evidence test asserts nothing
  is written at submit time.
- Consolidation extras: run_job-by-run_id (transports mint envelope
  ids opaquely, so request_id alone is unusable over MCP);
  get_logs offset/limit hardened to invalid_command; full Google
  docstrings on new public server helpers (check_docstrings exit 0).
- Evidence (imports resolve to the worktree via a /tmp symlink
  shadow — see below): 20/20 agent-path (incl. 2 live ngspice);
  final sweep 246 passed, 31 skipped, 1 pre-existing env failure
  (test_run_selects_solver_from_deck_tool: untracked
  drc_kl/bad_space.gds fixture, only make_cells.py in git —
  fails identically without this merge). Guard
  scripts/check_docstrings.py exit 0; `uv lock --check --offline`
  exit 0 after the pin.
- IMPORT SHADOW FINDING: the literal
  `PYTHONPATH=<worktree>/src` order resolves `rocket_engine` to
  the main .venv's installed copy (hatch force-include layout has
  no `rocket_engine/` dir under src/), NOT the worktree. Verified
  runs here used
  `PYTHONPATH=/tmp/fuel_shadow:/tmp/merge-fuel-mcp/src` with
  `/tmp/fuel_shadow/rocket_engine -> /tmp/merge-fuel-mcp/src`
  (venv untouched, read-only binaries). Re-runs must keep a shadow
  (or reinstall) or they silently test the sprint's installed copy.
- Residual: drc_kl generated fixtures; cross-slice rebase of
  merge/fuel-mcp onto post-sprint HEAD happens separately.
