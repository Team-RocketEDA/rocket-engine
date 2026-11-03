# API-V1-TOOLS-DEFERRED: Bind deferred FPGA/physics tasks (post-MVP)

*Status: Backlog · Depends: API-V1-TOOLS · Size: M ·
Roadmap: post-MVP task binding (explicitly NOT Nov-4 scope)*

## Why

API-V1-TOOLS binds the MVP delivery subset. The
deferred tasks — `implement.fpga` (off_mvp),
`simulate.em`, `simulate.device`, `simulate.thermal`
(post_mvp) — keep full v1 definitions (schemas, io
ports, presentation) and RED conformance evidence,
and bind providers only after Nov 4. Field-solver
smokes in Done history (MEOW-LIVE) do not qualify
as task bindings.

## What

- Bind nextpnr flows, EM/mode/thermal/device
  solvers to their v1 tasks with per-tool
  qualification (fixtures + regressions).
- Flip task `delivery` only with passing
  conformance evidence, never by editing the
  catalog alone.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Each deferred task turns its conformance suite
  green with real-solver evidence; catalog flips
  follow, not lead.
