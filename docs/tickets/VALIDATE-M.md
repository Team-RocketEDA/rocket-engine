# VALIDATE-M: Mixed-signal correctness end-to-end (sigma-delta)

*Status: Backlog · Depends: SIM-SKY130, FIXTURE-FETCH, MUTATE-HARNESS · Size: M · Roadmap: orch-build-mvp*

## Why

Mixed-signal is where engines embarrass themselves: analog macro +
digital wrapper, two sim domains, one verdict. The pthomas
sigma-delta ships a design doc with measured numbers — the perfect
forcing function. MVP scope is honest about the seam: analog-macro
sim + digital-wrapper sim run through the engine and compared
against documented results separately, with the co-simulation seam
documented as the known next step rather than faked.

## What

- Build sigma-delta with its flow; macro + wrapper through engine
  e2e; compare against documented measurements.
- Apply MUTATE-HARNESS operators across both halves; recheck.

## Acceptance (e2e patterns: artifacts, determinism, quarantine)

- Good design → results match documented within tolerance.
- Every mutation → expected FAIL, and only it.
- Co-sim seam documented (not faked); failure artifacts kept; 3x
  repeats identical; flakes quarantined, never silently skipped.
