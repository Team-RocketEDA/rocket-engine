# REFACTOR-SERVICE: Split src/project/service.py into cohesive subpackages

*Status: Ready · Design: AGENTS.md Module-size rule · Created: 2026-11-01*

Depends: none. Contracts/tooling only in the sense of zero behavior change; no provider logic changes.

`src/project/service.py` is a mega-module today (3,809 lines at last count). Split by cohesive responsibility into nested subpackages (one word per path segment, nested — never same-first-name siblings): project commands, revisions/snapshots, events, ECS wiring, run admission. Feature-local helpers stay with their feature; only genuinely shared pure helpers move to small `src/common/` modules — no giant `utils.py`, no mega service. Every public function keeps Google-style docstrings. All existing tests stay green; no fixture/contract changes.

Acceptance: service.py is a thin surface over cohesive subpackages (no mega-modules; reviewers judge the shape, not a line count); full suite + gate green; `git diff --check` clean.
