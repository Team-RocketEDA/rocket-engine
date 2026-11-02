# COALESCE-I33: Request coalescing per I33 (revision-pinned, force bypass)

*Status: Done · Depends: none · Size: M ·
Roadmap: convergence (MVP track, spam-click safety)*

## Why

An agent (or a spam-clicking human) will submit the same
run N times. Executing all N wastes solver-hours and
floods the ledger; worse, without a revision pin the Nth
request could silently share a verdict computed against
a project that has since changed. I33 makes the rule
exact: identical concurrent content on an unchanged
revision executes once, everybody shares the run_id —
and any intervening mutation breaks coalescing
unconditionally, because a stale verdict must never
serve as fresh.

## What

- RED-first: content key = operation + normalized
  arguments incl. deck hash + run.request; coalesce only
  across overlapping lifetime (queued/running) on the
  SAME project revision with no intervening mutation.
- Shared run_id fanned out to all callers; every
  request_id logged mapping to it; completed results
  serve via idempotent fetch, never coalescing.
- Force bypasses coalescing (forced re-runs execute
  fresh); revision moved between requests → separate
  executions, unconditionally.

## Acceptance

- 5 identical concurrent submits → 1 execution, 5
  mapped request_ids; mutation between submits → 2
  executions; forced duplicate → fresh execution.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
