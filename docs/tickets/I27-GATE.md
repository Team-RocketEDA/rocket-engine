# I27-GATE: Wire plan_checks/design-completion gate (I27)

*Status: Done · Depends: none · Size: M ·
Roadmap: hardening (E2E-REREVIEW FIND-01, HIGH)*

## Why

I27 is the only UNPROVEN invariant: per-run honesty
holds everywhere, but no cross-stage completion claim
exists. plan_checks is unwired (composition.py:560),
run_thermal is vocab-only, check_results is
stage-blind — so a blocked M14 is invisible and nothing
can say "not fully verified." The mixed lane falsified
this live; three other lanes confirm the clause is
untestable without a claim surface.

## What

- RED-first: wire plan_checks to the stage plan so
  required-but-blocked stages surface; add the
  design-completion query that reports blockers and
  refuses a fully-verified claim while any stand.
- Mixed M14 + run_thermal must appear as named
  blockers, not silent absences.

## Acceptance

- Blocked stage → completion query names it and
  refuses; unblocked → claims with evidence refs.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
