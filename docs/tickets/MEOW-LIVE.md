# MEOW-LIVE: EME smoke + tidy3d-locality verdict

*Status: Backlog · Depends: CIRCULAX-LIVE · Size: S · Roadmap: orch-build-mvp*

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
