# REWIND: Restorable project snapshots

*Status: Done · Depends: LEDGER-DURABLE · Size: M · Roadmap: management-plane*

## Why

Rewind is what makes agent autonomy safe instead of merely
fast — the Claude Code undo/checkpoint equivalent. Today's
`snapshot_id`s are ack receipts, not restorable states: nothing
can roll a project back to a revision. Policy-based auto-approve
for rocket-fuel (auto-approve classes of writes, escalate the
rest) is only responsible with audit + rewind behind it. This
is the enabler epic after the ledger lands.

## What

- RED-first: capture restorable snapshot at revision;
  rewind-to-revision restores managed bytes + ledger position
  (new event recording the rewind itself — history is
  append-only, never rewritten).
- Linked trees: rewind restores engine-tracked state; caller
  files outside `.rocket/` are reported, not touched
  (ADR-001 boundary).
- Rewind handle returned on every mutation response (feeds
  CRUD-API approval UI).

## Acceptance

- Mutate → rewind → byte-identical managed tree at the target
  revision; rewind itself appears in the event log; linked
  caller files untouched with an explicit report.
- Full suite + gate + scenarios green.

## Field notes (proven 2026-10-30, tools PATH + live store)

- RED `b505c12` (12 rewind tests), GREEN `22d4430` + fixup
  `9262e3f`: every mutation snapshots previous (when missing) +
  new under `projects/<id>/snapshots/<revision>/` (in-memory map
  without a root); `rewind` is an immediate OPERATION through
  submit's admission machinery (revision gate + idempotency +
  one new revision + one `project_rewound` event), restoring
  managed bytes byte-identically with runs/ledger/snapshots
  excluded; `Engine.run` delegates rewind back to submit and
  MCP/IPC/HTTP exposure comes free via the vocabulary (one
  write→rewind→read round-trip proven through `McpTransport`).
- Contract decisions: rewind advances from the live head (new id,
  never the target id) so history stays append-only;
  `rewind_handle.revision` points at the pre-rewind head so a
  rewind is itself rewindable; target==head fails
  `invalid_command`, missing snapshot fails `unknown_revision`;
  validation precedes the gate (CRUD precedent) with zero writes
  on stale writers; captures are atomic per snapshot (temp dir +
  rename, stale temps swept); restores roll back best-effort to
  staged pre-bytes; `snapshots/` is engine-owned (rejected as a
  doc path, excluded from listings) and schematized
  optional+tracked so the gitignore is unchanged; linked
  `linked_root` is report-only (files outside `.rocket/` listed
  with bytes, never written, `.rocket/` itself ignored).
- Evidence: REWIND 12/12; project 42/42
  (rewind+crud+ledger+service); neighbors 348 passed 38 skipped
  (project + engine_run + adapters + interfaces); docstring +
  no-cloud gates exit 0; gate-adjacent pytest 13/13; scenarios
  26/0 + pytest 22/22.
- Residual (non-blocking): snapshots have no retention bound
  (every revision kept); pre-slice revisions have no snapshots
  (`unknown_revision`); solver-submit revisions duplicate
  previous bytes (no dedup); cross-process file locking still
  future (inherited); full validate long pole
  (`test_sdtop_determinism_3x`) not rerun — parent gates scoped
  to project + CRUD neighbors, and rewind branches only divert
  the `rewind` name.
