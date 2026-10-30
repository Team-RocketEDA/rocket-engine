# PDK-SKY130GF: SkyWater pip distribution (decision + profile)

*Status: Backlog · Size: S · Roadmap: pdk-onboarding (MVP track)*

## Why

`pip install sky130` repackages (almost) the same process we
already support via the open_pdks tree — cells + DRC CI in
gdsfactory form. This slice is a decision plus a profile, not
a second sky130: keep the open_pdks tree as the CMOS sky130
(full decks, already proven) and scope the pip package as
layout-cells convenience — or justify dual support. One
process must never register two confusing ways.

## What

- RED-first: record the distribution decision (single vs
  dual registration with rationale); profile entry naming
  the distribution explicitly; live proofs for whatever the
  pip package claims (cell build at minimum).
- Runs pin the distribution in the I28 ingredient closure —
  reproducibility must survive the two-distributions fact.

## Acceptance

- Decision recorded; proofs green; no run can silently mix
  distributions; matrix names the distribution per row.
