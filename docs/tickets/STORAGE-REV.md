# STORAGE-REV: Amend ADR-001 for co-located runs

*Status: Backlog · Depends: none · Size: S · Roadmap: orch-build-mvp*

## Why

ADR-001 (runs/ beside projects/ under the root) was written before
the week's storage debates and now contradicts them — and the
repo's own `.gitignore` (`results/`, `.rocket/`). A stale ADR is
worse than none: slices built on it (PDK-STORE, LAYOUT-SCHEMA)
would encode the wrong layout. This ticket reconciles the record
before any storage code lands.

## What

- Amend ADR-001 + storage-policy: runs co-located per project
  (managed `projects/<id>/runs/`, linked `.rocket/runs/`),
  `pdks/` the sole shared store, KiCad-style global→project
  policy precedence.
- Record I28 (verbatim + results-not-bytes interpretation),
  ingredients-vs-exhaust test, and ordering-as-hygiene.

## Acceptance

- Docs committed; LAYOUT-SCHEMA/PATH-GUARD/PDK-STORE bodies
  consistent with the amended ADR (no contradictions on re-read).
