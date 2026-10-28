# adapters/mcp — MCP bridge for the agent harness

## Responsibility (PRD)

Thin project-bound bridge over MCP stdio (official Python MCP SDK):
typed tools for discovery, checks, bounded results, and approved
console submission — all delegating to the same engine operations the
UI uses ([suggested-api §10](../PRD/tools-research/suggested-api.md),
[harness §3.4](../PRD/harness/README.md), blueprint B9,
[tech-stack](../PRD/tech-stack.md) MCP row). MCP owns no agent loop, no
queue, no verification store. stdout carries protocol only. Approvals
resolve through the trusted UI route, never as an MCP tool.

## Boundaries

Owns: tool schemas derived from engine ports, argument bridging,
bounded replies with cursors. Must not own: preflight, evidence,
agent behavior, self-approval.

## Routing

- Operation list → `../../interfaces/README.md` (catalog).
- Console/approval rules → `../../execution/README.md`.
- Harness side → PRD `harness/README.md`.

## Status

Stub (empty). Slice 9 (after engine + console exist). Invariants I05,
I12, I19 (harness boundary). Tests: `tests/adapters/` vs fake engine.
