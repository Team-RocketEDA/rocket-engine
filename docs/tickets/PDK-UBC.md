# PDK-UBC: SiEPIC EBeam UBC support

*Status: Backlog · Size: S · Roadmap: pdk-onboarding (MVP track)*

## Why

UBC ebeam research PDK as repackaged for gdsfactory
(`ubcpdk`, pip-installable): cells, KLayout DRC workflow,
model regression in CI. The upstream SiEPIC flow documents
rules as docs; we consume the gdsfactory repackaging, which
is better (runnable DRC). Proves the ladder on an
ebeam-lineage PDK.

## What

- RED-first: profile entry; provision recipe (pip pin +
  KLayout tech + probe); live proofs (cell build, KLayout
  DRC run, model-usability check — confirm SAX-compatible
  or record the actual sim path) with UBC goldens.
- Capability matrix rows: layout ✓, drc ✓ (prove it),
  sim per verified path, lvs n/a (photonic, documented).

## Acceptance

- Fresh-store provision → register → verify → proofs green;
  sim path verified, not assumed; matrix truthful.
