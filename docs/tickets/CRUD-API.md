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
