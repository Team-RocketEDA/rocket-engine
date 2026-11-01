# API-V1-CORE: Implement shared v1 runtime, discovery, references and lossless admission

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CONTRACT, ENTITY-CAS. Read ADR-014, ADR-011, contracts/README.md and docs/work/API-V1/execution-review.md. Use canonical schemas; no new payload copy.

Implement one EngineRuntime for both adapters; describe/query registry without project imports or second Engine; working vs pinned references and snapshot resolution; typed request association queries; durable fast admission and immediate dispatch; advisory capacity pause/resume, saturation admitted:false and same-ID retry; no silent accepted loss. Reserve controls/short writer/read/event responsiveness. Equivalent in-flight artifact tasks coalesce across clients; scripts/edits never coalesce. Distinguish request retry from fresh run, policy gate override and quarantine override. Restart reports survivors, runs nothing until explicit resume/discard; completed reruns use fresh starts. Cancel tracks attributed request/completion and children accurately. Execution state, verdict, failure and committed effects are distinct.

Decompose source modules before 3000 lines; first reduce oversized project service and composition. Atomic entity/read-dependency CAS; global revision is cursor, not unrelated-write conflict gate. Meet C01-C17 execution acceptance scenarios and fail closed on I28 drift. No refactor of consumers until generated-boundary fixtures are shared.
