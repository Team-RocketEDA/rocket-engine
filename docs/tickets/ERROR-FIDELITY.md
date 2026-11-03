Problem: all error types carry fields but no transport serializes them (code+message only); HTTP maps every AdapterError->400 and every engine exception->500 incl. cases needing 403/409/429; 500 bodies leak raw str(exc). Three envelopes (MCP {ok:false}, suggested-api {error:{}}, v1 {code,message,details,retryable}) and two disjoint code vocabularies with no mapping table.
Expected-per: frontend-tooling-spec §3; v1 errors.json (24-code enum + HTTP mapping). Audit MC-30, D-05/D-06/D-07.
Actual-per: http/__init__.py:127-134, mcp/server.py:247-254, cli/__init__.py:123-134, stdio_console.py:893-903.
Ruling: RULING-02 — v1 errors.json wins. Fix: serialize fields; status map (403/409/429+Retry-After/422); v0<->v1 code mapping table; stop raw-exc bodies.

## Step-3 done
Table + statuses + fields + generic-500s in adapters/errors.py;
all transports serialize the triple. Emitted codes stay v0
(fidelity); statuses follow v1. Envelope unification across
MCP/CLI/HTTP/v1 shapes explicitly out of scope (v1 migration).
