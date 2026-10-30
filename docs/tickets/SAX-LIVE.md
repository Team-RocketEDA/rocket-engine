# SAX-LIVE: Prove run_optical live with SAX

*Status: Done · Depends: SAX-ADAPTER, CORPUS-P · Size: M · Roadmap: orch-build-mvp*

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

## Field notes (2026-10-30, proven in .venv with photonic group)

- Solver: sax 0.18.2 (uv.lock pin), cspdk mzi.gds fetched,
  klayout + ngspice on PATH. The "never executed" premise
  above is retired for this env; bare envs keep the
  skip/quarantine-loudly dual config (SAX-ADAPTER acceptance).
- Proof: `scripts/correctness.py --flow photonic` →
  `GATE PASS: 1/1 flows green (8 pass, 0 fail, 0 quarantined)`;
  `scripts/scenarios.py` sax_mzi pass/fail both PASS live;
  tests/adapters/test_sax.py 29 pass; tests/validate/test_photonic.py
  31 pass, 0 skipped; tests/mutate photonic 15 pass.
- Locked in: `SaxAdapter.parse` threads the driver-reported
  `sax_version` into every result (RED: `KeyError: 'sax_version'`
  x2 → GREEN); `test_gate_photonic_circuit_cases_live_or_loud`
  asserts the acceptance clause per env (live PASS where sax
  exists, loud quarantine where absent).
- Local-only: `scripts/check_no_cloud.py` green (no
  gdsfactoryplus/gcloud/tidy3d imports on engine paths).
