# STDIO-CONSOLE: MATLAB-esque script console, stdio-only (MVP stretch)

*Status: Backlog · Depends: WORKERS, CLI-DISPATCH · Size: M · Roadmap: orch-build-mvp*

## Why

The user wants Magic-TCL / KLayout-macro-console feel: an
always-on Python prompt with the engine world prebound, for
scripting alongside block editing and AI chat — without opening
any auth or networking can of worms. Local Electron deployments
talk to the engine over stdio with OS identity, so a stdio-only
console is trustworthy by construction: no tokens, no broker,
no remote threat model. Wiring xterm.js to it is cheap
(RocketIDE-side); the engine side is this ticket. Positioned as
MVP stretch: validation gates first, console second.
Hexagonal note: this console shares the op dispatch port with
the CLI (same calls, interactive framing) over the one shared
worker substrate. Adapters never call each other; both face the
same use-case layer. The core depends on no adapter.

## What

- Stdio console adapter as a REPL gateway onto the shared op
  dispatch: cell submit/history/output framing the IDE's xterm
  panel consumes; multiline + script-file cells; every cell
  compiles to the same op calls the batch CLI runs.
- Prebound API on every prompt (`project/tools/pdk/gf/np/plot`)
  per console spec; history persisted (`cells/*.py`,
  `executions/*.yaml`); no tabs needed (single console per panel).
- Approval flow reused from `console.py` (human Run = approval of
  the exact displayed cell); local-only trust documented in code.
- Explicit non-goals: no HTTP transport, no remote execution, no
  multi-user — see REMOTE-EXEC (backlogged).

## Acceptance

- RED-first: on-the-fly + multiline + script cells execute in
  fresh workers with prebounds available, zero setup; history
  persists across restarts; reset kills worker + approvals.
- Local-only trust boundary asserted in tests (no auth code paths
  added, none needed); suite green both configs.
