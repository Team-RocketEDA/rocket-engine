# adapters — transport edges and solver integrations

This package contains the client transports and wrappers around existing EDA tools. composition.Engine selects a registered solver for each operation. Adapters return normalized results; project state and verdict rules stay in engine services.

## Client transports

| Adapter | Current surface |
|---|---|
| cli/ | Interactive command loop, one-operation mode, sequential --batch, and JSON output; entry point is python -m rocket_engine. |
| mcp/ | Project-scoped MCP stdio server with one tool per catalog operation/query; descriptions come from handler docstrings. Most input schemas remain generic. |
| http/ | HttpTransport.handle routes one JSON command/query envelope; serve_http adds a stdlib POST listener on loopback only (no auth, ADR-006). SSE is not implemented here. |
| ipc/ | IpcTransport.handle routes one JSON command/query envelope. Length-prefix framing and Electron child-process lifecycle are not implemented here. |

Events are read through the engine event-query surface; HTTP SSE and pushed IPC events are not currently provided by these transport classes.

## Registered solver adapters

| Operation | Registered tool(s) |
|---|---|
| run_drc | Magic (default), KLayout |
| run_hdl_test, run_syntax, run_formal, run_synth, run_timing | Icarus, Slang, SBY, Yosys, OpenSTA |
| run_spice, run_post_layout, run_cosim | ngspice; run_cosim also uses Icarus |
| run_optical, run_em | SAX/Circulax, MEOW |
| run_extraction, run_lvs | Magic, Netgen |
| run_connectivity, run_erc, run_view_sync | connectgraph |
| generate_views | GDSFactory |
| run_digital_flow | LibreLane |

The exact registration order and default tool are in [composition.py](../composition.py). A registered adapter can still be blocked by a missing executable, incompatible PDK/deck, or an unqualified flow. Use get_capabilities for machine-specific readiness; see the [DIGITAL-FLOW report](../../docs/work/DIGITAL-FLOW/report.md) for the current live-flow limitation.

## Boundaries

Transport adapters validate the envelope and project scope, then call Engine.submit. Solver adapters implement the ToolAdapter port and own tool invocation and output parsing. The intended module boundary forbids solver adapters from importing one another. Current exception: CosimAdapter calls HdlSimAdapter directly for its digital half; treat this as existing boundary debt, not a pattern to extend.

For endpoint documentation rules, see [AGENTS.md](../../AGENTS.md). For operation names, see [interfaces](../interfaces/README.md) and the [generated API reference](../../docs/engine-api.md).
