# API-GENERALIZE: Frontend protocol — queue, microcommits, catalogue, symbols

*Status: Backlog · Depends: none · Size: L (phased) · Roadmap: orch-build-mvp*

## Why

The IDE bolts onto engine duplex channels (STDIO first) as pure
presentation: engine owns truth, frontend owns pixels. Three gaps
block pick-and-place/drag-and-drop at KiCad comfort today: (1) no
durable never-drop request path under UI spam, (2) no component
catalogue query + place op (frontend cannot import gdsfactory),
(3) no symbol serving (PDK has 685 xschem `.sym`, zero SVGs).
Frontend/engine disagreement is catastrophic-class: every gap
below closes a divergence vector.

## What (phased slices)

1. Durable request log + worker pool: append-first per-project
   log, `request_id` dedupe, in-order drain, one ack per request,
   boot replay. Refusal/backpressure shape, never silent drop.
2. Microcommit delta format: coalesced frontend edits (move/add/
   wire) → one revision bump via existing hash machinery.
3. Catalogue index query: versioned cell list (cell, PDK, ports,
   default params) introspected from upstream, plus
   `place_cell` durable project mutation.
4. Raw asset serving (I29): serve PDK bytes verbatim at every
   granularity — single `.sym` as-is, metadata, bulk. No
   conversion, no rendering; parsing and styling stay
   frontend-side. Hash-checked identity on every serve.

## Acceptance

- Spam test: N rapid placement edits → all N acked exactly once,
  frontend revision equals engine revision, zero divergence.
- Catalogue round-trip: list → place → simulate → verdict,
  all through the duplex channel, no console needed.
- Kill-and-reboot mid-queue: log replays, every request still
  acked exactly once.

## Revision (2026-10-30): partially superseded, narrowed

- Slice 1 (durable log half) → LEDGER-DURABLE. The worker
  pool half (in-order drain, backpressure/refusal shape,
  boot replay) REMAINS here.
- Slice 2 (microcommits) → CRUD-API (`apply_mutations` batch).
- Slice 3 (catalogue index + `place_cell`) REMAINS here —
  no other ticket covers the component catalogue.
- Slice 4 (raw asset serving, I29) REMAINS here — no other
  ticket covers verbatim PDK byte serving.
- New scope: pool/drain/backpressure + catalogue/place_cell
  + raw serving. Kill-and-reboot acceptance stays (needs
  pool, not just log).

## Field notes (2026-11-01): submit executes immediately

Queue-by-default is rejected: `submit()` now executes the job
immediately (inline, same `run_id` ack shape, same verdict
payload). `run_job` stays for explicit/deferred/batch pumping
plus idempotent result fetch. Rationale: a headless engine
that parks work until someone remembers a second call is a
scheduler, not an engine — running is the default, queueing
the opt-in. Keep the ack shape stable; fuel harness already
runs queued jobs before replying, so this tightens rather
than breaks the agent path.

## Field notes (2026-11-01): batch submit, one job ID, sequential

`submit()` accepts a single command OR a list of commands
(multiline/batch) in the same API. One call → one job ID →
steps execute sequentially in order. A single job is the
degenerate batch of one; no separate batch endpoint, ever
(per composite-command pattern). Each step keeps its own
step identity + verdict inside the job record; the job
verdict aggregates (FAIL if any step fails). Failure policy:
fail-fast by default — remaining steps go NOT_RUN with
reason `skipped_after_failure`, never silently skipped.
`run_job(job_id)` pumps/completes and fetches idempotently
for both shapes. Rationale: agents think in scripts, not
single shots — one ID to track, deterministic order, no
client-side orchestration to get wrong.

## Field notes (2026-11-01): gating policy decisions

- Verdicts CAN gate (`gate_on_verdict`): a FAIL verdict
  blocks downstream steps unless the call carries `force`.
  Force bypasses verdict gates ONLY — hard `depends_on`
  failures (error/NOT_RUN state, no data produced) are
  NEVER forceable. No flag runs a step whose inputs don't
  exist.
- Malformed batch (bad step args, unknown dep id):
  reject-all at admission. No partial execution of a
  misunderstood batch.
- `depends_on` is maintainer-owned, NEVER an API argument:
  engine flow templates declare the step DAG; callers
  submit steps, the engine knows the dependencies.
- Sequential execution only. Threadpooling/parallel
  scheduling is backlog, post-MVP, only if performance
  demands it. Stay lean.
- The engine provisions ALL IDs (job, step, run). Callers
  track what they're given; nothing caller-minted except
  `request_id` for dedupe.
- MVP bar: a verification engine strong enough for an AI
  agent to make a chip literally today.
