# library — PDK and reusable-cell catalogs

library/ supplies catalog lookups used by operations and capability checks. It currently contains PDK context/catalog logic and the APIG cell catalog; solver execution remains in adapters/ and project revisions remain in project/.

## PDK catalog

catalog.py resolves versioned PDK references, reports per-operation readiness, registers and verifies catalog entries, and provides cell instantiate/promote helpers. The file-backed PDK registry and asset resolver live in [interfaces/pdks.py](../interfaces/pdks.py); registration records a revision and content identity, and upstream files are treated as read-only inputs.

## Cell catalog

apig_catalog.py combines static providers with a GDSFactory provider, normalizes cell metadata, and supports list/get/placement methods. The engine currently exposes the list_cells query; the generated API marks place_cell unwired, and get_cell is not a public engine query yet. Check the [generated API](../../docs/engine-api.md) before depending on a caller-facing operation.

## Readiness

Catalog metadata is distinct from verification. get_capabilities reports whether a tool, PDK, or deck is ready on the current machine and includes a remedy for blocked items. Registering a PDK or cell does not imply a design has passed its checks.

## Routing

- PDK bytes, profiles, and setup probes → [interfaces](../interfaces/README.md) and [provision plan](../../docs/provision-plan.md).
- Project component state and revisions → [project](../project/README.md).
- Adapter execution → [adapters](../adapters/README.md).
- Product PDK model → [PRD PDK abstraction](../../../PRD/tools-research/pdk-abstraction.md).
