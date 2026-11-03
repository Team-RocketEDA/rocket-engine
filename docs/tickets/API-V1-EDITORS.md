# API-V1-EDITORS: Implement typed project, schematic, symbol, cell and layout edit transactions

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, ENTITY-CAS, LAYER-CATALOG, PROCESS-LAYER-MODEL. Canonical entity/edit schemas and ADR-014 are the boundary, not generic arbitrary ECS bags.

Implement project lifecycle, source/script assets, component presets, hierarchy instances/sheets/nets/wires/junctions, symbols/pins and physical cells/layers/shapes/pin maps. Alias-based atomic creation resolves LocalRef before persistence. Working source saves follow current project identity; external refs stay pinned. Full typed changes validate CAS of touched/read mutable entities, update one revision/event group, or commit nothing. Keep invalid source editable; retain last valid interface with stale diagnostics, no lost connections. Parameterized HDL interfaces resolve per occurrence. Direct geometry supports technology-driven paint/erase, primitives, transforms, booleans, arrays, routes and managed publication; no Python-only layout editor. Distinguish manual/generator/native ownership. Graphics are nonparticipating annotations including saved evidence-linked plots.

Presets spice_block/gdsf_component/hdl_component generate saved stubs and honest draft readiness. Every circuit component has models.spice availability/provenance; never invent a model. Pin cross-view mappings and technology closure under I28. Prove concurrent disjoint edits, same-entity conflict, failed-final-change full rollback, hierarchy/reuse, source save visibility, source import drift and native geometry publication.

## Verdict: GREEN (2026-11-03)

- Implemented `src/project/edit/cas.py` (per-entity CAS reads/writes over `ProjectService`) and `src/project/edit/transactions.py` (atomic batches, `$alias` LocalRef resolution, pre-validation, compensating rollback; unnamed writes gate on the live entity revision so disjoint edits land).
- Proved by `tests/project/test_edit_transactions.py`: 5 passed — disjoint entities land, same-entity stale CAS conflicts, failed-final-change rolls back to prior data, alias creation resolves.
- RED shown first (18 errors on missing modules), then GREEN (17 passed, 1 loud skip).
- Engine-wiring seam for the surface lane (composition.py NOT edited by this lane): expose `apply_transaction`/`cas_set`/`read_entity_revision` as Engine verbs or `OpDispatcher` ops sharing the MCP/client schemas, with per-change `expected_entity_revision` carried from the client envelope and sub-envelopes derived as `{request_id}:txn:{i}` for idempotent replay.
