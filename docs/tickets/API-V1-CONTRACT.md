# API-V1-CONTRACT: Freeze canonical v1 API, entities, tasks and consumer artifacts

*Status: Done · Design: ADR-014 · Created: 2026-11-01*

Design complete, provider conformance pending. ADR-014 and contracts/README.md own semantics; contracts/engine-v1.schema.json is the canonical modular bundle. Six methods; typed entities/atomic edits; SPICE availability; scoped testbench templates; canvas.toml; working/pinned/local refs; 33 tasks/65 tool descriptors. Derived types/help/examples/expanded schema checked offline. This ticket's Done status means design artifact only.

Acceptance: checker --write and checker pass all accepted/rejected fixtures through source bundle and expanded schema; no authored schema module >=3000 lines; old generated v0 API untouched; PRD/invariants/ADR authority aligned. No live tool/provider deployment claim.
