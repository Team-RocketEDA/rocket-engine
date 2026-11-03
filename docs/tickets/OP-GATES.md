# OP-GATES: engine-side depends_on + gate-on-verdict guardrails

*Status: Ready · Depends: none · Size: M ·
Roadmap: mechanical safety (MVP track)*

## Why

Fuel owns the plan, but a plan is advisory: a
confused agent can still submit illegal sequences
(sim before netlist, LVS on stale extraction).
The engine is the last mechanical line (ADR-004):
it must refuse nonsense structurally over every
transport, not trust the planner.

## What

- `depends_on` hard edges per op/deck, declared by
  engine maintainers (never caller arguments):
  unmet deps refuse unconditionally, never
  forceable.
- Gate-on-verdict: a step runs only if its gates
  verdict-ed PASS/expected; a force flag bypasses
  verdict gates only, never hard deps.
- Gates compose with BATCH-PARALLEL: ready items
  run, gated items wait, failed gates refuse with
  structured codes naming the unmet gate.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- Nonsensical sequences refuse loud with the gate
  named (tests pin refuse paths per deck).
- Force flag opens verdict gates, never hard deps
  (test pins both).
- Parallel batch with a failed gate: gated items
  refused, independent items complete.
