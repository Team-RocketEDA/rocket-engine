# LEDGER-DURABLE: Durable attributed event log + advancing revisions

*Status: Backlog · Size: M · Roadmap: management-plane*

## Why

This is the neuter-now set for the split-brain bug class: two
writers (human + rocket-fuel) with no arbitration. Today the
revision gate exists but the revision never advances past p12,
the event log is in-memory with only `job_queued` (a restart
wipes history), `run()` appends nothing, and mutations carry no
actor. Until this lands, lost updates, silent divergence, and
unattributable agent edits are all possible — and any CRUD
built on top would be half-built management with a fake gate,
worse than none. ADR-002 assigns the ledger to the engine;
this ticket implements it (I30).

## What

- RED-first: revision advances on every engine-mediated
  mutation; stale `expected_revision` → `revision_conflict`.
- Durable ordered event log (survives restart) with
  `run_completed` / `run_failed` appended from `run()`;
  actor attribution (human / rocket-fuel / system) on every
  event; `get_events_since` query with cursor + resync
  semantics.
- Retention policy documented (what `resync_required` means
  and when history ages out).

## Acceptance

- Concurrent-mutation test: second stale writer rejected, no
  lost update; restart test: log + cursor survive; run test:
  completion events present with actor and verdict link.
- Full suite + gate + scenarios green.
