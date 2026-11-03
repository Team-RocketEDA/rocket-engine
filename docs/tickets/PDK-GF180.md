# PDK-GF180: GF180MCU support (second CMOS node)

*Status: Backlog · Size: S · Roadmap: pdk-onboarding (MVP track)*

## Why

The "second CMOS node" that proves the PDK mechanism is not
sky130-shaped. Google + GlobalFoundries 180nm MCU (alpha but
huge community: chipathons, tutorials, tapeouts): stdcell 7T/9T
libs, ngspice models, Magic DRC/PEX, KLayout tech + DRC + LVS,
xschem. Sky130-shaped, best-documented onboarding after sky130.

## What

- RED-first: profile entry (model lib, decks, tech, symbols);
  provision recipe (clone + build per upstream docs + probe);
  live proofs mirroring the SKY130 slices (DRC clean/dirty,
  extraction + LVS, ngspice sim) with GF180 goldens.
- Capability matrix rows: full CMOS mapping.

## Acceptance

- Fresh-store provision → register → verify → proofs green;
  matrix truthful; sky130 proofs unregressed.
