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
