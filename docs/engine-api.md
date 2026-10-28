# Engine API (for RocketIDE frontend developers)

The engine is headless. This document is the complete data contract:
every operation, query, event, state, and result shape the UI can
depend on. No UI field may exist without a typed engine output defined
here or in `src/interfaces/`. Transports (`api`, `ipc`, `mcp`, `cli`)
carry identical commands — the shapes below never vary by caller.

Conventions: `ref` = `{scope, id, revision}` (scope `project` or
`global`). All lists are paginated with opaque `next_cursor`.
`artifact` = `{id, kind, relpath, mime, bytes, digest}`.
Items marked (proposed) extend the PRD and need its sign-off.

## 1. Operations (commands)

One backend per run, resolved by the engine from PDK + deck + registry.
The `backend` column names the decided tool (see README decisions).

| Operation | Key params | Result | Backend |
|---|---|---|---|
| `generate_views` | target ref, views[] | layout/schematic/symbol artifacts | GDSFactory, KLayout |
| `run_syntax` | sources[] | diagnostics[] {file, line, col, severity, rule, message} | Slang, Verible, Verilator lint |
| `run_connectivity` | netlist/circuit ref | findings[] (ports, nets, mismatches) | engine + SAX/Circulax checks |
| `run_hdl_test` | bench ref, sim, seeds[], waves? | pass/fail, asserts, coverage %, wave artifact | Verilator / Icarus / GHDL + cocotb |
| `run_formal` | properties[], depth, engines[] | proven/bounded/cex + trace artifact | sby (+mcy quality) |
| `run_digital_flow` | flow config, stages[]? | stage table (see §4), GDS/LEF/SDF/SPEF artifacts | LibreLane |
| `run_timing` | corners[], artifacts? | setup/hold, paths[] {slack, from, to}, limits | OpenSTA via LibreLane |
| `run_drc` | layout ref, deck ref | violations[] {rule, layer, bbox_um, count} | KLayout / Magic per deck |
| `run_lvs` | layout + reference refs | match/mismatch, device/net counts, diffs[] | Netgen (+KLayout LVS) |
| `run_erc` | netlist ref, rules? | findings[] | engine + PDK rules |
| `run_spice` | netlist, benches[], corners[] | measurements[] + curves (see §4) | ngspice (Xyce when qualified) |
| `run_optical` | circuit ref, analyses[] | spectra + S-params + measurements | SAX (freq) / Circulax (time) |
| `run_extraction` | layout ref, deck/rules | netlist artifact, device counts, coverage | Magic / KLayout |
| `run_post_layout` | extracted ref, benches[] | like `run_spice` + pre/post deltas | ngspice / Xyce / Circulax |
| `run_em` | geometry + materials + ports | S-params, modes, convergence, field summary | Meep / openEMS / Palace / MEOW |
| `run_thermal` | geometry + power + boundaries | hotspot list, peak/mean temps, margins | Elmer / FEMwell |
| `run_view_sync` | layout + intended refs | match/mismatch + diff list | engine + KLayout |
| `python_execute` | code ref or inline (approved), profile | cells[] with stdout/stderr, effects, child runs | console worker |

Controls: `cancel_run {run_id}`, `approve_console {approval_id}`,
`submit_revision {files}`. Queries: `api_search`, `api_info`,
`api_help`, `get_python_console`, `get_capabilities`,
`get_project_snapshot`, `list_job_kinds`, `plan_checks`,
`get_job_status`, `get_check_results`, `list_artifacts`, `get_logs`.

## 2. States and lifecycles

Readiness (per project × operation, from `get_capabilities`):
`ready` → executes; `blocked` (fixable, reason + missing items);
`unavailable` (env/tool down, retryable); `unsupported` (no backend
or deck — terminal for this config); `unknown` (never shipped).

Run lifecycle: `queued` → `running` → `completed` | `error` |
`cancelled`. Cancel is racy: cancelling a finished run truthfully
returns its terminal state, never a fake `cancelled`.

Check verdicts: `PASS` (all acceptance met) / `FAIL` (violations or
missed targets) / `NOT_RUN` (missing input, cancelled, unparsable, or
unsupported-required — always with `reason`) / `UNSUPPORTED`
(terminal for this config). Exit zero never implies PASS.

Freshness: evidence pins `snapshot_id`; later source edits mark it
`stale` (kept, flagged) rather than deleting it.

Events (SSE / stdio / MCP streams, ordered, cursor-resyncable):
`job_queued`, `job_finished`, `check_updated` carry
`{run_id, check_id, status, revision}`. `artifact_ready` (proposed)
carries artifact descriptors as files land. Console streams emit
`console_output` chunks plus `approval_requested` / `approval_resolved`
(proposed) for the trusted approval UI.

