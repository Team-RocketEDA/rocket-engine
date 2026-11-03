# PDK-IHP: IHP SG13G2 support (BiCMOS + RF flavors)

*Status: Backlog · Size: S · Roadmap: pdk-onboarding (MVP track)*

## Why

130nm SiGe BiCMOS (450 GHz HBTs) with the full open kit:
KLayout DRC + LVS + PyCells, Magic tech + extraction + DRC +
LVS, ngspice/Xyce models, xschem symbols + testbenches,
stdcells + IO + SRAM, LEF/Liberty. Sky130-shaped with RF
flavors. Caveat: upstream labels it preview, not production —
our proofs pin exact revisions and treat drift as failure.

## What

- RED-first: profile entry; provision recipe (per install
  guide + probe); live proofs (DRC, LVS, extraction,
  ngspice sim incl. one HBT/passive case) with SG13G2 goldens.
- Capability matrix rows: full CMOS mapping; RF/peak-fmax
  items marked preview-gated, never promised.

## Acceptance

- Fresh-store provision → register → verify → proofs green
  at pinned revisions; matrix truthful.
