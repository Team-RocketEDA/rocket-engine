# Architecture Decision Records

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](001-engine-storage-boundary.md) | Engine owns its root; callers own their files | accepted | 2026-10-29 |
| [002](002-engine-owns-project-ledger.md) | Engine owns the project ledger; ADR-001 owns the bytes | proposed | 2026-10-30 |
| [003](003-docstring-generated-api-contract.md) | API contract generated from Google-style docstrings | v0 only; v1 superseded by 014 | 2026-10-30 |
| [004](004-engine-side-op-gates.md) | Engine-side depends_on and gate-on-verdict guardrails | accepted | 2026-11-01 |
| [005](005-caller-blind-engine-client-edge-approvals.md) | Fuel owns language and approvals; the engine is caller-blind | accepted | 2026-11-01 |
| [006](006-localhost-only-http.md) | HTTP is localhost-only and unauthenticated | accepted | 2026-11-01 |
| [007](007-coverage-map-and-decks.md) | Stage tables are the coverage map; adapters are the decks | accepted | 2026-11-01 |
| [008](008-per-entity-cas.md) | Concurrent collaboration via per-entity CAS | accepted | 2026-11-01 |
| [009](009-parallel-batches.md) | Batches dispatch concurrently with per-item cancel | accepted | 2026-11-01 |
| [010](010-hand-rolled-ecs-store.md) | Hand-rolled stdlib ECS store, no ECS library | accepted | 2026-11-01 |
| [011](011-one-runtime-durable-admission-and-client-neutral-operations.md) | One client-blind runtime with durable admission and scoped design operations | accepted | 2026-11-01 |
| [012](012-always-editable-layer-catalog-and-process-bindings.md) | Always-editable layer catalog with separate process bindings | accepted; partially superseded | 2026-11-01 |
| [013](013-magic-aligned-technology-driven-layout.md) | Magic-aligned, technology-driven layout editing | accepted | 2026-11-01 |
| [014](014-contract-first-editor-and-tool-api.md) | Contract-first editor, component, tool and testbench API | accepted design; migration pending | 2026-11-01 |
| [016](016-console-apply-context.md) | Atomic session apply-context replaces per-verb console exfiltration | accepted | 2026-11-03 |
| [017](017-shared-engine-port-bus.md) | Shared-engine port bus with async QoS-1 delivery | accepted | 2026-11-03 |
