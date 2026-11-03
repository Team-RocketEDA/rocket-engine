Problem batch (wire or delist each; MCP currently advertises tools that always fail):
1. run_thermal, api_search, api_info, api_help, list_artifacts in vocabulary + MCP + generated docs, but submit raises "Operation not wired yet" (composition.py:573-576,607-610). Audit MC-05.
2. check_connection (bare fn, references.py:82-115) + check_view_sync->run_view_sync compat binding (tooling-operations.yaml:311-312) unrouted. MC-21.
3. parse_report, get_status absent from vocabulary and src. MC-22.
4. PDK list/search/filter/paging/coverage: partial via list_cells/list_assets/serve_asset/stackup, no search/paging/coverage query. MC-23.
5. Per-run findings: Engine.findings()/resolve_celllinks() unrouted; get_check_results is latest-per-operation only. MC-24.
6. plan_checks: flow-only stub reporting solver registration; want target+canvas with cost/evidence. MC-25.
Expected-per: suggested-api §10 rows; tooling-operations.yaml; console-spec:33.

## Verdict (Wave-2, 2026-11-03) — Ready, leftovers to Wave-3

Wired: list_artifacts (evidence trail, newest-first) + place_cell
path_prefix. Resolved no-op: parse_report/get_status (no store;
get_job_status covers), run_thermal (honest No-solver refusal —
delisting would break stages entrypoints). Carry to Wave-3 surface
lane (needs non-owned store/query files): check_connection,
check_view_sync compat, PDK search/paging/coverage, per-run
findings routing, plan_checks target+canvas.

## Verdict (Wave-3, 2026-11-03) — Wiring extended, leftovers confirmed out

`run_xschem`/`run_antenna` now submit end-to-end through owned
files (vocabulary, `Engine._solvers`, dynamic MCP, regenned
docs); the new-op docs render wired. The five leftover items
all bottom out in non-owned files, verified this wave:
`check_connection` lives in `interfaces/references.py`,
`check_view_sync` compat in `tooling-operations.yaml`, PDK
search/paging/coverage in the cell/store layers,
`plan_checks` target+canvas in `workflows/completion.py`, and
per-run findings routing beyond the existing
`Engine.findings`/`resolve_celllinks` in transports. No owned
file can close them; carrying to the sibling lanes unchanged.

## Verdict (Wave-4, 2026-11-03) — Owned-set leftovers landed

This wave owns `references.py`, `completion.py`+`gates.py`
(plan_checks target+canvas ONLY), `stores*` (findings/celllink
routing ONLY), and the no-store no-ops:

- `plan_checks` target+canvas: new `src/workflows/gates.py`
  (`gate_plan_for_target` — pure join of deck tools, canvas
  tool settings, and project-top metric budgets per stage;
  target-scoped constraints surface plan-level for the run to
  scope) + additive `plan_checks_report(flow, available,
  target, canvas)` kwargs (defaults return the backend-only
  plan; canvas-without-target refuses). Pinned by
  `tests/workflows/test_plan_gates.py` (green). `test_completion.py`
  neighbors that build an `Engine` currently fail on the
  sibling lane's in-flight `project/service.py`+`testbench/`
  edit (`ModuleNotFoundError: rocket_engine.project.interfaces`
  at composition import; unrelated to this change — pure
  `plan_checks_report` paths import clean). Engine-side wiring
  (passing target/canvas from `plan_checks`) stays core lane.
- `parse_report`/`get_status` resolve as documented no-ops
  (no store invented): pinned by
  `tests/test_wire_declared_ops_noops.py` — both absent from
  vocabulary while `get_job_status`/`get_check_results`/
  `get_events_since` and the `Engine` readers stay wired.
- `check_connection` (references.py) needs no change:
  implemented, `tests/interfaces/test_references.py` green;
  only its vocab/MCP routing is core lane.

Still core/sibling lane (verified, not owned here):
`check_view_sync` compat (no `tooling-operations.yaml` in
repo; `run_view_sync` lives in vocabulary+composition),
PDK search/paging/coverage (`src/library/`,
`interfaces/apig_assets.py` — only list/get exist, no query
surface), per-run findings routing (`Engine.findings` /
`resolve_celllinks` already route in composition; no store
change needed or made). api-schema regen (run_drc gains
`waive_rules`, sibling vocabulary deltas) belongs to core lane.

## Verdict (Step 11, 2026-11-03) — get_findings wired, remainder delisted

- `get_findings` wired: `Engine.findings()` was public but
  unrouted; now a QUERIES name through `_query_job`
  (run_id + limit/cursor), rendered in api_spec/MCP with
  generated schemas. TDD RED->GREEN
  (`tests/test_findings_query.py`, 4 tests: vocab, unknown_run,
  page content, limit). Oracle holds: zero
  advertised-but-failing tools.
- Delisted from Engine routing (not advertised, no new surface
  invented in a wiring step):
  - `check_connection`: pure library helper
    (`src/interfaces/references.py`, covered by
    `tests/interfaces/test_references.py`, green); no store,
    no transport.
  - `resolve_celllinks`: flow-internal compute used by
    completion flows (covered by
    `tests/interfaces/test_celllink_wiring.py`, green); stays
    library-level, no query.
  - PDK search/paging/coverage: no query surface invented
    here; list/get primitives stay. A search API is new
    surface, not wiring — future ticket if asked.
  - `plan_checks` target/canvas: signature change on a
    core-lane flow method with sibling in-flight edits;
    deferred. Flow-only plan stands and is oracle-green.
