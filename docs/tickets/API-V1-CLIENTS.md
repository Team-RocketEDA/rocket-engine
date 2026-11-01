# API-V1-CLIENTS: Generate and migrate MCP, stdio, HTTP and Python clients to v1

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CORE, API-V1-EDITORS, API-V1-TOOLS, TESTBENCH-COMPONENT. Boundary is canonical v1 bundle and generated outputs. Current v0 generated docs remain current until compatibility/provider tests pass.

Generate transport payloads/client types/help from same schemas; route six methods to one runtime. MCP must never instantiate another Engine for docs. Complete existing framed-stdio/HTTP event bindings under current localhost policy; no new remote/auth product promise. describe returns every method/task/schema/template/effect/tool requirement with bounded version-scoped help. query covers PDK/IP/GDSFactory/provider/project hierarchy/entities/ports/sources/runs/artifacts/request associations with snapshot pagination. watch cursor recovery and capacity pause/resume are mandatory. Same semantic calls from every client yield identical revisions, runs, findings and project effects.

Managed Python exposes full installed library APIs plus generated proxies; publication/edit contexts return real native geometry but commit at explicit checkpoint. No interception fiction, host fallback or package install during execution. Full history/profile/code authority uses existing execution policy, same run receipts/evidence and partial effect retention. No persistent-variable promise across fresh console cells. Legacy adapter maps explicit old op names to v1 with deprecation notice; migration is coordinated across UIUX/RocketIDE/fuel, not a silent break.
