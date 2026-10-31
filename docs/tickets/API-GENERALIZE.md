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

## Field notes (2026-11-01): gating gaps, decisions taken

- Force touches gating ONLY: never bypasses admission
  (malformed stays reject-all), prerequisite checks (no
  deck/PDK, no run), or verdicts (forced runs report real
  FAILs — force runs steps, never greens them).
- Force permission (MVP): human approval per call, matching
  the fuel permission model. Allowlist-per-flow is the
  later relaxation. Agents never self-approve force.
- Forced steps wear `forced: true, forced_by` in ledger +
  provenance. A downstream green after a bypassed red gate
  is legitimate only if inspectable.
- One snapshot per job, frozen at submit; all steps read
  it; recorded once. Mid-batch edits never change later
  steps' inputs (I28 load-bearing).
- Timeouts: per-step (timeout = error state → gates
  dependents) plus a job-level ceiling. Static default +
  explicit override for MVP; no silent hangs.
- Cancellation reason: cancelled job marks remaining steps
  `cancelled`, distinct from `skipped_after_failure` and
  NOT_RUN — fail/gated/stopped stay three answers.
- Step addressing: ack returns ordered step index →
  step_id map; queries accept either. No invented
  conventions.
- Gate table v0 (lane's first deliverable): crash-states
  gate dependents always; FAIL verdicts gate only where
  the flow template says so (e.g. synth→sta); sweeps never
  gate each other.
- No auto-retry in MVP, stated explicitly: transient flake
  → chain skipped → agent resubmits. Retries hide real
  failures; nothing retries inside adapters.

## Field notes (2026-11-01): replay scope, async boundary, coalescing

- Replay replays SURVIVORS only: ledger-admitted runs with
  no completion event get executed after reboot. Finished
  runs are NEVER re-executed, and no transcript of
  completed job_ids is ever re-run to reconstruct state —
  runs are reproducible from (snapshot + deck + params),
  resubmit-when-wanted covers everything.
- Console restores-as-idle: history + cwd + env persist
  across close (MATLAB shape), kernel starts fresh, zero
  auto-rerun. Session close drops runs, never replays them.
- Async boundary, sync core: endpoints never block callers
  (ack fast, queue, stream progress, accept cancel) while
  a 20-minute solver runs; the sync core is bridged by a
  bounded executor, NOT an asyncio rewrite. 0% drop comes
  from the durable log + typed refusal, not from async.
- I33 (proposed): request coalescing. Concurrent
  run-submits with identical normalized content —
  operation + arguments incl. deck hash + run.request —
  against the SAME project revision with no intervening
  mutation execute ONCE; all callers share the run_id and
  the fanned-out result, each request_id logged mapping
  to it. Revision moved between requests → separate
  executions, unconditionally (stale verdicts never serve
  as fresh). Force bypasses coalescing (forced re-runs
  execute fresh). Completed results serve via idempotent
  fetch, not coalescing — coalescing covers overlapping
  lifetime (queued/running) only.
