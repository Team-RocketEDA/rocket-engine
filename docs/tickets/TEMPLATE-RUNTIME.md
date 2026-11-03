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

## Verdict (2026-11-03, landed)

Done: new `src/project/templates/` package (`__init__.py` public
API plus `errors.py`; small modules, Google docstrings per the
docstring gate). RED: `tests/project/test_templates.py` failed 9/9
on the missing module; GREEN after implementation (9 passed).
`load_template`/`loads_template` migrate (registered one-step links,
mirroring `settings_store`: `future_format` when newer than known,
`missing_migration` naming the unlinked step) then validate against
the base shape — extensions only where allowed (fixed top-level key
set, name-plus-label area entries, scalar config with the `engine.`
namespace reserved). Every rejection names its violation (key, area
index, or config entry). Service/CRUD wiring is deliberately out of
scope: loading + validation + versioning only, per the ticket.
