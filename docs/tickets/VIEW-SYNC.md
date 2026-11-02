# VIEW-SYNC: run_view_sync (intended vs extracted comparison)

*Status: Done · Depends: none · Size: S ·
Roadmap: to-GDS lane (MVP track, serves P14)*

## Why

P14 requires comparing extracted physical connectivity
against the INTENDED circuit connectivity — and optical
comparison is explicitly not transistor LVS. `run_lvs`
compares netlists; nothing compares views. `run_view_sync`
takes a source snapshot + compared views + identity
mappings and reports missing/wrong ports, unexpected
connections, and unmapped objects. Small op, load-bearing
for layout-aware photonic verification.

## What

- RED-first: `run_view_sync` ToolAdapter over the
  CONNECT-GRAPH connectivity substrate: intended-vs-
  extracted diff with per-finding identity references.
- Reuses CellLink identity + net IDs; never invents a
  second naming scheme for the compared objects.
- MZI fixture: intended circuit vs perturbed extraction
  yields exactly the planted diffs, nothing more.

## Acceptance

- P14 dispatchable with a findings report; clean
  comparison passes with explicit coverage statement.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
