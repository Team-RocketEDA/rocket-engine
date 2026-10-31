# INVARIANT-PARTIALS: Close I01-guard, I28-replay, I12-auth gaps

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-15 + FIND-16 + FIND-17)*

## Why

Three PARTIAL invariants with concrete pins: the I01
guard rejects an alias fixture via the wrong guard
(documents.py:24); I28 pinning is proven but
replay-reproduces-verdicts is untested; I12 has no
auth story for HTTP/MCP callers (stdio_console:34,84).

## What

- RED-first: correct-guard rejection + pin; a
  replay-reproduces-verdicts test; a named auth
  surface for HTTP/MCP (implement the stdio-safe
  minimum, loud-scope the rest per the deferred
  auth decision).
- All three move PROVEN (or explicitly scoped).

## Acceptance

- I01/I28/I12 pins green with the partials closed.
- Contract + api_spec regen; full suite + gate green.
