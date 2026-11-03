# ENGINE-CORRECTNESS: MVP gate — correct vs incorrect, all flows

*Status: Backlog · Depends: VALIDATE-D, VALIDATE-A, VALIDATE-P, VALIDATE-M · Size: M · Roadmap: orch-build-mvp*

## Why

This is the MVP delivery criterion, verbatim from the user: the
engine must know a correct design from an incorrect one, per flow,
end-to-end, against real open-source designs with documented
results — before any frontend gets hooked up. Everything else in
the sprint is scaffolding for this gate. It exists as one ticket
so the gate has one command, one report, and one unambiguous
PASS/FAIL the demo can point at.

## What

- Aggregate gate over the four VALIDATE-* tickets: single command
  runs all flows (good + mutated), collects verdicts, writes the
  correctness report (e2e report-template adapted: totals, failed
  cases with artifacts, flakes quarantined with refs).

## Acceptance

- 4/4 flows green (good→documented PASS, mutations→expected FAIL).
- Single command; report committed; no silent skips anywhere in
  the gate (skip = fail, with reason and issue ref).
- DEMO-PATH runs this gate as its centerpiece.
