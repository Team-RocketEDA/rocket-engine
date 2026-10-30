# Storage policy: who owns which bytes

One sentence: **the engine owns its root; callers own their files.**
Carve-out: the engine writes into a caller tree only under the
single conventional `.rocket/` dir — never beside sources.

## ENGINE_ROOT (engine-managed)

The engine defines a single root for everything it must *trust*:

```
$ROCKETEDA_HOME/            # default: OS data dir (XDG_DATA_HOME/rocketeda);
  pdks/<id>/<revision>/      # SOLE shared store: verified PDK copies + manifest
  cache/                     # disposable derivations (rebuilt freely; never trusted)
  projects/<id>/             # DEFAULT home for engine-managed projects (see below)
    runs/<run_id>/           # co-located run evidence (native outputs, findings, verdicts)
```

- Root resolves as: explicit constructor/config arg → `$ROCKETEDA_HOME`
  → XDG default. Never a baked path; B10 owns integration.
- `pdks/` entries are immutable once verified: re-fetch/re-register
  re-verifies instead of duplicating. One copy shared by all projects.
- `cache/` holds regenerable derivations only. It is not a store:
  nothing in it carries identity, nothing trusted is read from it,
  and deleting it costs only rebuild time.
- Runs record PDK id + revision + manifest hash, resolvable without
  any IDE present (headless MCP/CI clients must reproduce runs).

## Projects (caller-owned, engine-operated)

Two modes; the caller picks per project. Both co-locate runs with
the project they evidence — evidence travels with sources
(checkout, CI artifacts) instead of living keyed by foreign ids
under a central `runs/` (that layout was ADR-001 as accepted;
STORAGE-REV superseded it).

1. **Managed** — created under `ENGINE_ROOT/projects/<id>/`. The
   engine owns the layout; runs live at `projects/<id>/runs/`.
   For quick starts, demos, and headless clients with no
   workspace of their own.
2. **Linked** — the caller passes an existing directory (e.g. the
   IDE's workspace, a git checkout). The engine reads design
   sources in place and writes run evidence to
   `<project>/.rocket/runs/` — co-located, gitignored exhaust,
   consistent with the repo's own `.gitignore`
   (`results/`, `.rocket/`).

## Policy precedence (KiCad-style: global → project)

Like KiCad's global preferences vs per-project settings:
`ENGINE_ROOT` holds global defaults (timeouts, threads, flags,
deck/tool fallbacks, seeds); each project may override beside
its runs (managed: inside `projects/<id>/`; linked: inside
`.rocket/`). Precedence, highest first:

1. Explicit per-run arguments.
2. Project-level policy.
3. Global (`ENGINE_ROOT`) policy.
4. Template-required entries: anything that matters must be
   present and non-empty somewhere in the chain, or startup
   fails loudly (zero silent defaults; exact names owned by
   LAYOUT-SCHEMA).

## I28: runs regenerate from recorded ingredients

New behavior invariant, promoted to the PRD list as I28
(`tools-research/behavior-invariants.yaml`) on 2026-10-29:

- **I28 — Run regenerability from recorded ingredients.**
  Given a stored run record with pinned project revision and
  PDK id + revision + manifest hash; when the run is replayed;
  then it reproduces the recorded results, and drift in any
  ingredient fails loudly naming the drifted field.

*Results-not-bytes interpretation:* "reproduces" means the same
results — verdicts, findings, measurements — not byte-identical
native outputs. Timestamps, absolute paths, and tool banner
strings legitimately differ across machines and reruns; the
comparison is over results. REPLAY automates this check once
the recipe format stabilizes under PDK-STORE.

*Ingredients-vs-exhaust test:* if deleting it still leaves the
run regenerable from the record, it is exhaust — gitignored,
cached, never the source of truth. If the run cannot be
regenerated without it, it is an ingredient — pinned and kept:
project revision, PDK id + revision + manifest hash, deck,
solver + version, seeds, resolved config.

*Ordering-as-hygiene:* everything the engine mints (run
records, findings, events) uses canonical ordering — sorted
keys, seq-ordered events — so regenerability comparisons are
diffs of substance, never of serialization order.

## Ledger durability + retention (LEDGER-DURABLE/I30)

Managed and linked projects alike keep their ledger under
`ENGINE_ROOT/projects/<id>/`: `events.yaml` (seq-ordered
actor-attributed events) plus `ledger.yaml` (current revision +
admitted-request identity for idempotent replay and `run_job`
lookup). The ledger is engine truth, not caller bytes, so linked
trees never carry it — the engine still writes into caller trees
only under `.rocket/`. Both files are schematized (optional,
engine-owned) in `layout_schema.yaml`; the writer also creates
`runs/` alongside so `validate_tree` stays green.

- Every accepted mutation advances the revision and appends its
  event; `run()` appends `run_completed` (PASS/FAIL verdict) or
  `run_failed` (NOT_RUN) with the run's verdict, never a bare id.
- Retention keeps the newest 10,000 events per project
  (constructor-overridable), trimmed oldest-first on append; the
  `ledger.yaml` head is never trimmed.
- `resync_required` means the reader's `require_contiguous_from`
  fell below the retained head (history aged out) or ahead of the
  live cursor (reader ahead of truth). Either way the reader must
  re-read the snapshot plus the full retained log and reset its
  cursor — never assume the gap is empty.
- Writes are atomic per file (sibling temp + rename), events
  before head; a crash between the two can leave an event ahead of
  its head, which the next accepted mutation reconciles by
  re-advancing from the head. Reads and mutations reload durable
  state first, so sequential writers through separate handles stay
  ordered; truly concurrent writers need an external lock (future
  work, not this slice).

## Document storage (CRUD-API/I31)

Managed-project documents live beside the ledger as plain files
under `ENGINE_ROOT/projects/<id>/` (in-memory map when no engine
root). `ledger.yaml`, `events.yaml`, and `runs/` are engine-owned
and rejected as document paths; everything else is addressable by
its unix path, including the conventional `components/` and
`scripts/` prefixes (no per-content verbs, no schema gate on
contents). Documents are UTF-8 text capped at 1 MB; `list_docs`
excludes engine-owned entries and accepts a segment-aware prefix
filter. Writes are atomic per file (sibling temp + rename);
`apply_mutations` validates the whole batch before anything lands
and rolls back best-effort on a mid-batch I/O failure, so a
half-landed batch is never a visible state.

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
mode is the demo path (fixtures stay in the repo). Run records
capture the I28 ingredient closure from the first slice that
writes them — no record format without regenerability.
