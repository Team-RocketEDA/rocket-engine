# project — revisions, snapshots, events (owns state)

## Responsibility (PRD)

The project service: scoped commands, expected-revision preconditions,
immutable input snapshots, idempotent `request_id` handling, file
watching, and the ordered persisted event log with snapshot+cursor
resync ([frontend-tooling-spec §3–§4, §6](../PRD/tools-research/frontend-tooling-spec.md),
[suggested-api §4, §9](../PRD/tools-research/suggested-api.md)).
Actor identity comes from trusted caller context, never the payload.
Blueprint B3.

## Inputs

- Validated commands (via `interfaces/` ports).
- Saved source revisions + native-file change notifications.

## Outputs

- Snapshots, run admissions, ordered events (`job_queued` … `check_updated`
  … `job_finished`), resync cursors.

## Boundaries

Owns: state, ordering, identity. Must not own: tool output parsing,
transport protocols, check verdicts.

## Routing

- Shapes of commands/events → `../interfaces/README.md`.
- Job lifecycle after admission → `../execution/README.md`.
- Which checks exist → `../workflows/README.md`.

## Status

Scaffold — package + this contract only. Slice 1 (with B1).
Invariants I05 (caller parity), I06 (retries/stale writes), I07 (event
recovery). Tests: `tests/project/` (fake adapter; real qualification
waits for slice 4).
