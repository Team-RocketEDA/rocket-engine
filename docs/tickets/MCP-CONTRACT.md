# MCP-CONTRACT: conform to fuel BOUNDARIES Contract 1 + expose cancel

*Status: Ready · Depends: none · Size: M ·
Roadmap: agent-driving surface (MVP track)*

## Why

Fuel's BOUNDARIES.md Contract 1 pins the shapes the
agent relies on: `run_job → {run_id, checks: {status,
measured, target, margin}, failing_required,
log_excerpt}`, exact `PASS|FAIL|NOT_RUN|UNSUPPORTED`
statuses, compact logs (first error first, ≤4k
tokens), string-matched errors
(`iteration_limit_reached`, `duplicate_revision`).
`cancel_job` sits on fuel's "still to agree" list —
while `Engine.cancel_job(run_id)` already exists
(`src/composition.py:1517`) with worker-tree kill
plumbed (`is_cancelled`), unreachable because it is
not in vocabulary. One ticket closes the shape gap
and the cancel gap together.

## What

- Conform engine replies to Contract 1 shapes,
  statuses, error strings, and compact-log rule;
  test against the stub's expectations.
- Expose `cancel_job` in vocabulary → submit → MCP:
  queued or running job by run_id, cancelled state,
  attributed durable cancellation request/completion events (ADR-014 supersedes the earlier no-event clause).
- `{request_id, run_id}` on every reply and log line
  so fuel chat and engine results join in the UI.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Fuel's stub-shaped assertions pass against the
  real engine bridge for run_job/cancel/status/log
  replies.
- Cancelling a running sim kills its worker tree
  promptly and reports `cancelled` (test pins).
- v0 shapes sunset into API-V1-CLIENTS (v1 envelopes
  + generated types); `cancel_job` and run_id joining
  persist across the migration.

## V1 migration amendment

Legacy fuel payloads remain compatibility inputs until both consumers migrate.
The new six-method boundary and generated help/types come from the canonical
v1 contract bundle (ADR-014); no handwritten fuel/IDE copies. `run_job` is not a
mandatory second start. Use run controls and watch/query for lifecycle evidence.
