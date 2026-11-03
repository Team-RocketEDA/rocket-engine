# API-V1-CORE: Implement shared v1 runtime, discovery, references and lossless admission

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CONTRACT, ENTITY-CAS. Read ADR-014, ADR-011, contracts/README.md and docs/work/API-V1/execution-review.md. Use canonical schemas; no new payload copy.

Implement one EngineRuntime for both adapters; describe/query registry without project imports or second Engine; working vs pinned references and snapshot resolution; typed request association queries; durable fast admission and immediate dispatch; advisory capacity pause/resume, saturation admitted:false and same-ID retry; no silent accepted loss. Reserve controls/short writer/read/event responsiveness. Equivalent in-flight artifact tasks coalesce across clients; scripts/edits never coalesce. Distinguish request retry from fresh run, policy gate override and quarantine override. Restart reports survivors, runs nothing until explicit resume/discard; completed reruns use fresh starts. Cancel tracks attributed request/completion and children accurately. Execution state, verdict, failure and committed effects are distinct.

Decompose source modules before 3000 lines; first reduce oversized project service and composition. Atomic entity/read-dependency CAS; global revision is cursor, not unrelated-write conflict gate. Meet C01-C17 execution acceptance scenarios and fail closed on I28 drift. No refactor of consumers until generated-boundary fixtures are shared.

## Verdict (runtime slice, 2026-11-03)

Implemented standalone in `src/execution/runtime.py` (new)
plus `src/execution/queue.py` (new). TDD RED was
`ModuleNotFoundError: rocket_engine.execution.runtime`;
GREEN is overlay-verified (checkout venv is a non-editable
copy — grading must reinstall). composition.py,
vocabulary.py, submit.py untouched; the Engine.submit seam is
recorded in ASYNC-SUBMIT.md.

| ID | State | Evidence |
|---|---|---|
| C01 | Pinned | `validate_request` + schemas/operations injection; unknown fields/names refused |
| C02 | Deferred | No second payload copy: runtime consumes injected registry only; generator derivation stays surface-lane work |
| C03 | Pinned | Discovery reads the injected registry; no second engine, no project imports |
| C04 | Pinned | One runtime owns ledger-facing state (requests, coalescer, queue, event order) |
| C05 | Partial | Revision cursor + per-request identity; per-entity CAS stays project-service work |
| C06 | Pinned | Shape/schema validation precedes any record or enqueue |
| C07 | Pinned | `max_inflight` bound, `admitted:false` + retryable, pause/resume, same-ID retry admits once |
| C08 | Pinned | Durable request/run mapping queryable after disconnect; `wait_for` recovers |
| C09 | Pinned | 5 identical in-flight share one execution via `Coalescer` |
| C10 | Pinned | Intervening edit, changed args, fresh content, scripts/edits all execute separately |
| C11 | Pinned | Immediate dispatch (`auto_dispatch` worker or explicit `pump`); no pump handshake |
| C12 | Pinned | Cancel/query/events bypass capacity; edits ride their own lane (`apply_edit`) |
| C13 | Pinned | Attributed cancel, truthful terminal states, late progress refused |
| C14 | Pinned | `boot_report` (no autoexec), explicit `resume`/`discard`, quarantine + override |
| C15 | Pinned | Pinned ingredients + `check_drift` field report; never silent substitution |
| C16 | Pinned | Ordered `watch` with stable seq; expired cursors fail with resubscribe path |
| C17 | Noted | v0 behavior untouched (append-only adapter changes); migration switch stays surface-lane work |

Binary-gated acceptances (opensta/librelane absent, no
network/docker daemon): lanes are implemented against
`probe_host_tool`; absence loud-skips with
BLOCKED-needs-host, presence executes — never faked green
(`test_host_tool_probe_is_loud_never_faked_green`,
`test_timing_lane_loud_skips_without_sta`,
`test_docker_lane_loud_skips_without_daemon`).
