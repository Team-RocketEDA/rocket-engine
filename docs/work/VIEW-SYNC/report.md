# VIEW-SYNC lane report — run_view_sync (intended vs extracted comparison)

Ticket: `docs/tickets/VIEW-SYNC.md` · Branch: GREEN-the-tests.

NOTE: the lane agent errored (runtime approval-capacity failure) before
filing a report, so the integrator reconstructed this record from the
landed RED-first sources + tests. No lane behavior was invented: wiring
below is exactly what `tests/workflows/test_view_sync_wired.py` pins
(stock Engine serves run_view_sync through the connectgraph solver,
FAIL-on-diff, PASS-with-coverage, job_kinds tool list).

## Files added (new files only)

- `src/workflows/viewsync.py` — `compare_views` over shared
  CONNECT-GRAPH extraction (`prepare_netlist_structs`) + CellLink
  identity; rules `view_sync.{missing,extra,wrong}_port`,
  `missing_connection`, `unexpected_connection`, `unmapped`.
- `src/adapters/view_sync/__init__.py` — `ViewSyncAdapter`
  (OPERATION `run_view_sync`, TOOL `connectgraph`), pure-Python,
  no subprocess; coverage + text report ride measurements.
- `tests/workflows/test_view_sync_adapter.py` — adapter RED
  (capabilities, preflight refusals, round trips).
- `tests/workflows/test_view_sync_diff.py` — diff-rule units +
  P14 stage-readiness data probe.
- `tests/workflows/test_view_sync_mzi.py` — MZI fixture tests.
- `tests/workflows/test_view_sync_wired.py` — wired integration:
  FAILs on unwired tree, PASSes once registered.
- `tests/workflows/fixtures/view_sync_mzi.json` — MZI
  intended/extracted pair with exactly 5 planted diffs.
- `docs/work/VIEW-SYNC/wiring.patch` + this report.

## Contract implemented (ticket clause → behavior)

- RED-first ToolAdapter over CONNECT-GRAPH: intended-vs-extracted
  diff with per-finding identity references — `ViewSyncAdapter`
  + `compare_views`; every net name flows from the cited view's
  shared `Connectivity.net_name` authority.
- Reuses CellLink identity + net IDs, never a second naming
  scheme — `_identity_maps` resolves links via
  `interfaces.celllink.resolve_link` only.
- MZI fixture: intended vs perturbed extraction yields exactly
  the planted diffs — wired test asserts the 5-rule set
  (extra/missing/wrong port, unexpected_connection, unmapped)
  and the "5 findings" coverage statement.
- P14 dispatchable with findings report; clean comparison passes
  with explicit coverage statement — wired FAIL + PASS tests.

## Wiring (integrator-applied, recorded in wiring.patch)

- `src/composition.py`: import + `_solvers` entry
  `run_view_sync: {connectgraph: ViewSyncAdapter()}` + docstring
  tool list. Appended at the end (post-FORMAL-SBY position).
- `src/interfaces/setup.py`: SOLVER_DEPS gains
  `(run_view_sync, connectgraph) -> {}` (pure-Python solver,
  always available, like run_connectivity).
- No vocabulary change (`run_view_sync` already cataloged), no
  stages change (P14 names the operation, already present), no
  catalogue change (no tool to provision).

## Suite + gates (integrator-measured)

- Lane: 34/34 pass (adapter + diff + mzi + wired).
- Substrate neighbors: connect-graph ×4 + celllink ×3 green.
- Gates: test_api_spec, test_contract, test_check_contract,
  test_docstrings, test_no_cloud green; check_docstrings +
  check_no_cloud clean; 100-col holds (integrator reflowed 4
  long lines in test_view_sync_diff.py, semantics unchanged).
- Regen: api_spec --write + contract --write; only the 4
  generated docs moved besides wiring.
