# VALIDATE-A: Analog correctness end-to-end (bandgap)

*Status: Backlog · Depends: SIM-SKY130, FIXTURE-FETCH, MUTATE-HARNESS · Size: M · Roadmap: orch-build-mvp*

## Why

Analog correctness is quantitative, not boolean: a bandgap is
correct iff Vref lands where the designer documented, across the
documented corners. Running the accepted bandgap through the
engine and reproducing its numbers (within stated tolerance) is
the analog half of the MVP criterion — and the first proof our
ngspice path + PDK models + measurement extraction chain holds
together on a real circuit.

## What

- Build accepted bandgap (2amlogic; efabless RDAC fallback) with
  its flow; DC (+corners stretch) through engine e2e; compare Vref
  against documented values.
- Apply MUTATE-HARNESS analog operators (sizing, opens); recheck.

## Acceptance (e2e patterns: artifacts, determinism, quarantine)

- Good design → measurements within documented tolerance.
- Every mutation → expected out-of-spec/FAIL verdict, and only it.
- Failure artifacts kept; 3x repeats identical; flakes quarantined
  with issue refs, never silently skipped.
