Problem: only python_execute exists (mode/lines/path) vs console contract (console_id/generation/code + workspace lifecycle); no python_open/python_reset. stdio_console is a separate submit/history/reset REPL protocol over OpDispatcher/engine.run, not the shared envelope.
Expected-per: python-console-spec.md:30-32; harness README:142. Audit MC-06, MC-39, D-37, D-23.
Ruling: RULING-04 closes I22 — trusted-local, user-side permissions, no auth; console is a plain python console. Sandbox choice (bwrap vs raw vs prepackaged contexts) comes from BWRAP-STUDY; this ticket implements lifecycle + envelope convergence (or records the scoping decision if separate protocol stays).

## Delivery verdict (2026-11-02)

DELIVERED, lifecycle only, no sandbox changes (TDD RED→GREEN,
7 new tests in `tests/test_console_lifecycle_open_reset.py`;
`tests/execution/test_console.py` stays green).

- `src/execution/console/lifecycle.py` (new): `ConsoleLifecycle`
  registry — `open_console` (one live handle per workspace root,
  else fresh `console_id`), `status`, `reset_console` (retires
  the generation, kills outstanding approvals through
  `ConsoleSession.reset`), `close_console` (releases the
  workspace binding), unknown ids fail with `unknown_console`.
- Envelope convergence: `console_envelope`/
  `parse_console_envelope` render the `python_open`/
  `python_execute`/`python_reset` operations through the shared
  admission-envelope dumper, so console commands admit with the
  same identity the Engine uses.
- Scoping decision recorded (per ticket): `stdio_console` keeps
  its local-panel REPL protocol; these envelopes are the
  Engine-side path the adapt lane wires `python_open`/
  `python_reset` through. Nothing here spawns a worker or
  touches the runner — the BWRAP-STUDY ruling (confined workers
  only, refusal is a lifecycle event) is unchanged.

Seam for adapt lane: wire the three operations in
`vocabulary.py` + `ops/submit.py` + `composition.py` through
these envelopes (operation names + `session_for` for the worker
lane). BLOCKED-needs-host: none — lifecycle is pure Python;
worker/bwrap behavior is untouched and untested here.
Standing requirement (RULING-07): live env provides all scriptable libs + project contexts.
