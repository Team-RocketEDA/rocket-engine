# REFACTOR-COMPOSITION: Split src/composition.py before it hits the limit

*Status: Ready · Design: AGENTS.md Module-size rule · Created: 2026-11-01*

Depends: none. Zero behavior change; no provider logic changes.

`src/composition.py` is 2,585 lines and approaching the 3,000-line architecture constraint. Preemptively split by cohesive responsibility into nested subpackages (short names, normally no more than two words per path segment): engine assembly/wiring, op dispatch tables, transport binding. Feature-local helpers stay with their feature; only genuinely shared pure helpers move to small `src/common/` modules. Google-style docstrings throughout. All existing tests stay green; no fixture/contract changes.

Acceptance: composition.py comfortably under the limit with cohesive homes for each part; full suite + gate green.
