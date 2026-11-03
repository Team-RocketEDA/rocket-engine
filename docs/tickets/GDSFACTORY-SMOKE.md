# GDSFACTORY-SMOKE: Layout smoke proof

*Status: Done · Depends: MEOW-LIVE · Size: S · Roadmap: orch-build-mvp*

## Why

gdsfactory 9.51 underpins layout, PDK attach, and every photonic
solver's geometry input. Prove the import + component build +
cspdk attach + GDS roundtrip before trusting downstream proofs.

## What

- Layout smoke, RED-first. Wave-8 slice 4 (serial).

## Acceptance

- Smoke executes live with 0 failures.

## Field notes (2026-10-30, proven in .venv with layout group)

- Solver: gdsfactory 9.51.0 (uv.lock pin) over kfactory 3.0.4;
  cspdk si340 2.1.0 from the vendored tree (fetch rev 3323b17b).
  Smallest honest layout proof: generic straight + cornerstone
  MZI build, then GDS write/read roundtrip.
- Proof: `tests/adapters/test_gdsfactory.py` 7 pass live, 0
  failures. Generic `straight` builds (2 ports, polygons > 0);
  attached `cornerstone_si340` PDK (53 cells) builds `mzi`
  (ports o1/o2/o3, 16 polygons); roundtrip preserves cell name,
  polygon total, and bbox exactly (`roundtrip_match is True`).
  Both versions named per run.
- Locked in: `rocket_engine.adapters.gdsfactory.run_layout_smoke`
  (RED: `ModuleNotFoundError` x7 → GREEN); bare envs skip loudly
  (`missing_dependency`, never fake-green); bad parameters and
  unknown cells raise `invalid_command`.
- Local-only: `scripts/check_no_cloud.py` green (no
  gdsfactoryplus/gcloud/tidy3d imports on engine paths).
