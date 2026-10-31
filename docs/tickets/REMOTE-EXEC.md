# REMOTE-EXEC: HTTP/remote execution adapter (OFF MVP TRACK)

*Status: Backlog · Depends: WORKERS · Size: L · Roadmap: orch-build-mvp*

## Why

Browser and hosted deployments eventually need what local stdio
cannot give: authenticated remote execution with sessions, file
sync, and per-user worker pools (the Replit shape: edge auth →
session → broker → containers). This ticket exists to park that
ambition *explicitly*: it stays off every MVP plan until the user
declares a happy engine and a happy IDE. Parking it in writing
protects the MVP from the auth/multitenancy worm-can.

## What (when scheduled, post-happy)

- Edge auth + session routing to per-user worker pools; engine
  ops unchanged (caller/project identity fields already reserved).
- Transport adapter (WS/HTTP) carrying bytes/files only — trust
  stays at the container boundary + approval edge, never in transit.

## Acceptance

- Unauthenticated remote execution impossible (tested); sessions
  isolated (no cross-user reads); resource quotas enforced.
- Local stdio path untouched by remote code (no shared auth bypass).
