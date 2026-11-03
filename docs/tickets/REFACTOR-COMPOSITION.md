# REFACTOR-COMPOSITION: Split src/composition.py into cohesive subpackages

*Status: Ready · Design: AGENTS.md Module-size rule · Created: 2026-11-01*

Depends: none. Zero behavior change; no provider logic changes.

`src/composition.py` is a mega-module (2,585 lines at last count). Split by cohesive responsibility into nested subpackages (one word per path segment, nested — never same-first-name siblings): engine assembly/wiring, op dispatch tables, transport binding. Feature-local helpers stay with their feature; only genuinely shared pure helpers move to small `src/common/` modules. Google-style docstrings throughout. All existing tests stay green; no fixture/contract changes.

Acceptance: composition.py is a thin surface with cohesive homes for each part (no mega-modules; reviewers judge the shape, not a line count); full suite + gate green.
