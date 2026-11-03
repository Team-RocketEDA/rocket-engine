# ADR-004: Engine-side depends_on and gate-on-verdict guardrails

*Status: accepted (2026-11-01) | Tickets: [OP-GATES](../tickets/OP-GATES.md), [BATCH-PARALLEL](../tickets/BATCH-PARALLEL.md)*

## Context

Fuel owns the plan (iteration budget, repairs, constraints), so
orchestration ordering could live entirely in the client. But a
plan is advisory: a confused or buggy agent can still submit
illegal or nonsensical sequences (simulate before netlist
exists, LVS against a stale extraction, tape out an
un-verdict-ed flow). The engine is the last mechanical line:
it must refuse nonsense structurally, not trust the planner.

## Decision

The engine enforces `depends_on` (hard ordering edges) and
gate-on-verdict (a step runs only if its gates verdict-ed
PASS/expected) mechanically at submit time. A force flag
bypasses verdict gates only; hard `depends_on` failures
reject unconditionally and are never forceable. `depends_on`
is declared by engine maintainers per op/deck, never taken
from caller arguments.

## Alternatives considered

1. **Fuel-only ordering.** Rejected: plans are advisory;
   nothing mechanical stops an illegal sequence, and every
   future client re-implements the guardrails.
2. **Caller-supplied depends_on.** Rejected: lets the party
   being guarded write its own guardrails (same flaw as
   caller-supplied spice targets, already refused).
3. **No gating (sequential batch only).** Rejected: serial
   order is not safety; parallel dispatch (BATCH-PARALLEL)
   needs the gates more, not less.

## Consequences

- Positive: illegal sequences are structurally
  impossible over every transport; agents fail fast with
  structured codes instead of corrupt runs.
- Positive: gates compose with parallel dispatch —
  ready items run, gated items wait, failed gates refuse
  loudly.
- Negative: engine owns a dependency model per op/deck
  that must be maintained as decks are added.
- Risk: over-gating blocks legitimate flows. Mitigation:
  gates ship per-deck with tests pinning both the refuse
  and the allow paths; force flag covers verdict gates.
