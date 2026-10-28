# adapters — one duplex adapter per channel

## Responsibility (PRD)

Every edge implementation lives here. Each submodule owns its full
round trip, both directions — no inbound/outbound grouping. Transports
drive engine use cases through the `interfaces/` ports; solver wrappers
implement those ports against real tools
([frontend-tooling-spec §1, §8](../PRD/tools-research/frontend-tooling-spec.md),
[tech-stack transports](../PRD/tech-stack.md), blueprint B5/B7/B9).

| Submodule | Channel | PRD source |
|---|---|---|
| `api/` | HTTP service (FastAPI routes + SSE) | tech-stack "Web service" |
| `ipc/` | Electron main ↔ engine framed stdio | tech-stack "Desktop engine transport" |
| `mcp/` | MCP stdio bridge for the agent harness | suggested-api §10, harness §3.4, B9 |
| `cli/` | Headless debug client | project decision, parked stretch goal |
| `<solver>/` | One per tool family (ngspice, magic, sax, …) | verification-process adapter table, B7 |

## Inputs

- `../interfaces/README.md` (the ports each adapter speaks).
- Outside bytes (transports) or engine jobs (solvers).

## Outputs

- Transport adapters: engine commands in, project events out.
- Solver adapters: tool invocations out, normalized evidence in.

## Boundaries

Owns: protocol framing, tool CLIs, output parsing. Must not own:
business rules, state, verdicts — and no adapter imports another.

## Routing

- What commands/events look like → `../interfaces/README.md`.
- How jobs are queued and judged → `../execution/README.md`.
- Which tool to wrap next → `../workflows/README.md` (plan slots).

## Status

Transports GREEN (slice 4): `api/`, `ipc/`, `mcp/` speak the ports
against any engine; `ToolAdapter` port defined in `interfaces/`
(re-exported here). CLI stays parked. No solver wrapper yet — needs
its own RED plus toolchain + PDK decks. Tests: `tests/adapters/`
(4 passed vs fake engine).
