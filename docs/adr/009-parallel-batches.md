# ADR-009: Batches dispatch concurrently with per-item cancel

*Status: accepted (2026-11-01) | Tickets: [BATCH-PARALLEL](../tickets/BATCH-PARALLEL.md), [MCP-CONTRACT](../tickets/MCP-CONTRACT.md)*

## Context

Batch exists so parallel requests dispatch to tools at
once — but `--batch` runs sequentially, `run_job`
pumps in order, and cancel is not on the wire. The
agent's iteration loop pays full serial latency for
independent sims, and a regretted long run cannot be
stopped. The substrate exists (bounded FIFO pool,
`pool_full` backpressure, identical-submit coalescing,
worker-tree kill); it is not composed.

## Decision

`run_job` batches dispatch concurrently over the
bounded pool: reads/sims parallelize freely,
same-entity mutations serialize via per-entity CAS
(ADR-008), identical concurrent submits coalesce,
gated items wait on ADR-004 gates, and every item is
independently `cancel_job`-able with honest per-item
states (worst-state-wins summary). This supersedes the
"sequential unless perf demands" deferral.

## Alternatives considered

1. **Stay sequential.** Rejected: agent iteration
   speed is the product's inner loop; serial latency
   is the tax on every repair cycle.
2. **Unbounded parallelism.** Rejected: solver
   processes are heavy (ngspice, librelane); the pool
   bound + `pool_full` refusal protects the machine
   and the ledger.
3. **Cancel whole batch only.** Rejected: coarse;
   killing 4 good sims to stop 1 bad one wastes the
   very time parallelism saves.

## Consequences

- Positive: N independent sims cost ~1x single-sim
  time; regret is one `cancel_job` away.
- Positive: pool bound keeps the machine safe; gates
  keep parallel dispatch legal.
- Negative: the bounded pool + CAS + gates
  interaction is the most concurrent code in the
  engine — needs the strictest tests (acceptance
  pins concurrency, per-item cancel, pool_full).
