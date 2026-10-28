# interfaces — the engine's contract (single source of truth)

## Responsibility (PRD)

Every shape the engine speaks is defined once, here: wire schemas
([suggested-api §1–§9](../PRD/tools-research/suggested-api.md): objects,
references, components, schematic/layout views), the typed command and
event envelopes
([frontend-tooling-spec §2–§4](../PRD/tools-research/frontend-tooling-spec.md)),
the operation catalog
([tooling-operations.yaml](../PRD/tools-research/tooling-operations.yaml),
to be vendored here), and the outbound ports (`ToolAdapter`,
`IsolationRunner`, `CatalogProvider`). Blueprint B1, as amended
(`contracts/` merged here — see `docs/prd-feedforward.md` F2).

## Inputs

- PRD YAML catalog and API proposal (prose sources, above).
- Pydantic v2 + `ruamel.yaml` (stack-pinned).

## Outputs

- Validated types every module imports; port types generated from
  schemas (never hand-copied twice); one contract test proving
  schema↔type agreement.

## Boundaries

Owns: shapes, validation, port definitions. Must not own: any I/O,
any transport or solver code, any business rules.

## Routing

- Implementing a transport or tool → `../adapters/README.md`.
- Running jobs or holding state → `../execution/README.md`,
  `../project/README.md`.
- Which check runs when → `../workflows/README.md`.

## Status

GREEN (slice 1): `documents.py` (strict validator), `references.py`
(resolution + connection checks), `errors.py` (`ContractError`).
Invariants I01, I02 proven. Tests: `tests/interfaces/` (12 passed).
