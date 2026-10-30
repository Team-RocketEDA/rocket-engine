# GDSFACTORY-SMOKE: Layout smoke proof

*Status: Backlog · Depends: MEOW-LIVE · Size: S · Roadmap: orch-build-mvp*

## Why

gdsfactory 9.51 underpins layout, PDK attach, and every photonic
solver's geometry input. Prove the import + component build +
cspdk attach + GDS roundtrip before trusting downstream proofs.

## What

- Layout smoke, RED-first. Wave-8 slice 4 (serial).

## Acceptance

- Smoke executes live with 0 failures.
