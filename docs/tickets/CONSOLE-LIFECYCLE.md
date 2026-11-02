Problem: only python_execute exists (mode/lines/path) vs console contract (console_id/generation/code + workspace lifecycle); no python_open/python_reset. stdio_console is a separate submit/history/reset REPL protocol over OpDispatcher/engine.run, not the shared envelope.
Expected-per: python-console-spec.md:30-32; harness README:142. Audit MC-06, MC-39, D-37, D-23.
Ruling: RULING-04 closes I22 — trusted-local, user-side permissions, no auth; console is a plain python console. Sandbox choice (bwrap vs raw vs prepackaged contexts) comes from BWRAP-STUDY; this ticket implements lifecycle + envelope convergence (or records the scoping decision if separate protocol stays).
Standing requirement (RULING-07): live env provides all scriptable libs + project contexts.
