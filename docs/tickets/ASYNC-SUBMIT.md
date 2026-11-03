Problem: Engine.submit admits, drains, and merges completion inline (composition.py:395-406,683,690) — the run_id arrives with the verdict already attached. No deferred handle exists to watch.
Expected-per: frontend-tooling-spec.md:117 (prompt ack without verdict) + :158-162 (job_queued/started/progress/finished events). Audit MC-02, X-07.
Actual-per: submit always blocks to completion; none of the lifecycle events are emitted.
Ruling: RULING-02 (contract wins) — implement prompt-ack/deferred-handle mode + lifecycle events. Note X-07: MCP-CONTRACT's "run controls + watch/query" reading is equally unmet (no watch exists) until this + PUSH-EVENTS land.

## Verdict (runtime slice, 2026-11-03)

Done in `src/execution/runtime.py` (new: EngineRuntime with
deferred handles) plus `src/execution/queue.py` (new: bounded
deferred FIFO). TDD RED was `ModuleNotFoundError:
rocket_engine.execution.runtime`; GREEN is 22 passed plus 1
loud skip (`tests/test_async_submit_deferred.py`,
`tests/execution/test_runtime_deferred.py`, overlay-verified
against the installed package — the checkout venv is a
non-editable copy, so grading must reinstall before running).

Behavior: submit returns the receipt (admitted, run_id,
request_id, snapshot_id, revision, event cursor) with no
verdict; the handle poll/waits to the terminal completion;
lifecycle emits job_queued/started/progress/finished in order
(buffered pre-start progress flushes after job_started; a
synthetic progress heartbeat covers silent runners; late
progress is refused, never logged).

Engine.submit integration seam (composition.py untouched —
surface lane owns it): route solver operations to
`EngineRuntime.submit(operation, arguments, request_id)` for
the prompt ack, merge the terminal completion with
`execution.apig.submit.merge_ack_completion`, and serve
`list_survivors`/`resume_run`/`discard_run`/`cancel_job`/
`get_events_since` from `boot_report`/`resume`/`discard`/
`cancel`/`watch`.

*Verify 2026-11-03 (Step 7 closeout, post PR #4 merge):
handle-pre-verdict + `test_async_submit_deferred` green on the
merged tree; no owned files touched by the merge.*
