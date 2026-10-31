# E2E-REREVIEW: Invariant-by-invariant codebase re-review + e2e journeys

*Status: Ready · Depends: convergence workflow delivered ·
Size: L · Roadmap: hardening (multiagent review lane)*

## Why

The engine grew fast across parallel lanes; the "to GDS"
audit proved vocabulary can promise what adapters don't
serve. This is the scheduled skeptic pass: every PRD
invariant (I01–I29 plus the I30–I33 texts) re-verified
against the real code, and every D/A/P/M journey
re-proven end to end through the scenario harness and
correctness gate — with artifacts, not assertions.

## What

- Multiagent review (launches after the convergence
  workflow delivers — one workflow owner at a time):
  one journey lane per D/A/P/M domain driving
  scenarios.py + correctness.py + mutate.py on real
  fixtures, plus one invariant-compliance lane mapping
  I01–I33 to code + tests with RED-proof spot checks.
- e2e-testing discipline, engine-adapted: full-journey
  runs (no mocked solvers), failure artifacts (logs,
  verdicts, native outputs) captured per journey, flaky
  runs quarantined with repeat counts (never deleted),
  structured verdict tables per lane.
- Findings land as new tickets or lane refusals with
  reasons — the review never edits product code itself.
  I27 (missing stages block completion claims) and I09
  (exit-zero-is-not-PASS) are explicit falsification
  targets, not background assumptions.

## Acceptance

- 4/4 journey verdict tables + invariant map delivered;
  every finding ticketed or refused-with-reason; suite +
  gate re-stamped green at review HEAD.
