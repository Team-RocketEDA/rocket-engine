# SPLIT-LOCK-HARDEN: Assert thin surfaces on split mega-modules

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

[REFACTOR-SERVICE](REFACTOR-SERVICE.md),
[REFACTOR-COMPOSITION](REFACTOR-COMPOSITION.md) and
[REFACTOR-EXEC](REFACTOR-EXEC.md) are Done, but the review found the
split-lock tests assert only ops/ledger existence — nothing pins the
thin surface (module line-count ceiling, no-business-logic-in-split
shims, no reintroduced mega-file). `composition.py` (2250 lines),
`service.py` (2941) and `execution/runtime.py` (1149) still sit near
the ceiling with no guard against regrowth.

## Goal

Regrowth structurally impossible without a red test.

## Scope

- Add a size/dependency lock test: per-module line ceiling + forbidden
  import directions (execution→adapters already covered by
  DISPATCH-PORTS-FIX guard; extend to composition/service/runtime).
- Assert split facades carry no logic (delegation-only check).

## Acceptance

- Lock test green; a deliberately fattened module or a new
  execution→adapters import fails the suite loudly.
