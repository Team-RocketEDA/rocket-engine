# ADR-006: HTTP is localhost-only and unauthenticated

*Status: accepted (2026-11-01) | Tickets: [HTTP-LOCALHOST](../tickets/HTTP-LOCALHOST.md)*

## Context

ADR-005 makes the engine caller-blind with approvals at
the client edge. That only holds if every transport is
genuinely local: an HTTP adapter that can bind remotely
with no auth would silently void the trust model the
moment someone deploys it.

## Decision

The HTTP adapter binds 127.0.0.1 only, refuses any
non-loopback bind loudly, and serves the same
caller-blind API as every other transport with no
auth. The trust boundary is the loopback interface.
Remote/multi-user access is a future, separate,
authenticated adapter — never this one with a flag.

## Alternatives considered

1. **HTTP with auth now.** Rejected: no remote
   deployment exists; auth is deferred scope (REMOTE-EXEC
   backlog) and would gate local usefulness.
2. **Document-only (no bind enforcement).** Rejected:
   documentation does not stop a bad deploy; the
   refusal must be mechanical.
3. **No HTTP adapter.** Rejected: the IDE and local
   tooling need an HTTP face; localhost-only is the
   safe shape for it.

## Consequences

- Positive: local HTTP use is frictionless and safe
  by construction.
- Positive: the trust model has exactly one sentence,
  enforceable in one test.
- Negative: any remote story starts from zero (new
  adapter + auth), by design.
