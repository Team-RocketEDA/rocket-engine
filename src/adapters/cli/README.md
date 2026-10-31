# Adapters/cli — headless command surface

## Responsibility (project decision)

Every engine operation invokable, every event printable: the terminal
client for debugging the headless engine without RocketIDE. Bare
args drop into the interactive REPL; `run <op> [key=value ...]`
runs one op; `--batch FILE`/`-` batch-executes; `--json` gives
stable machine envelopes. Entry: `python -m rocket_engine` (a
`[project.scripts]` `rocket-engine` alias can point at
`adapters.cli:main` once packaging wires it).

## Boundaries

Same as every transport: protocol ↔ ports only. No logic. argv
parsing/formatting lives here; op-call parsing and dispatch live in
the use-case layer (`execution.dispatch`, the inbound port shared
with console/MCP over the one catalog). Adapters never call each
other.

## Routing

- Parent rules → `../README.md`.

## Exits (honest)

- 0 execution-ok, EVEN when the verdict is FAIL (verdicts live in
  the payload, never in exit codes — same rule as solvers).
- 1 engine error. 2 usage error (unknown op/args).

## Status

Live (CLI-DISPATCH). Console history replays as CLI batch scripts
by construction — same dispatch, same grammar.
