# DISPATCH-PORTS-FIX: Remove execution-side adapter import

*Status: Ready · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

`src/execution/dispatch.py:21` carries `from ..adapters import api`.
This violates the execution-ports-only rule ([AGENTS.md](../AGENTS.md)
dependency arrows: `execution/ → interfaces/` ports only, never concrete
adapters) and the file's own docstring (:13-14).

Blame: introduced in `084eec3 fix(http)` — a recent regression, not
pre-existing drift. Adapter side is clean (mcp/pull.py, xschem/deck.py,
transports import only shared helpers).

## Goal

Execution depends on `interfaces/` ports only. No `adapters.*` import
anywhere under `src/execution/`.

## Scope

- Reroute whatever `dispatch.py` takes from `adapters.api` through an
  `interfaces/` port (or move the shared helper down/out per the F2
  ports-vs-edges rule).
- Add a regression guard: grep/import test failing on any
  `adapters` import inside `src/execution/` (extend the no-cloud-guard
  pattern, or `scripts/check_docstrings.py` sibling).

## Acceptance

- `grep -rn "from ..adapters\|from .adapters\|import adapters" src/execution/` empty.
- Full suite + docstring gate green.
