# VALIDATE-M: Mixed-signal correctness end-to-end (sigma-delta)

*Status: Backlog · Depends: SIM-SKY130, FIXTURE-FETCH, MUTATE-HARNESS · Size: M · Roadmap: orch-build-mvp*

## Why

Mixed-signal is where engines embarrass themselves: analog macro +
digital wrapper, two sim domains, one verdict. The pthomas
sigma-delta ships a design doc with measured numbers — the perfect
forcing function. The end goal is closed-loop co-simulation like
every other domain (no domain is permanently partial — see F9);
for the demo, macro + wrapper verify through the engine against
documented results with the seam status reported honestly, and
seam closure tracked as follow-up work, never cut scope.

## What

- Build sigma-delta with its flow; macro + wrapper through engine
  e2e; compare against documented measurements.
- Apply MUTATE-HARNESS operators across both halves; recheck.

## Acceptance (e2e patterns: artifacts, determinism, quarantine)

- Good design → results match documented within tolerance.
- Every mutation → expected FAIL, and only it.
- Co-sim seam status reported honestly with closure tracked as
  follow-up; failure artifacts kept; 3x repeats identical; flakes
  quarantined, never silently skipped.
