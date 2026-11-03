# API-V1-CLIENTS: Generate and migrate MCP, stdio, HTTP and Python clients to v1

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, API-V1-EDITORS, API-V1-TOOLS, TESTBENCH-COMPONENT. Boundary is canonical v1 bundle and generated outputs. Current v0 generated docs remain current until compatibility/provider tests pass.

Generate transport payloads/client types/help from same schemas; route six methods to one runtime. MCP must never instantiate another Engine for docs. Complete existing framed-stdio/HTTP event bindings under current localhost policy; no new remote/auth product promise. describe returns every method/task/schema/template/effect/tool requirement with bounded version-scoped help. query covers PDK/IP/GDSFactory/provider/project hierarchy/entities/ports/sources/runs/artifacts/request associations with snapshot pagination. watch cursor recovery and capacity pause/resume are mandatory. Same semantic calls from every client yield identical revisions, runs, findings and project effects.

Managed Python exposes full installed library APIs plus generated proxies; publication/edit contexts return real native geometry but commit at explicit checkpoint. No interception fiction, host fallback or package install during execution. Full history/profile/code authority uses existing execution policy, same run receipts/evidence and partial effect retention. No persistent-variable promise across fresh console cells. Legacy adapter maps explicit old op names to v1 with deprecation notice; migration is coordinated across UIUX/RocketIDE/fuel, not a silent break.

## Verdict — client migration (CLIENTS wave, 2026-11-03)

All four transports plus the Python client now serve one
integrated runtime. Engine/vocabulary/service/runtime files are
untouched; everything below delegates to public Engine methods.

- `src/clients/runtime.py` (`RuntimeClient`): sync submit plus
  the deferred surface — submit/pump/wait/status/fetch/cancel,
  watch with cursor recovery, survivors/resume/discard/
  resume-all/replay. No second runtime is ever constructed.
- Transport seams (addition-only, existing paths byte-identical):
  `McpTransport`/`HttpTransport`/`IpcTransport`/`StdioConsole`
  each gained `runtime_client()` over their bound engine.
- `clients/python/client.py`: `connect(project_id, ...)` builds
  one Engine and serves its runtime through `RuntimeClient`.
  No legacy op renames exist in the tree (verified by search),
  so no deprecation map ships — any future rename lands there
  with a DeprecationWarning instead of a silent break.
- One-runtime identity proved: the same semantic call through
  MCP, HTTP, and IPC admits one run id with one completion;
  a deferred run submitted via one transport pumps/waits/
  fetches via the others; identical in-flight deferred calls
  share one execution (runtime coalescing, observed).
- Watch recovery: an expired cursor replays from the floor with
  `resynced: True` plus the current revision. Capacity:
  saturation refuses retryable with admitted False (client
  `paused`), and pump/cancel/admit clears it.
- Proof: `tests/test_v1_clients_runtime.py` (7 tests) green.
- Carry V1C-2 (core/composition lane): push subscriptions still
  take `runtime=` explicitly (HTTP `/events`, MCP
  `subscribe_runtime`, IPC `EventStream`) because the engine
  exposes no public runtime-listener accessor — servers cannot
  default to the integrated runtime without one.
