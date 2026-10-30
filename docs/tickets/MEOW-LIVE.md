# MEOW-LIVE: EME smoke + tidy3d-locality verdict

*Status: Done · Depends: CIRCULAX-LIVE · Size: S · Roadmap: orch-build-mvp*

## Why

MEOW (0.15.0) is JAX-local at its core but hard-depends on the
tidy3d cloud client for mode solving. This slice proves the
local EME smoke AND records exactly which calls stay on-device
vs need an account — the verdict the local-only rule demands.

## What

- Local EME smoke, RED-first; tidy3d-locality probe with a
  written verdict (ticket/docs).
- Wave-8 slice 3 (serial).

## Acceptance

- Smoke green live; locality verdict recorded; no cloud call
  on any default path.

## Field notes (2026-10-30, proven in .venv with photonic group)

- Solver: meow 0.15.0 over tidy3d 2.10.0 (uv.lock pins).
  Smallest honest EME circuit: 500x220nm Si strip on SiO2 at
  1550nm, 2 modes via meow's tidy3d FDE backend, cascaded over
  a 10um cell with meow's SAX EME backend.
- Proof: `tests/adapters/test_meow.py` 7 pass live, 0 failures.
  Matched guide: TE0 neff=2.3108, T=1.0/R=0.0. Abrupt
  0.5->1.0um width step: T=0.877 (< 0.95), R>0 — the
  good-vs-bad signal. Cascade phase matches the analytic
  2*pi*neff*L/wl to 1e-9 (plumbing oracle); both solver
  versions named per run.
- Locked in: `rocket_engine.adapters.meow.run_eme_smoke` (RED:
  `ModuleNotFoundError` x7 → GREEN); bare envs skip loudly
  (`missing_dependency`, never fake-green); bad parameters
  raise `invalid_command` before any solver import.
- Local-only: `scripts/check_no_cloud.py` green (no
  gdsfactoryplus/gcloud/tidy3d imports on engine paths).

## Locality verdict: what stays on-device vs needs an account

Correction to the Why above: meow hard-depends on the tidy3d
*package*, but mode solving does NOT touch its cloud client.

On-device (smoke path, proven):
- `meow.fde.tidy3d.compute_modes_tidy3d` calls
  `tidy3d.components.mode.solver.compute_modes`
  (`EigSolver.compute_modes`) directly — a local CPU
  eigensolver. `tidy3d/components/mode/solver.py` (2.10.0)
  contains zero references to web/http/api/auth.
- The EME cascade (`meow.eme`, SAX `klu` backend) is pure
  local numpy/sax; the tidy3d material library is bundled
  data, not a service.
- Runtime proof: the smoke passes with `socket.socket.connect`
  amputated (`test_meow_smoke_runs_with_network_blocked`),
  and this env holds no credentials (`TIDY3D_API_KEY` unset,
  no `~/.tidy3d/config`) — so the smoke needs no account.

Needs cloud/account (never on the smoke path):
- `tidy3d.web.*` only: FDTD job submission (`web.run`), task
  polling, and `web.test`, whose auth gate
  (`tidy3d/web/api/webapi.py`) demands an API key from a
  tidy3d.simulation.cloud account page. Engine code never
  imports the client — `tidy3d_version()` reads installed
  metadata via `importlib.metadata` instead.
- Follow-up (out of scope): full `deck.tool: meow` Engine
  adapter on `run_optical`; this slice is the install +
  signal + verdict proof only.
