# HTTP-LOCALHOST: loopback trust boundary, loud and enforced

*Status: Ready · Depends: none · Size: XS ·
Roadmap: caller-blind API (MVP track)*

## Why

Decision (user, 2026-11-01): HTTP is localhost-only,
unauthenticated, same API as every other transport —
the trust boundary is the loopback interface, not
the caller. That decision must be enforced in code,
not just documented, so nobody deploys the adapter
remotely believing auth exists.

## What

- HTTP adapter binds 127.0.0.1 only; any
  non-loopback bind request refuses loud.
- Startup banner + README state the trust model:
  no auth, localhost only, same caller-blind API.
- Contract + api_spec regen if surfaces change;
  full suite + gate green.

## Acceptance

- Non-loopback bind attempt fails with a message
  naming the localhost-only rule (test pins).
- Docs state the boundary in the adapter README
  and the provision/setup surface.
