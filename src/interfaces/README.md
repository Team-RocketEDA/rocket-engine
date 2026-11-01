# interfaces — shared engine contracts and design data

`interfaces/` defines the operation and query vocabulary, shared records, validation helpers, and ports used across the engine. It is the source for the command names and core shapes that transports and solver adapters share.

## What lives here

- `vocabulary.py`, `ports.py`, and `errors.py`: operation/query names, the `ToolAdapter` and other boundary types, and contract errors.
- `documents.py`, `references.py`, `paths.py`, and `runparams.py`: document validation, reference resolution, path containment, and run-parameter validation.
- `engine_ecs_store.py`, `wireplace.py`, `celllink.py`, and `layout.py`: entity/component, schematic connectivity, cell-link, and layout data operations.
- `settings_store.py`, `layout_schema.yaml`, and `yaml_dump.py`: project settings and persisted design-data formats.
- `pdks.py`, `setup.py`, `setup_catalogue.yaml`, and `setup_probes.py`: PDK registration/verification and tool readiness support. The PDK registry performs bounded filesystem I/O; this module is no longer entirely I/O-free.

The module does not invoke EDA solvers. Some low-level stores and registries are colocated here; project revisions and event ordering belong to [`project/`](../project/README.md), while user-facing engine operations are dispatched by [`composition.py`](../composition.py).

## API contract generation

The operation vocabulary is maintained in `vocabulary.py`. Google-style handler docstrings feed `scripts/api_spec.py`, which generates `docs/engine-api.md`, `docs/api-schema.json`, and `docs/api-help.json`. Those generated artifacts must not be edited by hand. The [contributor rules](../../AGENTS.md) describe the required docstring shape; the [generated API reference](../../docs/engine-api.md) is the current operation and query inventory.

## Routing

- Add or change a transport or solver edge → [`adapters/`](../adapters/README.md).
- Change revision, document, or event behavior → [`project/`](../project/README.md).
- Change run lifecycle or verdict evaluation → [`execution/`](../execution/README.md).
- Change stage coverage or completion rules → [`workflows/`](../workflows/README.md).
- Product-level contract → [PRD tooling spec](../../../PRD/tools-research/frontend-tooling-spec.md) and [tooling operation catalog](../../../PRD/tools-research/tooling-operations.yaml).
