Problem: "Duplex" is docstring-only. MCP exposes list/call handlers only (server.py:325-405), HTTP has no SSE (README:3), IPC has no event stream (README:5). Polling get_events_since is the only watch path; on_live progress stays in-process (worker.py:355-356).
Expected-per: frontend-tooling-spec.md:154-166 (ordered events), contracts v1 watch, tech-stack MCP/HTTP same semantics. Audit MC-03.
Actual-per: zero notification/progress/subscribe hits across mcp+http+ipc.
Fix: MCP notifications/progress + HTTP SSE + IPC event stream. Minimum honest interim step: fix "duplex" docstrings to "request/response + get_events_since polling".

## Verdict (runtime slice, 2026-11-03)

MCP and IPC push are implemented; HTTP SSE is out of this
slice's owned set and stays outstanding (polling remains the
HTTP watch path — no docstring claims otherwise were added).

MCP (`src/adapters/mcp/server.py`, append-only):
`build_lifecycle_notification` maps runtime events to
`notifications/<kind>` (`notifications/progress` for
job_progress); `subscribe_runtime` registers a push listener.
Existing list/call handlers are byte-identical in behavior —
62 neighboring tests green
(`tests/adapters/test_mcp_server.py`,
`tests/adapters/test_transports.py`,
`tests/adapters/test_transport_parity.py`,
`tests/test_coalesce.py`, `tests/test_coalesce_wiring.py`,
`tests/execution/test_execution_service.py`) plus 4 new
`tests/adapters/test_mcp_notify_lifecycle.py` tests.

IPC (`src/adapters/ipc/__init__.py`, addition-only):
`EventStream` wraps `EngineRuntime.watch` (`since`) plus
`subscribe`; `IpcTransport.handle` is untouched. Covered by
`tests/test_async_submit_deferred.py::test_ipc_stream_sees_same_lifecycle`.
