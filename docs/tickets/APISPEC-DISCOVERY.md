Problem: scripts/api_spec.py resolves handlers through static maps
(solver_map, crud, run_job/python_execute special cases, query
maps). Submit-branch job-control ops match none, so wired ops
render as "Declared operation `X`; no handler wired yet."
(wired:false, empty schema) in engine-api.md, api-schema/help.json,
contract.json, and the MCP wire falls back to the generic object
schema. Affects resume_run, discard_run, resume_all_retryable,
cancel_job — all four carry complete Google docstrings already.

Expected-per: ADR-003 docstrings are the single contract source;
adapters consume the generated spec. A wired op must render wired.

Fix: teach endpoint_spec/section_body/build_schemas an Engine-op
address map (op -> Engine method on composition.py, _method_section
already supports rel=composition.py/cls=Engine), so docstring text
flows through with no generator prose. Consider making
Engine.cancel_job's run_id a required positional (behavior already
raises invalid_command without it; signature currently defaults
None, which would derive as optional). Add contract-sync checks:
every cataloged name resolves identically through engine submit,
the generated spec, and HTTP/IPC/MCP/CLI adapters. Regen all
artifacts; RED->GREEN on api-spec/mcp-schema/contract freshness.
Out of scope: replacing the renderer with Sphinx/pdoc (human docs
only; JSON-Schema/MCP derivation stays custom).
