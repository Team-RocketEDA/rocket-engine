# LEDGER-DURABLE: Durable attributed event log + advancing revisions

*Status: Done · Size: M · Roadmap: management-plane*

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

## Field notes (proven 2026-10-30, tools PATH + live store)

- RED `474e2b6` (12 ledger tests + 3 schema tests + 1 strong
  p12→p13 migration), GREEN `1f1d116`: `ProjectService` owns the
  durable ledger (`events.yaml` + `ledger.yaml` under
  `ENGINE_ROOT/projects/<id>/`, both schematized optional +
  tracked so the derived gitignore is unchanged, schema stays
  v1); `Engine` passes `engine_root` through and appends
  `run_completed`/`run_failed` from `run()` with the full
  verdict; `get_events_since` is a wired query.
- Contract decisions: ack carries the advanced
  `current_revision` so writers follow the head; idempotent
  replay returns the stored ack *before* the revision gate (a
  retry necessarily carries a stale revision); `run_failed`
  means NOT_RUN, a FAIL verdict is a completed run; linked
  projects keep their ledger in ENGINE_ROOT (never in the
  caller tree); in-memory default preserved (durable only with
  explicit `engine_root`); sequential multi-handle writers stay
  ordered via reload-first, true file locking is future work.
- Migration kept strong: `test_mcp_live` now pins p12→p13 on
  the ack and the snapshot; the stale-revision conflict tests
  still use truly-stale revisions. No scenario YAML changed
  (all single-submit; each engine starts at p12).
- Evidence: full suite 690 passed (587 + 103 validate, 0
  fail); docstring + no-cloud gates exit 0; scenarios 26/0;
  correctness gate 4/4 (44/0/0).
- Residual (non-blocking): cross-process file locking for
  concurrent writers; `ledger.yaml` request-map compaction.
