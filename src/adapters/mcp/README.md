# adapters/mcp — project-scoped MCP stdio server

The MCP bridge exposes the engine operation and query vocabulary as tools. `McpTransport` validates and routes calls to the same `Engine.submit` path used by other clients; the server itself owns no agent loop, queue policy, or verdict logic. stdout is reserved for MCP protocol traffic.

## Trust boundary

Local-only trust: this server speaks stdio to the local harness under OS identity — no tokens, no listener, no remote execution, no multi-user, hence no auth step (the named `TRUST_NOTE` in `server.py`). Human Run on the displayed cell is the approval; the harness edge (rocket-fuel client permissions) owns ask/deny. Same caller-blind API as every other transport; localhost-only, no auth.

## Project binding

`--project` binds the server to one project and fills the project ID and current expected revision for mutation calls. `--project-dir` additionally confines `run_spice` source paths to that project, loads run targets from its `constraints.yaml`, chooses the run work directory, and writes completed run evidence under `results/engine-runs/`.

Normal solver operations currently execute inline through `submit` and return their completion. `run_job` remains available for deferred work, pool draining, and idempotent result retrieval. This differs from older Fuel notes that describe every run as a two-call admission/execution sequence; use the [current Engine implementation](../../composition.py) and generated [API reference](../../../docs/engine-api.md) for the live behavior.

## Tool descriptions and schemas

Descriptions are derived from the same handler docstrings used by the generated API reference. The MCP `inputSchema` is still generic for most operation/query tools; `python_execute` is the current specific-schema exception. The open [MCP-SCHEMA ticket](../../../docs/tickets/MCP-SCHEMA.md) tracks wiring generated schemas to every tool. `cancel_job` is also not yet part of the public operation vocabulary.

Python execution requests an approval; the agent cannot approve its own code. Approval resolution belongs to the trusted client path. See [`execution/`](../../execution/README.md), the [Fuel contract note](../../../docs/fuel-contract.md), and the [PRD harness boundary](../../../../PRD/harness/README.md).
