# library — PDKs, profiles, reusable IP (owns catalogs)

## Responsibility (PRD)

Everything the engine looks up instead of computes: metadata-only PDK
discovery (no imports during search), prepared-profile catalog with
immutable environment identities, and IP
search/register/instantiate/promote with dependency closure and cycle
checks ([pdk-abstraction](../PRD/tools-research/pdk-abstraction.md),
[suggested-api §5, §6, §9](../PRD/tools-research/suggested-api.md),
[deep-dive §6](../PRD/tools-research/gdsfactory-api-deep-dive.md)).
Upstream PDK files stay read-only; registration grants reuse, never
verification. Blueprint B2 + B6 (one module: project/global records
share the same reference shape).

Known constraint, recorded not solved: CSPDK needs `gdsfactory~=9.51`
while the SKY130 wrapper needs `~=9.48` — separate worker envs until
reconciled upstream.

## Inputs

- PDK installation manifests, profile locks, component YAML manifests.

## Outputs

- Exact references, per-operation readiness (ready/blocked/
  unavailable/unsupported/unknown), immutable revisions, dependency
  closures.

## Boundaries

Owns: catalogs, references, closures. Must not own: geometry,
simulation, job execution.

## Routing

- Reference/record shapes → `../interfaces/README.md`.
- Readiness consumption → `../execution/README.md` (preflight).
- Environment placeholders → `../../app-resources/`.

## Status

Scaffold — package + this contract only. Slice 3. Invariants I03
(granular readiness), I04 (PDK isolation), I13 (bootstrap). Tests:
`tests/library/` (electronic + photonic fixtures).
