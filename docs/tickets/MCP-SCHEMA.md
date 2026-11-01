# MCP-SCHEMA: real input schemas on every MCP tool

*Status: Ready · Depends: none · Size: S ·
Roadmap: agent-driving surface (MVP track)*

## Why

The MCP server hand-builds tool definitions and only
`python_execute` has a real `inputSchema`
(`_TOOL_SCHEMAS` has exactly one entry; everything
else presents `{"type": "object"}`). The agent must
guess ~70 tools' arguments or read schemas
out-of-band — the biggest round-trip tax on the
fuel loop. Fuel's own stub gets schemas free from
SDK annotations. Meanwhile `scripts/api_spec.py`
already generates per-op JSON Schema from
docstrings: the schemas exist, they just never
reach the wire.

## What

- Wire the api_spec generator output into MCP tool
  definitions so every cataloged op/query carries
  its real input schema + description.
- Single source: docstrings → api_spec → MCP wire.
  No hand-maintained second schema set.
- Keep the generic-object fallback only for tools
  the generator cannot describe, loudly marked.
- Contract + api_spec regen; full suite + gate green.
- Interim v0 unblock with an explicit sunset:
  API-V1-CLIENTS replaces the MCP wire with v1
  envelopes + generated types; this ticket buys
  fuel its schemas this week, then retires.

## Acceptance

- Every MCP tool definition carries a non-generic
  inputSchema matching the generated api-schema.json
  for that op.
- A new op with a documented docstring gains a wire
  schema with no MCP-server edit (test pins this).
