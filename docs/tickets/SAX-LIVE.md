# SAX-LIVE: Prove run_optical live with SAX

*Status: Doing · Depends: SAX-ADAPTER, CORPUS-P · Size: M · Roadmap: orch-build-mvp*

## Why

The SAX adapter exists but its circuit paths never executed the
real solver (0.18.2 now installed). A photonic flow that never ran
is a promise, not a proof.

## What

- Live `run_optical` proof vs cspdk MZI good/bad fixtures,
  RED-first; un-quarantine what the proof earns (tests +
  scenarios + gate photonic-circuit paths).
- Wave-8 slice 1 (serial).

## Acceptance

- Photonic circuit gate cases execute live (not skipped,
  not quarantined) with 0 failures.
