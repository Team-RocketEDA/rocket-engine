# CRUD-API: Uniform document CRUD over the project tree

*Status: Backlog · Depends: LEDGER-DURABLE · Size: M · Roadmap: management-plane*

## Why

The engine can verify but barely manage: zero project-management
actions exist — no list/create projects, no component or script
operations. Both coming consumers need them: rocket-fuel wants a
small abstracted mistake-free surface for everything it dreams of
doing, and the UIUX team wants a boring readable API. Per-content
verbs (`create_component`, …) would bloat to dozens; the project
is already an addressed tree, so uniform document ops cover every
content type with six verbs. The batch op is what makes agent
multi-file edits land atomically instead of half-failing.

## What

- RED-first: `list_projects` / `create_project`;
  `list_docs` / `read_doc` / `write_doc` / `delete_doc` over
  (project, path) with `expected_revision`; `apply_mutations`
  batch with all-or-nothing semantics (I31).
- Writes route through submit's admission machinery (revision
  gate + idempotency + event logging) — reuse, never a parallel
  mechanism. Every mutation returns new revision + events.
- Components/scripts are conventional paths per the layout
  schema; no per-content verbs. Skip `delete_project`
  (archive/rename covers it) and `run_script` (console executes).
- Mutation responses carry approval-UI needs: actor, diff
  summary, revision transition, rewind handle.

## Acceptance

- All six ops live over Engine + one transport E2E; batch
  atomicity proven (partial failure lands nothing, names the
  document); stale revision rejected without effects.
- Full suite + gate + scenarios green; docstrings Google-style
  per API-GEN mandate (or that ticket first — order at sprint start).

## Field notes (proven 2026-10-30, tools PATH + live store)

- RED `6a26fe7` (14 CRUD tests), GREEN `514589e`:
  `list_projects`/`list_docs`/`read_doc` are wired queries;
  `create_project`/`write_doc`/`delete_doc`/`apply_mutations`
  execute immediately inside `submit()` via a `_CRUD_OPERATIONS`
  bypass (run_job precedent — no queue, no solver); `Engine.run`
  delegates CRUD back to `submit` so the CLI `run` spelling shares
  the one implementation. MCP/IPC/HTTP exposure comes free via the
  vocabulary (one write→read round-trip proven through
  `McpTransport` against the real Engine).
- Contract decisions: docs live beside the ledger as UTF-8 files
  under `projects/<id>/` (1 MB cap, atomic rename; in-memory map
  without `engine_root`); `ledger.yaml`/`events.yaml`/`runs/` are
  engine-owned and rejected; `components/`+`scripts/` are plain
  conventional paths with no per-content verbs and no schema gate.
  Single writes/deletes and the batch reuse the admission
  machinery (`_check_replay` before the gate, so retries with
  stale revisions replay instead of conflicting). The batch
  validates every mutation before anything lands (unknown op,
  missing content, delete-with-content, unknown fields, missing
  doc — each naming its document), gates once, then lands under a
  single new revision with one `mutations_applied` event;
  mid-batch I/O failures roll back best-effort. `create_project`
  takes `new_project_id` (the envelope keeps the bound project so
  MCP survives the pop), starts the new ledger clean at `p12` with
  no events, and persists the bound request map for replay.
  Responses carry `actor`, `diff_summary`, `revision_transition`,
  `rewind_handle {project_id, revision, request_id}`; rewind
  restore itself stays with REWIND. `delete_project`/`run_script`
  pinned unwired (vocabulary lacks them, submit raises
  `unsupported_operation`).
- Evidence: CRUD 14/14; ledger neighbors 67 passed 2 skipped
  (project + engine_run + mcp_live/server + transports);
  docstring + no-cloud gates exit 0; scenarios 26/0; full suite
  788 passed 33 skipped 0 failed (non-validate 626+32 in 272s;
  validate-rest 161+1 in 694s; long pole
  `test_sdtop_determinism_3x` solo 1 passed in 622s — 36 PEX
  ngspice sims in one test, see residual).
- Residual (non-blocking): cross-process file locking for
  concurrent writers (inherited); `policy.yaml` writable via CRUD
  with no policy validation (loud at next `validate_tree`);
  non-UTF8 durable bytes read as `invalid_document`;
  `tests/validate/test_mixed.py::test_sdtop_determinism_3x` is a
  pre-existing long pole (6 cases x 3 reps x 2 ngspice runs) that
  exceeds a 15-minute budget in this environment — for its
  operations (`run_spice` via `engine.run` + direct
  `NgspiceAdapter`) this slice executes the identical path (CRUD
  branches only divert CRUD names), so the slowness is
  ngspice-perf territory (VALIDATE-M), not a CRUD regression.
