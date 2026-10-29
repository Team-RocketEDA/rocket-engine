# Storage policy: who owns which bytes

One sentence: **the engine owns its root; callers own their files.**

## ENGINE_ROOT (engine-managed)

The engine defines a single root for everything it must *trust*:

```
$ROCKETEDA_HOME/            # default: OS data dir (XDG_DATA_HOME/rocketeda);
  pdks/<id>/<revision>/      # verified PDK copies + manifest (hashes, source, date)
  runs/<project>/<run_id>/   # run evidence (native outputs, findings, verdicts)
  cache/                     # disposable derivations (rebuilt freely)
  projects/                  # DEFAULT home for engine-managed projects (see below)
```

- Root resolves as: explicit constructor/config arg → `$ROCKETEDA_HOME`
  → XDG default. Never a baked path; B10 owns integration.
- `pdks/` entries are immutable once verified: re-fetch/re-register
  re-verifies instead of duplicating. One copy shared by all projects.
- Runs record PDK id + revision + manifest hash, resolvable without
  any IDE present (headless MCP/CI clients must reproduce runs).

## Projects (caller-owned, engine-operated)

Two modes; the caller picks per project:

1. **Managed** — created under `ENGINE_ROOT/projects/`. The engine
   owns the layout. For quick starts, demos, and headless clients
   with no workspace of their own.
2. **Linked** — the caller passes an existing directory (e.g. the
   IDE's workspace, a git checkout). The engine reads design sources
   in place and writes run artifacts to `ENGINE_ROOT/runs/` keyed by
   project id + revision — it never scatters files into the caller's
   tree except through explicit, approval-gated export operations.

## Why this split

- The IDE cannot own the layout: headless clients (MCP, CLI, CI)
  have no IDE, yet must fetch PDKs and reproduce runs identically.
- The engine cannot own user files: workspaces live in git, on
  network drives, in the IDE's own structure. Copying them would
  waste disk and break provenance.
- Trust boundary = the rule: anything the engine must trust (PDKs,
  decks, evidence) is copied-or-verified under its root; anything
  the user owns stays put and is read by path.

## MVP scope

`register_pdk` adopts a local directory into `pdks/` (copy +
manifest + verify). Remote fetch is a later operation on the same
store. Managed projects only where the slices need them; linked
mode is the demo path (fixtures stay in the repo).
