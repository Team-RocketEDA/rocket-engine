# ADR-016: Atomic session apply-context replaces per-verb console exfiltration

*Status: accepted (2026-11-03) | Ticket: [CONSOLE-APPLY](../tickets/CONSOLE-APPLY.md)*

## Context

Console cells run user and agent scripts in isolated workers (Step 9:
bwrap-only). Edits return to the project today through bespoke
per-verb exfiltration: two parallel proxy mechanisms
(`ConsoleTools` worker-side recorder in
`src/execution/routing/tools.py`, `ConsoleNamespace` host-side
executor in `src/execution/routing/namespace.py`), tier-2 verb
tables (`CELL_VERBS`, `DOC_VERBS`, `ECS_VERBS`, `PROJECT_VERBS`,
`WIRE_VERBS` in `src/execution/routing/calls.py`), per-call
admission in `src/execution/console/route.py`, and prelude
templates (`PRELUDE_TEMPLATE`, `CELL_PRELUDE_TEMPLATE`) that teach
each scenario its own way home.

Every new scenario — new cell kind, new PDK, new geometry macro —
adds another branch to this matrix. There is no atomicity: a
script dying halfway leaves half-landed writes. History spams one
revision per landed call with no grouping identity beyond the
envelope.

## Decision

One explicit, session-owned apply-context replaces the exfil
matrix:

```python
with project.edit("output stage"):
    import gdsfactory as gf
    mzi = gf.components.mzi(delta_length=20)
    project.place(mzi, 100, 200)
# clean exit: everything lands as one batch, one revision. No commit call exists.
# exception: nothing lands. The store never saw any of it.
```

- The context object is owned by the console session, one live
  instance per (console, generation), bound into the prelude for
  every client (MCP, stdio, IDE). `python_reset` retires it.
- Inside the block, ~6 sink primitives (`cell`, `place`,
  `instance`, `rect`, `path`, `wire`) record landable intents.
  gdsfactory does all geometry thinking against its own API;
  the sinks are the only landing surface, so gf version churn
  cannot break the engine side.
- Sinks return handles with provisional ids that chain
  naturally and resolve to real ids in the exit receipt.
- Outside any block, the same calls are scratch: identical
  return shape, no persistence, plus a one-line console hint.
- Exit converts intents into a single `apply_transaction`-shaped
  batch (one envelope identity via `console_envelope`, one
  revision bump). Exception drops the batch and returns the
  error plus the discarded intent list as evidence.
- Nesting bubbles inward-out; only the outermost exit submits.
  Read-only analysis stays context-free; entering a block
  declares write intent and can be refused loudly.
- Approvals bind at exit, where the batch exists (I22:
  approve what actually happens).

## Alternatives considered

1. **Keep per-verb exfiltration.** Rejected: N-scenarios × M-verbs
   growth, no atomicity, history spam. The matrix only gets wider.
2. **Implicit capture (everything created lands).** Rejected: a
   scratch calculation would commit throwaway cells by surprise.
   Landing must be explicit (`with` entry + sink calls).
3. **Manual stage + commit.** Rejected by product decision:
   a third state (staged-but-uncommitted) the user must manage
   is exactly the friction this removes.
4. **End-of-cell batch with no context object.** Rejected: no
   explicit intent declaration means read-only sessions cannot
   refuse writes loudly, and there is no shared global for all
   clients to write through.

## What this replaces (evidence)

- `src/execution/routing/tools.py` (`ConsoleTools` recorder +
  `__getattr__` fallback): recording moves into the context;
  one exit path replaces per-verb record calls.
- `src/execution/routing/namespace.py` (`ConsoleNamespace`
  per-verb proxies): host-side execution collapses to the
  single batch submit.
- Tier-2 verb tables in `src/execution/routing/calls.py`
  (`CELL_VERBS`, `TIER_2_OPERATIONS`, `CONSOLE_TOOL_VERBS`,
  per-kind verb lists): no longer the dispatch surface for
  scripted edits; sinks are fixed at ~6 and version-proof.
- Per-call admission path in `src/execution/console/route.py`:
  admission happens once per batch at exit, not once per call.
- Exfil-shaped prelude content (`PRELUDE_TEMPLATE`,
  `CELL_PRELUDE_TEMPLATE` in `support.py` / `stdio_console.py`):
  preludes bind the context object instead of teaching
  per-verb translations.

Kept unchanged: `admission_envelope`/`console_envelope`
identity (envelope convergence gets stronger, not weaker),
the ledger admission itself, generation/binding/reset rules,
and the bwrap worker substrate. No vocabulary change: this is
an internal route change, not new API surface.

## Consequences

- Positive: one exit path instead of an N×M matrix; atomic
  history (one revision per block); gf-version-proof waist;
  blocks act as natural critical sections under serial
  dispatch (no locks needed).
- Positive: rollback is free — isolated workers mean dropped
  intents never touched the store, so there is nothing to undo.
- Negative: provisional-id handles add one indirection layer;
  mid-block progress is invisible to the IDE until exit (cell
  output remains the progress channel, not the ledger).
- Negative: existing prelude tests and route wiring tests
  (`test_console_route*`, `test_python_exec_modes`,
  `test_stdio_console`) migrate to the context path in the
  same slice — no parallel exfil paths left behind.
- Rollback: decision-only until CONSOLE-APPLY lands; after
  that, the old route modules are removed in-slice (no
  deprecation window for an internal path with no vocabulary
  footprint).
