# ADR-003: API contract generated from Google-style docstrings

*Status: proposed (2026-10-30)*

## Context

Three consumers need the engine API shape: frontend developers
(UIUX repo), the rocket-fuel agent (via MCP help), and generated
client types. Today the shape lives twice — prose in
`docs/engine-api.md`, names in `interfaces/vocabulary.py` — with
nothing forcing agreement. A third handwritten copy (IDE types,
fuel stub shapes) guarantees drift within a month.

## Decision

Docstrings are the contract source. Every adapter
operation/query handler carries a Google-style docstring
(summary, Args, Returns, Raises, plus a `Caution:` line where
the endpoint can bite). A generator derives from code:

- the human API reference (replaces hand-written endpoint prose),
- JSON Schemas per operation (machines: IDE types, fuel stub),
- MCP tool descriptions and help text (agent clarification).

One text, three consumers; drift becomes structurally
impossible. `AGENTS.md` mandates the docstring rule for
contributors (human and agent), enforced by a guard script in
the gate — missing or malformed endpoint docstrings fail
loudly, the way the no-cloud guard fails on cloud imports.
`docs/engine-api.md` prose migrates into docstrings per
endpoint then the file becomes generated output plus a
pointer, never hand-edited again.

## Alternatives considered

1. **Separate OpenAPI/IDL file as source.** Rejected: a second
   source beside the code reintroduces the drift the decision
   exists to kill; the engine's surface (opaque `arguments`
   dicts per op) fits docstring + schema generation better
   than REST-first IDL.
2. **Keep prose doc authoritative.** Rejected: prose rots; no
   machine checks it against the code.
3. **Hand-written IDE/fuel types.** Rejected: duplicates the
   contract per consumer; each copy can silently redefine the
   interface (contract-first FAIL case).
