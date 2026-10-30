# API-GEN: Docstring-mandated generated API contract

*Status: Backlog · Size: M · Roadmap: management-plane*

## Why

Three consumers (UIUX frontend, rocket-fuel via MCP help,
generated client types) need one API shape, and today it lives
twice — prose in `docs/engine-api.md`, names in
`vocabulary.py` — with nothing forcing agreement. A third
handwritten copy guarantees drift within a month. ADR-003
makes docstrings the contract source: one text feeds human
docs, machine schemas, and agent help, so drift becomes
structurally impossible. Zero Google-style docstrings exist
today, so this is a genuine migration with a mechanical,
reviewable per-endpoint shape.

## What

- RED-first where code: `AGENTS.md` mandate (Google-style:
  summary, Args, Returns, Raises, `Caution:`) for every
  adapter operation/query handler.
- Guard script in the gate: missing/malformed endpoint
  docstrings fail loudly (same posture as the no-cloud guard).
- Generator deriving from code: human API reference, JSON
  Schema per operation, MCP tool descriptions + help text.
- Migrate `docs/engine-api.md` prose into docstrings per
  endpoint; the file becomes generated output + pointer, never
  hand-edited again.

## Acceptance

- Guard green on the full tree; generated reference covers
  every wired op/query; MCP help serves the same text as the
  docs for a sampled endpoint; a deliberately broken
  docstring fails the gate with the endpoint named.
- Full suite + gate + scenarios green.
