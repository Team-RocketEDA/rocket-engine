# DRC-SKY130: KLayout sky130A.lydrc live proof

*Status: Backlog · Depends: PDK-STORE, FIXTURE-FETCH · Size: M · Roadmap: orch-build-mvp*

## Why

KLayout batch is the declared sole DRC backend, but no slice has
run a real foundry deck — only synthetic checks. Until
`sky130A.lydrc` executes through the adapter on good/bad cells,
the DRC story is scaffolding. This is the first proof the engine
can run the user's actual PDK.

## What

- Drive `sky130A.lydrc` via KlayoutDrcAdapter on known-good and
  known-bad layout cells; parse violations into the unified shape.
- Scenario coverage for the pass + fail paths.

## Acceptance

- RED-first: good cell PASS, bad cell FAIL with expected rules
  named; unknown deck/tool raises (no silent substitute).
- New scenarios green in CLI 8/8+; suite green both configs.

*Verify 2026-11-03: Wave-2 strict cell check exposed a generator bug
(make_cells.py hardcoded TOP while the check expects the file-stem
cell); fixed generator to per-file name, 8 passed current tree.*
