Problem: mega-module trajectory breaches the ceiling: project/service.py 2247 + composition.py 1576 + routing/namespace.py 764 + mutate/__init__.py 776 + connectgraph.py 734 lines. Worse: settings_store (1188) + engine_ecs_store (1466) + wireplace (1324) + layer_serving (1023) do real I/O inside interfaces/ whose docstring says "No I/O, no logic" — the hexagonal direction (interfaces = data contracts) is violated. Mixins split files but share all private state (organizational seam, not contractual). Deferred-import cycles papered over (ops<->composition, project->execution).
Expected-per: API-V1-CORE.md:9 decomposition order; AGENTS.md module-size rule; hexagonal direction. Audit M-01/M-02/M-11, D-14.
Fix: decompose composition dispatch/queries/serving + project service; move the four stores out of interfaces/ behind ports; type the v0 envelopes (submit command, findings, events) as the v0->v1 mapping table (needed anyway for D-05/D-06/D-08/D-10/D-11 renames).

## Verdict (Wave-3, 2026-11-03) — next slices landed, gates green

*Composition shrink (1979 -> 1973, limit 2000):* `_describe_op`
moved to `ops/queries.py`, `replay_pending` to `ops/deferred.py`;
Wave-3 wiring added as tables plus thin dispatch
(`_CRUD_OPERATIONS` +14 editor ops, `QUERY_METHODS` +22 read
mappings, `_EDITOR_READS` -> `_EditorMixin._query_editor`).
`QUERY_ENGINE_METHODS`/`ENGINE_OP_METHODS` untouched (api_spec
AST pins honored).

*Service (2309 -> 2977, limit 3000):* 13 editor/testbench ops +
7 computed reads as thin envelope delegates
(`_editor_mutation`/`_editor_read` in `ops/editors.py`); deletion
rides the existing generic `delete_entity`; typed delete/shape
verbs deferred. Headroom is thin (23 lines) — the next slice
that adds verbs must move bodies to `ledger/` (sibling lane).

*Stores behind ports:* `ops/ports.py` exposes the four concrete
store bindings plus port Protocols; `project/service.py`
consumes stores through it (pinned by
`tests/test_service_split.py`). Protocols are not yet injected
— the next slice can swap fakes without touching call sites.

*EngineRuntime integration:* `Engine` owns one `EngineRuntime`
bound to the ledger-admitting solver lane (`ops/deferred.py`):
`deferred_submit` prompt-ack, `deferred_pump`/`deferred_wait`,
`merge_ack_completion` merge, survivors/resume/discard/cancel/
watch served straight from the runtime. Synchronous submit is
byte-identical; every ledger mutation advances the runtime
cursor for coalescing parity. Pinned by
`tests/test_composition_split.py` (Wave-3 gates).

*I28 closure pins:* `interfaces/refs.py` (closure/template/entity
pins only) attached to every editor receipt and testbench
record/describe.

Gates: composition_split 30 passed, service_split 8 passed,
api_spec + docstrings clean for owned files (3 remaining
docstring violations are pre-existing in untouched
adapters/cace + hdl_sim), regenerated api-schema/help +
engine-api via `api_spec.py --write`.
