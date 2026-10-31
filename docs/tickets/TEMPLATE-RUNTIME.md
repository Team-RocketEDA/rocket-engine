# TEMPLATE-RUNTIME: Runtime-modifiable project templates

*Status: Backlog · Depends: LAYOUT-SCHEMA · Size: S · Roadmap: orch-build-mvp*

## Why

Source-baked schemas are correct for MVP stability, but PDKs and
power users will eventually need layout variants (extra areas,
custom config) without forking the engine. Parking this now is
deliberate: runtime templates unlock a feature class (user-defined
project shapes) that needs the base template + migrations proven
first, lest modifiability arrive before stability.

## What (when scheduled)

- Custom template loading + validation against the base template
  (extensions only where allowed); versioned like everything else.

## Acceptance

- Custom template loads, validates, migrates; invalid custom
  template fails loudly naming the violation.
