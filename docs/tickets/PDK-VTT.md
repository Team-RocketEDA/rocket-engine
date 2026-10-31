# PDK-VTT: VTT 3um SOI support (verify upstream first)

*Status: Backlog · Size: M · Roadmap: pdk-onboarding (MVP track)*

## Why

VTT's 3µm SOI platform (`gvtt`, pip-installable) — but v0.1.0
vintage-2023 with a threadbare README. Highest-risk
photonic: likely minimal cells/tech, probably no DRC or SAX
models. This slice leads with upstream verification: prove
what exists before promising anything. Layout-import-only is
an acceptable honest outcome.

## What

- RED-first: upstream coverage probe (cells? tech? DRC?
  models? versions?) recorded as the support ceiling.
- Profile entry + provision recipe for whatever exists;
  live proofs only for verified capabilities.
- Capability matrix rows: layout per proof; everything else
  n/a-with-reason until upstream matures (revisit trigger
  documented, not silently dropped).

## Acceptance

- Matrix truthful to verified coverage; no promised path
  unproven; revisit trigger recorded.
