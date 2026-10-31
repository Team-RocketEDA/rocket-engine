# REWIND: Restorable project snapshots

*Status: Backlog · Depends: LEDGER-DURABLE · Size: M · Roadmap: management-plane*

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
