# PYTHON-EXEC: Python execution API (inline lines + project script files)

*Status: Ready · Size: M · Roadmap: convergence (MVP track)*

## Why

The engine owns a prepared Python worker (pinned packages,
PDK access, tool binaries on PATH) that the stdio console
already drives — but no headless caller can reach it. An AI
agent designing a chip needs scripted execution as a
first-class tool: generate a gdsfactory cell, fit a curve to
sim output, stitch a netlist — without a human pasting into
a REPL. Two modes, no more: execute inline script lines
directly, or execute a script file living in the project
folder. Anything narrower forces the agent through
read-eval round-trips it shouldn't need; anything wider
(arb paths, shells) reopens the approval can of worms. This
closes the last origination gap: with catalogue/place for
cells and python_execute for scripts, the agent can both
place AND program.

## What

- RED-first: `python_execute` engine API with exactly two
  input modes — `lines` (inline script text) and `path`
  (project-contained script file; traversal/out-of-project
  rejected loudly). Runs in the prepared worker substrate
  shared with the console; bounded stdout/stderr + exception
  locations; effects (docs written, runs triggered) returned
  as structured data with run_ids, never side-channeled.
- Approval policy per python-console-spec: agent calls
  resolve through the approval route (pending/denied/expired
  distinct from job state); human UI approval path only,
  never MCP self-approval.
- MCP tool with a real input schema (mode one-of, bounded
  sizes), wired through the same dispatch + errors-as-values
  shape as the run tools. Zero exit is never check PASS.
- Timeouts scale honest: bounded default, explicit override,
  cancellation through the job surface.

## Acceptance

- Inline-lines and file modes both green on a gdsfactory
  cell-build + a sim-output curve fit; effects land in the
  ledger with actor + revision; traversal rejected;
  approval-denied stays distinct from run failure.
- Contract + api_spec regen; full suite + gate green.

## Field notes (2026-11-01): console routes to the recipe

- A script that edits the project is an INGREDIENT, not
  exhaust (I28): console tier-2 mutations (cell add, wire,
  doc writes) route through ProjectService admission —
  expected_revision gating, ledger events, idempotency —
  the same verbs as CRUD/MCP. The console is a client,
  never a side-channel writer. See CONSOLE-ROUTE.
