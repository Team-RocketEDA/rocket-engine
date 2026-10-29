# ADR-001: Engine owns its root; callers own their files

*Status: accepted (2026-10-29) | Normative detail: [docs/storage-policy.md](../storage-policy.md)*

## Context

The engine needs trusted, shared, reproducible bytes (PDKs, decks,
run evidence) while operating on caller-owned design sources
(IDE workspaces, git checkouts, CI trees) — across headless clients
(MCP, CLI, CI) that have no IDE at all. Someone must own the
filesystem layout, and the choice determines reproducibility,
disk use, and whether headless operation is possible.

## Decision

Split ownership: the engine manages `ENGINE_ROOT` (`pdks/`, `runs/`,
`cache/`, default `projects/`), root configurable via arg → env →
XDG default. Projects are caller-owned and engine-operated in two
modes: managed (under the root) or linked (external path, artifacts
written back to `runs/`). Trust boundary is the rule: trusted bytes
live verified under the root; user files stay put, read by path.

## Alternatives considered

1. **IDE owns all layout.** Rejected: headless clients have no IDE;
   runs would not be reproducible outside it, and PDK sharing /
   verification would be re-implemented per client.
2. **Engine owns everything incl. user files.** Rejected: forces
   copies of workspaces (disk, stale copies), fights git and IDE
   project structures.
3. **Purely caller-passed paths, no engine root.** Rejected: no
   stable identity for PDKs (id+rev+hash), verification cost paid
   per run, no shared cache.

## Consequences

- PDK fetch/register is an engine operation writing to `pdks/`;
  the IDE "menu" is a view over engine ops, not a second store.
- Run records carry PDK id+rev+hash resolvable without the IDE.
- MVP implements local-dir adoption + managed/linked projects;
  remote fetch and cache GC are later ops on the same layout.
