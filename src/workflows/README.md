# workflows — process inventories and completion gates

`workflows/` holds the digital, analog, photonic, and mixed-domain verification stages as data. It plans checks and reports whether the requested flow has enough available operations and passing evidence. It never launches a solver.

## Current behavior

- `stages.py` contains the D/A/P/M inventories and their stage-to-operation mappings.
- `capability_plan.py` marks stages ready or blocked based on available operations.
- `completion.py` combines the plan with the latest check records. Missing operations, checks that have not run, and non-PASS verdicts remain blockers; only a blocker-free flow can report fully verified.
- The stage `when` expressions are descriptive today. The planner currently treats planned stages as required instead of evaluating those expressions to narrow applicability.

The same plan and completion reports are served by `plan_checks` and `get_design_completion`, so clients can show the engine's reasons and blockers directly.

## Boundaries and routing

This module owns stage order, applicability metadata, and completion rules. `composition.Engine` supplies registered operations and check results. Solver inputs and evidence belong to [`adapters/`](../adapters/README.md) and [`execution/`](../execution/README.md); command and result shapes belong to [`interfaces/`](../interfaces/README.md).

For the product process source, see the [PRD verification process](../../../PRD/tools-research/verification-process.md) and [workflow catalog](../../../PRD/tools-research/verification-workflows.yaml). For current engine gaps, see the [sprint board](../../docs/sprint-board.md).
