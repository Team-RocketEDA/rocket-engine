# DOCKER-DEPLOY: One-container judging/deployment recipe

*Status: Backlog (pre-judging priority) · Depends: DEMO-PATH, B10 · Size: M · Roadmap: orch-build-mvp*

## Why

No judge should ever have to say "now I have to install Linux?"
Judging must be one command: pull, run, open the browser. A
container recipe that bundles the engine + toolchain + provisioned
environment turns the demo from a setup ordeal into a performance.
This is backlog relative to the engine-core sprint, but it must
land before judging — a perfect engine nobody can run scores zero.

## What

- Multi-stage `Dockerfile` (deps → build → judging image): locked
  engine install + oss-cad-suite toolchain. Base image pinned by
  digest (never `:latest`); non-root user; `.dockerignore` keeps
  fixtures/stores/secrets out of the layers.
- Compose file with `engine` + `frontend` services on one network
  (service-name discovery); healthcheck on the engine; frontend
  port published to the host for the judge's browser.
- PDK story decided and documented: the 12G sky130A rides a named
  volume or a first-run fetch into the engine store — never baked
  into image layers.
- Dual-use access: the plain-HTTP adapter stays NO-AUTH for
  local/judging convenience and binds `127.0.0.1` only (host
  loopback, per the expose-only-what's-needed rule), while HTTPS
  (+ auth) remains the separate later production path. The engine
  talks to the frontend over the compose network.
- One-command judging flow in the demo runbook (`docker compose
  up → open localhost:PORT → correctness gate green`).

## Acceptance

- Fresh-machine `docker compose up` → frontend up, engine
  healthy, ENGINE-CORRECTNESS gate green inside the container.
- No-auth HTTP reachable via loopback only, with a printed
  trust-boundary warning; NEVER exposed to untrusted networks
  (auth'd HTTPS is the later path for that — see the HTTP auth
  note in the repo). No bare tracebacks to the judging audience.
- Rebuild reproducible from lockfile + pinned digest; image size
  and PDK strategy recorded in the runbook.
