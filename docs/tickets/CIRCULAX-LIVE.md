# CIRCULAX-LIVE: Time-domain smoke proof

*Status: Done · Depends: SAX-LIVE · Size: S · Roadmap: orch-build-mvp*

## Why

Circulax (0.2.5) covers what SAX cannot: transient, DC, AC,
harmonic-balance. One honest smoke proves the install and the
good-vs-bad signal before any bigger photonic-electronic claim.

## What

- Smallest honest circulax circuit, good-vs-bad, RED-first.
- Wave-8 slice 2 (serial).

## Acceptance

- Smoke executes live with 0 failures; result recorded.

## Field notes (2026-10-30, proven in .venv with photonic group)

- Solver: circulax 0.2.5 (uv.lock pin) via kfnetlist + jax/diffrax.
  Smallest honest circuit: V step + R + C + GND, `Circuit.transient`
  from discharged start (y0=zeros), 0..5us in 11 saves.
- Proof: `tests/adapters/test_circulax.py` 5 pass live, 0 failures.
  Good RC (1k/1nF, tau=1us): Vc(1us)=0.6321, Vc(5us)=0.9933 —
  passes the 0.9 V @5us threshold. Slow RC (100k/1nF):
  Vc(5us)=0.0488 — misses it. Helper matches the raw solver to
  1e-9 (oracle test); `circulax_version` names 0.2.5 per run.
- Locked in: `rocket_engine.adapters.circulax.run_rc_step` (RED:
  `ModuleNotFoundError` x5 → GREEN); bare envs skip loudly
  (`missing_dependency`, never fake-green).
- Local-only: `scripts/check_no_cloud.py` green (no
  gdsfactoryplus/gcloud/tidy3d imports on engine paths).
- Follow-up (out of scope): full `deck.tool: circulax` Engine
  adapter on `run_optical`; this slice is the install + signal
  proof only.
