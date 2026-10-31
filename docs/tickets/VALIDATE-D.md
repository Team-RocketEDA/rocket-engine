# VALIDATE-D: Digital correctness end-to-end (SERV, picorv32)

*Status: Backlog · Depends: FIXTURE-FETCH, MUTATE-HARNESS · Size: M · Roadmap: orch-build-mvp*

## Why

The MVP delivery criterion is that the engine knows a correct
design from an incorrect one. For digital, "correct" is defined by
the designs' own authors: SERV and picorv32 ship testbenches with
documented pass outcomes. Building them with their scripts and
running them through the engine end-to-end — then proving each
mutation flips its verdict — is what turns "HDL sim works" into
"the engine is CORRECT on real digital designs."

## What

- Build SERV + picorv32 with their own scripts; run testbenches
  through HdlSimAdapter end-to-end; compare with documented
  outcomes (same/similar results).
- Apply MUTATE-HARNESS digital operators; recheck each e2e.

## Acceptance (e2e patterns adapted: artifacts, determinism, quarantine)

- Good designs → PASS matching documented outcomes.
- Every mutation → its expected FAIL, and only it.
- Failure artifacts kept: verdict JSON + native logs + run record.
- 3x repeat runs identical verdicts; flakes quarantined with issue
  refs, never silently skipped.
