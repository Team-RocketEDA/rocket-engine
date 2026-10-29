# FIXTURE-FETCH: Vendor accepted D/A/M fixtures reproducibly

*Status: Backlog · Depends: none · Size: M · Roadmap: orch-build-mvp*

## Why

The user accepted SERV, picorv32, the 2amlogic bandgap, and the
pthomas sigma-delta into the suite. "Accepted" must mean pinned:
unpinned fetches rot (upstream moves, fixtures silently change,
verdicts drift). A fetch script with commit pins + a license gate
turns accepted designs into reproducible suite inputs — and keeps
unlicensed code (two analog repos were already excluded) out forever.

## What

- Fetch script: clone at pinned commits into schema layout,
  idempotent re-runs, per-design README noting documented results
  (what "correct" means for each).
- License gate: Apache/MIT/BSD/ISC only; test asserts no vendored
  file lacks an accepted license.
- Accepted set: SERV + picorv32 (D), 2amlogic bandgap (A, efabless
  RDAC fallback), pthomas sigma-delta (M). PIC lands via VALIDATE-P.

## Acceptance

- Fresh fetch produces pinned trees; rerun is a no-op (hash check).
- License-gate test green; documented-results notes exist per design.
- Selection criterion (locked): every fixture ships prior
  verification — testbenches, datasheets/measured numbers, or
  regression suites. Designs with nothing measurable to compare
  against are excluded, no matter how tempting.
