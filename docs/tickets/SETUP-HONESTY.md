# SETUP-HONESTY: No false-ready probes, fresh tests, capable readiness

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-10 + FIND-14 + FIND-21)*

## Why

Three faces of one lie — readiness that isn't:
find_spec false-readies on import shadows
(setup.py:195,431,445), feeding the I27 planner;
test_setup.py is stale (_no_sax must also mask
circulax — 2 pre-existing failures, engine honest);
M11 reports ready without sta (capability-unaware
readiness, setup.py:73).

## What

- RED-first: shadow-proof spec detection; stale
  tests refreshed (mask circulax alongside sax);
  readiness computed from capabilities (missing sta
  → not-ready with remedy).
- No false-ready in any of the three probes.

## Acceptance

- Import-shadow, stale-mask, and no-sta cases all
  report honestly; regressions pinned.
- Contract + api_spec regen; full suite + gate green.
