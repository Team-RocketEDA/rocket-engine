# PDK-QPDK: Quantum RF PDK (STRETCH, off MVP track)

*Status: Backlog · Size: M · Roadmap: pdk-onboarding (STRETCH — OFF MVP TRACK)*

## Why

Superconducting qubits (transmon/fluxonium/unimon), CPW
resonators, SQUIDs, TSVs (`qpdk`, pip-installable). A new
domain: genuine verification needs EM simulation (Palace
sidecar), and upstream's GDSFactory+ verify path is
cloud-shaped (off our hot path per I32). Parked as stretch:
layout import/build now, real verification when Palace
lands. Tracked so the domain survives with its caveats
attached.

## What (when scheduled)

- RED-first: profile entry; provision recipe; layout
  import/build proofs only.
- Capability matrix rows: layout ✓; EM verification
  sidecar-gated; cloud verify paths refused per I32.
- Palace-sidecar trigger documented as the unblocker.

## Acceptance

- Layout proofs green; nothing EM/cloud promised or
  faked; matrix truthful.
