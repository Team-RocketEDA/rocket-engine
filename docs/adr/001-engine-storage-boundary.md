# ADR-001: Engine owns its root; callers own their files

*Status: accepted (2026-10-29), amended (2026-10-29) by STORAGE-REV | Normative detail: [docs/storage-policy.md](../storage-policy.md)*

## Context

The engine needs trusted, shared, reproducible bytes (PDKs, decks,
run evidence) while operating on caller-owned design sources
(IDE workspaces, git checkouts, CI trees) — across headless clients
(MCP, CLI, CI) that have no IDE at all. Someone must own the
filesystem layout, and the choice determines reproducibility,
disk use, and whether headless operation is possible.

The as-accepted decision put `runs/` beside `projects/` under the
root. The week's storage debates superseded that: run evidence
belongs beside the project it evidences, and the repo's own
`.gitignore` (`results/`, `.rocket/`) already assumed co-located,
gitignored engine state. This amendment reconciles the record
before any storage code lands.

## Decision

Split ownership: the engine manages `ENGINE_ROOT` (`pdks/`,
`cache/`, default `projects/`), root configurable via arg → env →
XDG default. Runs are co-located per project: managed projects
keep `projects/<id>/runs/`, linked projects keep
`.rocket/runs/` inside the caller tree. `pdks/` is the sole
shared store. Policy resolves KiCad-style: global
(`ENGINE_ROOT`) defaults, project-level overrides win, explicit
run arguments win over both. Trust boundary is the rule:
trusted bytes live verified under the root; user files stay put,
read by path; the engine writes into a caller tree only under
the single conventional `.rocket/` dir, never beside sources.

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
4. **Root-level `runs/` keyed by project (as accepted).**
   Superseded by this amendment: evidence separated from sources,
   the root keyed by foreign project ids + revisions, and
   contradicted by the `.gitignore` convention. Co-located runs
   travel with the project (checkout, CI artifacts) with no
   cross-keying.

## Consequences

- PDK fetch/register is an engine operation writing to `pdks/`;
  the IDE "menu" is a view over engine ops, not a second store.
- Run records carry PDK id+rev+hash resolvable without the IDE,
  plus the full ingredient closure I28 demands (project
  revision, deck, solver, seeds, config) — regenerability is
  results, not bytes (see storage-policy).
- MVP implements local-dir adoption + managed/linked projects;
  remote fetch and cache GC are later ops on the same layout.
- Exact dir/file names are owned by LAYOUT-SCHEMA; PATH-GUARD
  owns name safety; PDK-STORE owns the `pdks/` manifest format.
