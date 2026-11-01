# project — revisioned project state and event ledger

`ProjectService` owns engine-mediated project state: documents, the project revision, idempotent mutation requests, snapshots, and the ordered event ledger. It also exposes the component/entity queries used by the engine's ECS-shaped design model.

## State and persistence

- Every mutation checks `expected_revision`. A stale head returns `revision_conflict`; changes are never merged silently.
- Accepted mutations advance the project revision and append an actor-attributed event. Reusing a `request_id` with the same command replays its stored result; reusing it with different command text is refused.
- With `engine_root` configured, project ledger files, events, managed documents, and rewind snapshots persist beneath `projects/<project_id>/`. Without an engine root, `ProjectService` keeps them in memory.
- Event reads are cursor-based and bounded by retention. A reader that requires missing history receives `resync_required` and reloads the snapshot.
- `rewind` restores engine-managed bytes under a new revision; it does not rewrite history or overwrite caller-owned files in a linked project.
- `ledger.yaml`, `events.yaml`, `runs/`, and `snapshots/` are engine-owned paths and cannot be written through document CRUD.

## Design entities

Entities and components are projected through the project document store. IDs are engine-minted; component changes use the same project mutation/event path. The service also handles settings and wire/junction operations through the corresponding interface stores. `get_world_snapshot`, `get_component`, `components_of`, and `entities_with` provide read surfaces for clients.

## Boundaries

`ProjectService` owns project revisions, documents, snapshots, idempotency, and event ordering. Solver output parsing and verdicts belong to [`execution/`](../execution/README.md); transport framing belongs to [`adapters/`](../adapters/README.md). `Engine` in [`composition.py`](../composition.py) routes operations into this service.

## Routing

- Contract shapes and path rules → [`interfaces/`](../interfaces/README.md).
- Run admission, results, and verdicts → [`execution/`](../execution/README.md).
- External behavior → [generated engine API](../../docs/engine-api.md) and [storage policy](../../docs/storage-policy.md).
- Product semantics → [PRD tooling spec](../../../PRD/tools-research/frontend-tooling-spec.md).
