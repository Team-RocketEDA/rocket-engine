# MUTATE-HARNESS: Systematic incorrect-design generator

*Status: Backlog · Depends: FIXTURE-FETCH · Size: M · Roadmap: orch-build-mvp*

## Why

"Incorrect designs" must be systematic, not ad hoc. Hand-breaking
one file per validation proves nothing about coverage and rots on
contact. A harness of documented mutation operators — each with a
declared expected verdict — turns incorrectness into a repeatable
test dimension: apply operator, recheck engine e2e, assert the flip.
This is what makes "knows incorrect from correct" falsifiable.

## What

- Mutation operators per domain: digital (reset break, truncation,
  unconnected port), analog (device sizing out-of-spec, open net),
  layout/netlist (DRC violation, LVS mismatch), photonic (geometry
  + circuit mistune).
- Each operator: script + doc + expected verdict; reproducible
  from seed; runner rechecks engine e2e per mutation.

## Acceptance

- Every operator flips its target verdict and only it (RED-first
  per operator: unmutated PASS, mutated expected-FAIL).
- Operator→verdict map documented; mutations reproducible from seed.
