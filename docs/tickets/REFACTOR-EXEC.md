# REFACTOR-EXEC: Split execution mega modules (python_exec, console_route)

*Status: Ready · Design: AGENTS.md Module-size rule · Created: 2026-11-01*

Depends: none. Zero behavior change; no provider logic changes.

`src/execution/python_exec.py` (1,827 lines) and `src/execution/console_route.py` (1,512 lines) are the next mega files after service/composition. Split each by cohesive responsibility into nested subpackages (worker lifecycle, approvals, routing, output handling), one word per path segment, nested — never same-first-name siblings. Feature-local helpers stay with their feature; only genuinely shared pure helpers move to small `src/common/` modules. Google-style docstrings throughout. All existing tests stay green; console/approval semantics byte-identical.

Acceptance: both modules decomposed with no file over 1,000 lines added back; console + approval + execution suites green.
