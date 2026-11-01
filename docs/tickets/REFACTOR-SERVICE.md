# REFACTOR-SERVICE: Split src/project/service.py (3809 lines, over limit)

*Status: Ready · Design: AGENTS.md Module-size rule · Created: 2026-11-01*

Depends: none. Contracts/tooling only in the sense of zero behavior change; no provider logic changes.

`src/project/service.py` is 3,809 lines, violating the 3,000-line architecture constraint today. Split by cohesive responsibility into nested subpackages (short names, normally no more than two words per path segment): project commands, revisions/snapshots, events, ECS wiring, run admission. Feature-local helpers stay with their feature; only genuinely shared pure helpers move to small `src/common/` modules — no giant `utils.py`, no mega service. Every public function keeps Google-style docstrings. All existing tests stay green; no fixture/contract changes.

Acceptance: no engine source module over 3,000 lines; full suite + gate green; `git diff --check` clean.
