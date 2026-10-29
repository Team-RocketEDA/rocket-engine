# EXTRACT-SKY130: Magic extraction + Netgen LVS proof

*Status: Backlog · Depends: PDK-STORE · Size: M · Roadmap: orch-build-mvp*

## Why

Extraction is Magic's last defensible seat (sky130A `.ext` feeding
Netgen LVS). This slice proves that loop end-to-end on a known-good
cell — and, critically, delivers the local verdict on the upstream
`sky130.lvs` case bug: if KLayout LVS passes locally, the engine
gains a second LVS path; if not, the Magic dependency is
evidence-locked until the trigger fires. Either way we stop guessing.

## What

- Magic `sky130A.tech` extraction proof → Netgen LVS compare on a
  known-good cell (PASS) and a mismatched netlist (FAIL).
- Attempt the KLayout `sky130.lvs` path on the same cell; document
  the verdict (use it or evidence-lock Magic, no middle ground).

## Acceptance

- RED-first; good→PASS, mismatch→FAIL with named diffs.
- `sky130.lvs` bug verdict written down with reproduction steps.
- Scenario coverage; suite green both configs.
