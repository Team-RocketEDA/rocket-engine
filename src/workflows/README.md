# workflows — process knowledge as data (never executes)

## Responsibility (PRD)

The ordered domain processes — digital D01–D30, analog A01–A23,
photonics P01–P23, mixed assembly M01–M16 — with required/conditional
stages, prerequisites, and entrypoint bindings to engine operations
([verification-process](../PRD/tools-research/verification-process.md),
[verification-workflows](../PRD/tools-research/verification-workflows.yaml),
operation phases in the catalog). Source for `plan_checks` and the
IDE's check-plan display. Required stages stay required even when
their backend is absent (a missing stage blocks "fully verified").

## Inputs

- PRD process inventory (prose source, above).

## Outputs

- Stage tables, entrypoint maps, applicability rules consumed by
  `execution/` (planning) and the UI (display).

## Boundaries

Owns: process data. Must not own: solver invocation, scheduling,
verdicts — this module never calls a tool.

## Routing

- Adding a check type → `../interfaces/README.md` (operation) +
  `../adapters/README.md` (tool) + a plan slot here.
- Stage visibility rules → invariants I25–I27.

## Status

GREEN (slice 4): `stages.py` (full D/A/P/M inventory +
`applicable_stages` planner). Prose `when` evaluation is a later
slice; v1 treats every planned stage as required. Tests:
`tests/workflows/` (3 passed).
