# PDK-CSPDK: Cornerstone PDK support (first photonic proof)

*Status: Backlog · Size: S · Roadmap: pdk-onboarding (MVP track)*

## Why

First rung of the PDK ladder: Southampton 220nm SOI MPW,
`pip install cspdk` (pin 2.1.0), 8 process variants, SAX
models per variant, KLayout DRC + tech. We are already
halfway (gdsfactory smoke builds the si340 MZI), so this
slice proves the full ladder — profile, recipe, live proof —
on friendly ground, establishing the pattern the other six
follow.

## What

- RED-first: profile entry (variant → tech/DRC relpaths);
  provision recipe (pip pin + KLayout tech install + verify
  probe); live proofs (si340 MZI build, KLayout DRC run,
  SAX-over-cspdk sim) with golden expectations.
- Capability matrix rows: layout ✓, drc ✓ (klayout),
  optical-sim ✓ (sax), lvs n/a (photonic, documented).

## Acceptance

- Fresh-store provision → register → verify → proofs green;
  matrix truthful; no other PDK's proofs regress.
