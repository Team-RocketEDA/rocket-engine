# Invariant map — E2E-REREVIEW lane (I01–I33 + Generalization law)

- Repo: `rocket-engine`, branch `GREEN-the-tests`, HEAD `a8aaa09`.
- Method: REVIEW ONLY — no tree edits (final `git status` clean except this
  untracked report dir, which already held another lane's file).
- Tests cited below were executed in this session against the sealed install
  (`site-packages/rocket_engine`, verified byte-identical to `src/` via
  `diff -rq` excluding `__pycache__`).
- Verdict scale: PROVEN (implementing symbol + passing proving test),
  PARTIAL (core proven, named sub-clause unproven), UNPROVEN (no
  implementation or no proving test, with probe).

## RED-proof spot checks (breaks applied to `/tmp/rp1/*` shadow copies only)

| # | Invariant | Break (shadow) | Result |
|---|-----------|----------------|--------|
| RED-I09 | I09 | `execution/service.py:evaluate` returns PASS when `exit_code == 0` | `test_exit_zero_with_violations_stays_fail` FAILS |
| RED-I33 | I33 | `execution/coalesce.py` revision check removed from `lookup`+`join` | 3 FAIL: `test_lookup_is_pure_and_revision_pinned`, `test_join_misses_when_revision_moved`, `test_register_replaces_stale_revision_without_stranding_waiters` |
| RED-I01 | I01 | `interfaces/documents.py:validate_document` canned-accept | 8/8 `test_strict_yaml.py` FAIL |
| RED-I30 | I30 | `project/service.py:_gate_revision` neutered (stale lands) | 2 FAIL: `test_write_doc_stale_rejected_without_effects`, `test_apply_mutations_stale_rejected` |
| RED-I01-guard | I01 (granularity) | Only `_reject_composition_tricks` neutered | 8/8 PASS — fixture rejected via `Unknown field: base` instead (see F3) |

## Generalization law — PASS, no smoke-only solver adapter

All 18 registered solver ops (`src/composition.py:275-293`) consume project
inputs from the job, verified by `job.get` use in each adapter's
`preflight`/`execute`:

- `run_drc` (magic: `cell_file`/`cell`; klayout: `gds_file`/`rules`/`deck_file`),
  `run_hdl_test` (`sources`,`defines`), `run_optical` (sax/circulax `sources`),
  `run_em` (meow `sources`), `run_extraction` (`cell`/`cell_file`/`tech_file`),
  `run_lvs` (`layout`/`schematic`/`setup_file`/`cell`), `run_spice`
  (`sources`,`measurements`,`analyses`,`params`,`corner`,`pdk`),
  `run_post_layout` (`extracted_netlist`,`testbench`, refuses `sources` alias),
  `run_syntax` (`sources`,`slang_flags`), `run_synth`
  (`top`,`sources`,`liberty`), `run_connectivity`/`run_erc`
  (`schematic`,`languages`,`run_key`), `run_formal`
  (`top`,`sources`,`mode`,`depth`,`engines`), `run_view_sync`
  (`intended`,`extracted`,`links`), `generate_views`
  (`recipe`,`sources`,`pin_map`,`cspdk_path`), `run_cosim`
  (`analog_sources`,`digital_sources`,`analog` loop), `run_digital_flow`
  (`top`,`sources`,`flow`,`pdk`,`clock_period`,`force`),
  `run_timing` (`top`,`netlist`,`libs`,`sdc`,`spef`).
- Smoke modules each have a sibling real op already wired: `meow/__init__.py`
  `run_eme_smoke` → `meow/adapter.py` `MeowAdapter`; `circulax/__init__.py`
  `run_rc_step` → `circulax/adapter.py` `CirculaxAdapter`;
  `gdsfactory/__init__.py` `run_layout_smoke` → `gdsfactory/adapter.py`
  `GdsfactoryViewsAdapter`. (`cli`/`http`/`ipc`/`mcp` are transports, not
  solvers — out of scope for the law.)

## Invariant map

| ID | Verdict | Implementing file:symbol | Proving test |
|----|---------|--------------------------|--------------|
| I01 | PROVEN (+F3) | `src/interfaces/documents.py:validate_document` (L53; guards `_reject_composition_tricks` L24, `_reject_nonfinite_and_depth` L40, 1 MiB / depth-100 caps) | `tests/interfaces/test_strict_yaml.py` (8/8 pass; RED-I01) |
| I02 | PROVEN | `src/interfaces/references.py:resolve_reference` (exact scope/id/revision, root containment) + `check_connection` (wavelength-unit compat); `src/interfaces/paths.py` escape/`path_escape` | `tests/interfaces/test_references.py` (in 50-pass batch) |
| I03 | PROVEN | `src/library/catalog.py:Catalog.capabilities` (per-op ready/unsupported+reason) | `tests/library/test_catalog.py::test_generation_ready_while_lvs_unsupported` |
| I04 | PROVEN | `src/library/catalog.py:Catalog.resolve` (per-revision records) + `active_context` (per-job token); worker-level: `src/adapters/gdsfactory/_driver.py:_activate` (per-process PDK activation from job `cspdk_path`, L180) | `tests/library/test_catalog.py::test_same_name_revisions_stay_isolated` |
| I05 | PROVEN | `src/composition.py:Engine.submit` — single admission path for IDE/MCP/console; `src/adapters/mcp/__init__.py:McpTransport.handle`, `http`, `ipc` converge on it | `tests/project/test_project_service.py` (B3 parity) + `tests/adapters/test_transports.py::test_api_ipc_mcp_submit_identical_commands` |
| I06 | PROVEN | `src/project/service.py:_check_replay` (same id+text→same ack; changed→`request_conflict`) + `_gate_revision` (stale→`revision_conflict`); mirrored in `src/interfaces/engine_ecs_store.py` | `tests/project/test_project_service.py`; `tests/test_engine_ecs_store.py` (39 pass) |
| I07 | PROVEN | `src/project/service.py:events_since` (`resync_required` on retention gap / cursor ahead) | `tests/project/test_project_service.py` (B3 event recovery) |
| I08 | PROVEN | `src/execution/service.py:dispatch` (`snapshot_id` pin) + `evidence` (current/stale via `note_source_change`) | `tests/execution/test_execution_service.py::test_long_run_keeps_original_snapshot_after_source_change` |
| I09 | PROVEN | `src/execution/service.py:evaluate` (verdict from findings, exit code recorded-only) + `record_not_run`; every adapter `parse` judges output not exit (e.g. `postlayout` Caution L566, `digital_flow.parse` L721 gateless-fail); console returns NOT_RUN (`python_exec.py:run_job` L1444) | `tests/execution/test_execution_service.py::test_exit_zero_with_violations_stays_fail`, `::test_unparsable_output_is_not_run_not_fail`; RED-I09 |
| I10 | PROVEN | `src/execution/service.py:findings` (errors-first page, total counts, `next_cursor`, `truncated`) + `src/execution/runner.py:clean_stream` (1 MiB/stream bound + marker) | `tests/execution/test_execution_service.py::test_bounded_findings_preserve_counts_and_cursors` |
| I11 | PROVEN | `src/execution/service.py:cancel` (finished keeps terminal state) + `src/execution/runner.py:_kill_tree` + `src/execution/worker.py:_confirm_tree_dead` + `src/composition.py:cancel_job` L1506 | `tests/execution/test_execution_service.py::test_cancel_queued_running_completed_is_truthful`; `tests/execution/test_workers.py` |
| I12 | PARTIAL (+F5) | Scope: `src/adapters/base.py:enforce_scope` + per-transport `project_id` gate (`mcp`/`http`/`ipc`); resume via `events_since` snapshot | `tests/adapters/test_transports.py::test_transports_reject_cross_project_calls`, `::test_http/ipc_rejects_missing_project_id` — auth half unproven (F5) |
| I13 | PROVEN | `src/library/catalog.py:register`/`instantiate`/`promote` (UNVERIFIED preserved, dependency closure, port checks) | `tests/library/test_catalog.py::test_register_reuse_promote_without_blanket_pass`, `::test_incompatible_ports_rejected_on_instantiate` |
| I14 | PROVEN | Real-solver adapters + good/failing fixture pairs (hdl `tb_pass`/`tb_fatal`, drc good/bad `.mag`, sax `mzi`/`broken`, ngspice RC, formal counters) | `tests/adapters/test_hdl_sim.py`, `test_ngspice.py`, `test_sax.py`, `test_drc.py`, `test_syntax.py` et al (137 pass batch); `scripts/correctness.py` gate |
| I15 | PROVEN | `src/execution/python_exec.py:request_execution` L1178 + `resolve_approval` L1327 (code/history/env/revision re-check; non-`ui`→`approval_forbidden`); `src/execution/console.py:admit_cell` | `tests/execution/test_console.py`; `test_python_exec_live.py` (sandbox-gated) |
| I16 | PROVEN | `src/execution/runner.py:BwrapRunner.preflight` L223 + `default_profile` + `run` (budgets, `clean_stream` bounds); unprovable→refuse, no host fallback | `tests/execution/test_runner.py`; `tests/execution/test_workers.py` (bwrap-absent skips, never fake-green) |
| I17 | PROVEN | `src/execution/python_exec.py:validate_request` (prebound APIs) + `run_job` fresh worker + `reset`/`cancel` generation retirement | `tests/execution/test_console.py` (lifecycle/binding); live worker path in `test_python_exec_live.py` / `test_workers.py` |
| I18 | PARTIAL (+F6) | `src/execution/console.py:get_help` L33 (pure data, `unknown_topic`, no imports) | `tests/execution/test_console.py` — `api_search`/`api_info`/`api_help` queries unwired (F6) |
| I19 | PARTIAL (+F7) | `src/adapters/mcp/__init__.py:host_execution_enabled=False` L23 + `handle` rejects non-cataloged (host shells first) | `tests/adapters/test_transports.py::test_mcp_never_substitutes_host_or_console_routes` — explicit host opt-in surface not located (F7) |
| I20 | PARTIAL (+F8) | `scripts/install.sh --install` (locked `uv sync` + sealed `uv pip install --no-deps .`) | Install path exists; no clean-account offline proof test (F8) |
| I21 | PROVEN | `src/interfaces/setup.py:report_capabilities` (ready/blocked+reason+missing+remedy/unsupported; BYOC cloud rows) + per-adapter preflight remedies | `tests/interfaces/test_setup.py` (2 pre-existing failures, see F2; remainder pass) |
| I22 | PROVEN | `src/execution/service.py:request_approval`/`admit` (closure+revision binding) + `python_exec` closure re-check + `src/execution/console_route.py` tier-2 admission routing (L1); tier-2 = mutations via admission | `tests/execution/test_execution_service.py::test_executable_closure_change_invalidates_approval` |
| I23 | PROVEN | `src/execution/worker.py:CredentialGate.revoke` L135 + `_confirm_tree_dead` L172, fresh worker per run (`CellRunner.run` L292); mirrored in `python_exec.py` L900/L568 | `tests/execution/test_workers.py` |
| I24 | PROVEN | `src/adapters/gdsfactory/adapter.py:GdsfactoryViewsAdapter` (job-driven recipes, no new MCP endpoint) + `console_route` effect replay through revision-gated `apply_mutations` | `tests/adapters/test_generate_views.py`, `tests/adapters/test_gdsfactory.py` |
| I25 | PROVEN | `src/adapters/digital_flow/__init__.py:parse` L721 + `_evaluate_stages` (per-stage table preserved; clean exit with gateless stages FAILs them — no parent-completion inference); `src/workflows/stages.py` inventory | `tests/adapters/test_digital_flow.py` |
| I26 | PROVEN | `src/adapters/postlayout/adapter.py:preflight` (extracted-netlist+provenance required; stale/foreign refuses; `sources` alias refused); `timing_sta` SPEF-gated parasitics; stage data D21/A17/P15/M10 | `tests/adapters/test_postlayout.py`, `tests/adapters/test_timing_sta.py` |
| I27 | UNPROVEN (+F1) | `src/workflows/stages.py:applicable_stages` (ready/blocked data) exists, but NO reporting surface consumes it | None — `plan_checks` in `QUERIES` (`vocabulary.py:24`) has zero implementations (grep probe); no "fully verified" gate found |
| I28 | PARTIAL (+F4) | Ingredients: `src/interfaces/pdks.py:pdk_ingredient` L487 (id+revision+manifest/tree hash) + `cosim:build_run_record` L1243 + `scripts/correctness.py` `run_record.json`; drift-loud via `pdk_drift`; exhaust gitignored (`*.gds`,`results/`,`tmp/`,`.rocket/`) | `tests/test_replay_safe.py` (quarantine, never auto-rerun); `test_cosim_live.py` I28 artifacts — verdict-reproduction-on-replay unproven (F4) |
| I29 | PROVEN | `src/interfaces/apig_assets.py:serve_asset` L115 + `list_assets` (verbatim bytes, sha256 identity, PATH-GUARD containment, loud unknown-asset) | `tests/test_apig_assets.py` |
| I30 | PROVEN | `src/project/service.py` mutations advance revision + actor event; `_gate_revision` L1416 (`revision_conflict`); idempotent `request_id` | `tests/project/test_ledger_durable.py`, `tests/project/test_crud_api.py`; RED-I30 |
| I31 | PROVEN | `src/project/service.py:apply_mutations` L3005 (validate-all-first, one revision, names failing document, untouched on failure) | `tests/project/test_crud_api.py` |
| I32 | PROVEN | `scripts/check_no_cloud.py` (forbids `tidy3d`/`gdsfactoryplus`/`gcloud` imports) + `setup.py` static gated cloud rows, no key lookup, no network | `tests/test_no_cloud.py`, `tests/interfaces/test_setup.py::test_cloud_entries_gated_without_keys_and_no_network` |
| I33 | PROVEN | `src/execution/coalesce.py:content_key` L141 (op + normalized args incl `deck_hash` + `run.request`) + `Coalescer` (key,revision) pin, `guard` admission lock, completion eviction; forced re-runs bypass (composition L601-606) | `tests/test_coalesce.py` (24 pass) + `tests/test_coalesce_wiring.py`; RED-I33 |

## Findings

- F1 — severity: high — `src/interfaces/vocabulary.py:24` (`plan_checks`
  declared) vs zero implementations repo-wide; `src/workflows/stages.py`
  `applicable_stages` has no Engine caller gating a completion claim.
  Probe: `grep -rn plan_checks src/ scripts/` → only the vocabulary
  declaration. I27's "block a fully verified claim" has no code path.
  Proposed ticket: `E2E-REREVIEW: wire plan_checks/design-completion gate (I27)`.
- F2 — severity: medium — `tests/interfaces/test_setup.py:73` `_no_sax`
  masks only `sax`, but `run_optical` has a second solver (`circulax`,
  `src/composition.py:280`, installed in the venv), so
  `test_fresh_machine_names_every_missing_tool_with_remedy` and
  `test_sax_absent_reports_photonic_remedy` fail with `ready != blocked`.
  Engine is honest; the test simulation is stale. Pre-existing (tree
  untouched). Proposed ticket: `E2E-REREVIEW: mask circulax in fresh-machine setup tests`.
- F3 — severity: medium — `src/interfaces/documents.py:24`
  `_reject_composition_tricks` is deletable without red:
  `tests/interfaces/fixtures/invalid/alias_merge.yaml` carries a
  top-level `base:` anchor node, so the neutered validator still rejects
  it via `Unknown field: base` (probe in RED-I01-guard). The I01 test
  pins "rejected" but not "rejected by the composition guard".
  Proposed ticket: `E2E-REREVIEW: pin I01 composition guard with allowed-fields alias fixture`.
- F4 — severity: medium — I28 ingredient pinning proven, but no test
  replays a recorded run and asserts identical verdicts/measurements.
  Probe: `grep -rn reproduc|same verdict tests/test_replay_safe.py
  tests/adapters/test_cosim_live.py scripts/correctness.py` → no hits.
  Proposed ticket: `E2E-REREVIEW: add I28 replay-reproduces-verdicts test`.
- F5 — severity: medium — I12 "authenticated caller scope": project
  scope enforced, but no authentication exists —
  `src/adapters/stdio_console.py:34,84` ("no auth step … no second
  party"); HTTP adapter has no token check. Acceptable for local
  stdio, undefined for HTTP/MCP callers.
  Proposed ticket: `E2E-REREVIEW: define I12 auth story for HTTP/MCP callers`.
- F6 — severity: low — `api_search`/`api_info`/`api_help` in `QUERIES`
  (`vocabulary.py:24`) have no implementation (grep over
  `src/composition.py`, `src/execution/*`, `scripts/api_spec.py` →
  none); only `console:get_help` (static 3-topic metadata) is proven.
  Proposed ticket: `E2E-REREVIEW: wire or descope api_search/api_info/api_help (I18)`.
- F7 — severity: low — I19 default-deny proven
  (`mcp/__init__.py:23`, transport test), but no explicit trusted
  opt-in flag/setting for a host-terminal route was located (grep
  `opt.in|allow_host|host_exec` → only the MCP `False` default).
  Proposed ticket: `E2E-REREVIEW: name the I19 host-execution opt-in surface`.
- F8 — severity: low — I20: locked+sealed install exists, but no
  clean-account offline install test and no runtime-digest-vs-manifest
  assertions exist (`tests/test_packaging.py` only checks imports).
  Proposed ticket: `E2E-REREVIEW: offline clean-account install proof (I20)`.

## Notes

- Suite state at HEAD: everything cited above passes except the two F2
  failures (284 pass + 7 skip in the final sweep batch; earlier batches
  50/50, 85 pass + 21 skip, 137 pass + 10 skip). Skips are
  environment-gated (missing optional solvers/sandbox), none deleted.
- Methodology note for later lanes: tests import the sealed
  `site-packages/rocket_engine` copy installed by `install.sh`; after any
  future `src/` edit the package must be reinstalled or tests prove stale
  code. In sync at this HEAD.
- I26/M10 "parasitics counted once" and final-dataprep re-gating live as
  stage data (`stages.py` M10/A21/P20/M15) without an enforcement
  endpoint — same root cause as F1, not separately ticketed.
