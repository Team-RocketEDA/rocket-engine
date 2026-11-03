# BATCH-PARALLEL: concurrent batch dispatch + per-item cancel

*Status: Ready · Depends: ENTITY-CAS, MCP-CONTRACT · Size: M ·
Roadmap: agent iteration speed (MVP track)*

## Why

Batch exists so parallel requests dispatch to tools
at once — but `--batch` is sequential, `run_job`
pumps in order, and cancel is not on the wire.
The agent's iteration loop pays full serial latency
for independent sims. The pieces exist (bounded
FIFO pool, `pool_full` backpressure, identical-submit
coalescing, worker-tree kill); they are not composed.
This supersedes the "sequential unless perf demands"
deferral: perf is demanded.

## What

- `run_job` accepts a batch: per-item run_ids
  dispatched to the bounded pool concurrently.
- Reads/sims parallelize freely; same-entity
  mutations serialize via ENTITY-CAS; identical
  concurrent submits still coalesce.
- Each item independently `cancel_job`-able
  (MCP-CONTRACT); batch reports per-item states,
  worst-state-wins summary.
- Bounded pool stays the substrate: same-revision
  scoped, no shared mutable solver state.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- N independent sims complete in ~1x single-sim
  time (test pins concurrency, not wall time).
- Cancelling item 2 of 5 leaves the rest
  completing with honest per-item states.
- Pool exhaustion refuses `pool_full` before
  touching the ledger (existing behavior kept).
