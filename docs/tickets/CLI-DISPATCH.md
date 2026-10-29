# CLI-DISPATCH: One command surface (binary + batch + REPL entry)

*Status: Backlog · Depends: none · Size: M · Roadmap: orch-build-mvp*

## Why

Today the CLI is a parked stub while the console plans its own
surface — two syntaxes growing toward one engine. The coherent
shape (Blender rule): `rocket-engine` bare drops you into the
interactive shell (like entering an oss-cad-suite environment, but
for the whole engine); `rocket-engine run <op> …` runs one
operation; batch files run many. Console, MCP, and CLI are then
three syntaxes over one dispatch — test once, document once,
replay console history as CLI scripts. Adapters compose here
(console rides CLI); the core depends on nothing.

## What

- `rocket-engine` entry point: no args → interactive REPL loop;
  `run <operation> [args…]` → single op; `--batch FILE`/`-` →
  batch execute; `--json` → stable machine output.
- argv→op validation shared with MCP/console (one catalog, one
  parser of record); unknown op/args → usage error (exit 2).
- Honest exits: execution-ok is exit 0 *even when the verdict is
  FAIL* (verdict lives in the payload); engine errors exit 1.
  Verdicts from data, never from exit codes — same rule as solvers.

## Acceptance

- RED-first: bare→REPL smoke, single op good/bad, batch file +
  stdin, `--json` shape, unknown-op usage error, FAIL-verdict
  exits 0 with FAIL in payload.
- Console-history-as-CLI-script replay works by construction
  (same dispatch); suite green both configs.
