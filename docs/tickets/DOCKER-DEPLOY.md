# DOCKER-DEPLOY: One-container judging/deployment recipe

*Status: Backlog (pre-judging priority) · Depends: DEMO-PATH, B10 · Size: M · Roadmap: orch-build-mvp*

## Why

No judge should ever have to say "now I have to install Linux?"
And no Windows user should need Linux either. ONE container that
deploys engine + rocket-fuel + web app together, frontend served
straight to the browser, turns every deployment — judging,
Windows, curious newcomers — into pull, run, open the browser.
The environment is controlled by us and totally compatible; the
user never provisions a toolchain by hand. Backlog relative to
the engine-core sprint, but lands before judging — a perfect
engine nobody can run scores zero.

## What

- Single multi-stage `Dockerfile` (deps → build → run image):
  locked engine install + toolchain + rocket-fuel + web app in
  one deployable. Base image pinned by digest (never `:latest`);
  non-root user; `.dockerignore` keeps fixtures/stores/secrets
  out of the layers.
- Model: take a page from
  https://github.com/iic-jku/iic-osic-tools (full open-source
  EDA toolchain in containers) — fork vs from-scratch is an
  open decision for ticket kickoff, recorded with reasons.
- One-time setup menu inside the app (Vivado-style): checkbox
  dependency/PDK install into the container's engine store on
  first run; everything else pre-provisioned and compatible.
- PDK story decided and documented: the 12G sky130A rides a
  named volume or a first-run fetch into the engine store —
  never baked into image layers.
- Dual-use access: the plain-HTTP adapter stays NO-AUTH for
  local/judging convenience and binds `127.0.0.1` only (host
  loopback, per the expose-only-what's-needed rule), while
  HTTPS (+ auth) remains the separate later production path.
- One-command flow in the demo runbook (`docker run ... →
  open localhost:PORT → correctness gate green`).

## Acceptance

- Fresh-machine `docker run` → web app in the browser,
  engine healthy, fuel connected, ENGINE-CORRECTNESS gate
  green inside the container.
- No-auth HTTP reachable via loopback only, with a printed
  trust-boundary warning; NEVER exposed to untrusted networks
  (auth'd HTTPS is the later path for that — see the HTTP auth
  note in the repo). No bare tracebacks to the judging audience.
- Rebuild reproducible from lockfile + pinned digest; image size
  and PDK strategy recorded in the runbook.

## Verdict (Wave-2, 2026-11-03) — Ready, BLOCKED-needs-host (daemon)

Recipe complete: multi-stage Dockerfile (pinned-qual base + digest
transcription procedure, non-root, PDK/store volumes, provisioner
layer, demo-gate CMD), .dockerignore, one-command runbook section;
13/13 recipe-review checks green. Carry: fresh-machine docker
build+run acceptance needs a networked host with daemon.
