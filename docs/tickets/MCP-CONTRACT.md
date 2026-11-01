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
  no ledger event (like every cancelled job).
- `{request_id, run_id}` on every reply and log line
  so fuel chat and engine results join in the UI.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Fuel's stub-shaped assertions pass against the
  real engine bridge for run_job/cancel/status/log
  replies.
- Cancelling a running sim kills its worker tree
  promptly and reports `cancelled` (test pins).
