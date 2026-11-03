# E2E-AUDIT: Routing audit — submit honesty, run_job, run_syntax

*Status: Done · Size: M · Roadmap: e2e-verification*

## Why

A vocabulary × transport audit found shipped features that were
tested but unreachable: submit-only transports (MCP/IPC/HTTP)
could never execute anything (terminal `queued` acks, queue
never drained), `run_syntax` had a port-tested Slang adapter
with no Engine route, and `submit()` queued unwired operations
while `ProjectError` crashed the MCP server.

## What

- `submit()` rejects unwired ops (`unsupported_operation`); MCP
  handler catches `ProjectError` into structured `isError`.
- New `run_job(request_id)` op: two-phase submit→run over
  `run()` directly and all submit-only transports, zero
  transport edits; unknown ids raise `unknown_request`.
- Wired `run_syntax → slang` (7th solver), live-proven.
- Full gates on fixed HEAD.

## Acceptance

- 756 passed / 33 skipped, 0 failed (baseline 746 + 10 new).
- Gate 4/4 (44/0/0), scenarios 26/0, no-cloud clean.
- Commits 883cacc, 70c7cb7, 860620e, 67a6daf, 295e8c1, e39ac28.
