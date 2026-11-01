# API versions and evidence

The v1 design contract names `describe`, `query`, `edit`, `run`, `script`, and
`watch`. A deployed runtime can still expose the current v0 surface while the
provider migrates. Choose from actual exposed tool schemas and compatibility
metadata, not from an assumed endpoint name.

In a source checkout, `docs/engine-api.md`, `docs/api-schema.json`, and
`docs/api-help.json` describe generated v0 handler behavior. The `Wired` column
matters: a name in the vocabulary does not prove the route exists. In the source
snapshot reviewed November 1, `api_help`/`api_info`/`api_search` are declared but
unwired. Use supplied transport descriptions and canonical artifacts until the
conforming discovery service is available. Do not construct a second Engine to
obtain help.

Legacy calls such as `run_spice`, `run_hdl_test`, `run_drc`, `run_lvs`,
`run_digital_flow`, `get_job_status`, `get_logs`, and `get_events_since` remain
legacy calls; they do not automatically accept a v1 request envelope. The
selected transport's exact schema decides their arguments. Existing adapters
can have narrower source/model/output support than the v1 design.

V1 replaces routine tool-specific transport calls with a typed `run.start`
task. It does not require a mandatory second `run_job` start handshake. Current
legacy deferred execution can still have that handshake: follow the runtime's
actual receipt/lifecycle contract, and do not pump a conforming v1 run twice.

Use current capability and readiness records for installation/qualification.
Native tool versions, model dialects and PDK/deck coverage affect valid tasks.
A mock provider or a schema-valid fixture can help test clients but cannot
qualify a real solver. Report exactly which source supplied an observation.
