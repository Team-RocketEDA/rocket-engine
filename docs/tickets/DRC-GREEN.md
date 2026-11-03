# DRC-GREEN: Magic/KLayout DRC adapter GREEN

*Status: Done · Size: M · Roadmap: orch-build-mvp*

## Why

Stale-in-Doing record: this line sat in Doing since board
creation (40ef160) while the work landed under DRC-RED,
DRC-SKY130, and RUNNER-ROLLOUT. Closed on evidence, not memory.

## What

- Magic DRC + KLayout batch DRC behind `deck.tool` selection;
  good/bad layout fixtures; sky130A.lydrc live proof.

## Acceptance (proven 2026-10-30, tools PATH + live store)

- DRC files (`test_drc`, `test_drc_kl`, `test_drc_sky130`)
  live-green inside a 96 passed / 1 skipped combined run —
  the single skip is the inverted missing-binary test.
- Scenarios green (26/0); gate analog/digital/mixed/photonic
  4/4 with DRC evidence live.