## 3. Common result envelope

Every check result carries: `run_id`, `check_id`, `status`,
`project_revision`, `snapshot_id`, `tool` {adapter, version, deck
digest}, `started/finished_at`, `summary` {counts by severity},
`measurements[]`, `findings[]`, `artifacts[]`, `log_excerpt` +
full-log artifact ref, `freshness`. A finding is
`{id, severity, rule, message, location?, actual?, limit?}` where
location may be a file span, a `layer+bbox_um`, or a device path. A
measurement is `{name, value, unit, target?, margin?, status}` —
`margin` is always engine-computed, never left to the UI.

## 4. Per-family data shapes

- HDL sim: `{passed, failed_asserts[], coverage_pct, seeds[], cycles,
  wave}` where `wave` is an FST artifact (+VCD on request).
- Formal: `{engine, depth, result: proven|bounded|cex|timeout,
  trace_artifact?}`; mutation quality `{score, killed/total}`.
- Digital flow: `stages[] {name, status, occurrences[],
  disabled_reasons[]}` plus `area_um2, power_mw, wns_ns, tns_ns` and
  GDS/LEF/SDF/SPEF artifacts. Parent completion never implies all
  checks passed — the UI must render per-stage states.
- SPICE: `op {node: {v,i}}`, `ac[] {f, mag_db, phase_deg}`,
  `tran {t[], signals{}}` (downsampled + full artifact),
  `corners[] {name, measurements[]}`, `mc {runs, mean, std, yield}`.
- Photonic: `spectra[] {wavelength_nm[], transmission_db[]}`,
  `s_params {ports[], matrix_ref}`, scalar measurements as in §3.
- EM/thermal: `{converged, iterations, s_params?, modes[]?,
  hotspots[] {location, value, unit}, peak, mean, margins{}}`.
- DRC: `violations[] {rule, layer, bbox_um, count}` + total + deck
  identity. LVS: `{match, layout_devices, schematic_devices,
  mismatches[]}`. Extraction: `{netlist_artifact, devices, nets,
  coverage_pct}`.
- Console: `cells[] {seq, code_ref, stdout, stderr, state}`,
  `effects[]` (runs spawned, files staged — never silent writes),
  approvals `{approval_id, state, binding_hash}`.
- Library: `pdks[] {id, revision, domains, readiness{}}`,
  `components[] {ref, status}` where `status` includes `UNVERIFIED`
  for unproven reuse; `dependency_closure[]`.

## 5. Artifact kinds

`wave` (FST/VCD), `layout` (GDS/OAS + preview PNG), `schematic`
(SVG/PNG render), `netlist` (SPICE/CDL/Verilog), `report`
(TXT/JSON), `plot` (PNG + source CSV), `dataset` (CSV/NPY),
`trace` (formal/VCD), `log` (bounded excerpt inline, full file).
The engine serves bytes by `relpath`; RocketIDE renders and caches.

Dual-representation rule: anything a human would read as a graph
MUST ship as a full-fidelity `dataset` the agent can script against
(columnar, units in metadata, no silent downsampling) plus an
optionally generated `plot` image for visual intuition. Every `plot`
links its source `dataset`. Inline previews MUST declare `n_total`
vs `n_shown` and the downsampling method.

## 6. Errors

Stable `code` + human `message` + `fields[]` when itemized:
`invalid_yaml`, `invalid_reference`, `missing_dependency`,
`incompatible_port`, `unsupported_operation`, `unsupported_check`,
`revision_conflict`, `request_conflict`, `resync_required`,
`approval_invalid`, `runner_unavailable`, plus adapter-layer
`cross_project_denied` and `invalid_command`. Unknown enum values
and fields are rejected, never ignored.

## 7. Transports and versioning

Same command over HTTPS+SSE, framed stdio, MCP `tools/call`, and
the CLI mirror. Envelope: `{schema, request_id, project_id,
expected_revision, operation, target?, arguments}` → ack
`{run_id, snapshot_id, state}` → events → result. Contract
changes are additive and versioned (`rocketeda/tooling/vX.Y`);
renames are breaking and need a major bump plus migration notes.

## 8. Agent analytical access

The harness is an LLM: sequential data is for scripts first, eyes
second. Datasets are analysis-ready (see §5); the design profile
guarantees numpy/scipy/pandas/matplotlib so agents can fit, FFT,
and diff against models — e.g. fit a SPICE transient to the target
s-domain step response and report stray as margins.

Console permission is two-tier (proposed, needs PRD sign-off):
standing user permission covers the analysis sandbox only
(read-only project data + scratch, no host/network/evidence
writes); anything effectful keeps per-action approval binding.
Reference workflow: the analog s-domain loop in
`docs/prd-feedforward.md` F7.
