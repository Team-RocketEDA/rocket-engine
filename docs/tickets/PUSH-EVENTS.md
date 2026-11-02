Problem: "Duplex" is docstring-only. MCP exposes list/call handlers only (server.py:325-405), HTTP has no SSE (README:3), IPC has no event stream (README:5). Polling get_events_since is the only watch path; on_live progress stays in-process (worker.py:355-356).
Expected-per: frontend-tooling-spec.md:154-166 (ordered events), contracts v1 watch, tech-stack MCP/HTTP same semantics. Audit MC-03.
Actual-per: zero notification/progress/subscribe hits across mcp+http+ipc.
Fix: MCP notifications/progress + HTTP SSE + IPC event stream. Minimum honest interim step: fix "duplex" docstrings to "request/response + get_events_since polling".
