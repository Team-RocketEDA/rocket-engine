# PDK-DISPLAY: Preserve canonical PDK display id in store records

*Status: Backlog · Depends: PDK-STORE · Size: S · Roadmap: orch-build-mvp*

## Why

Wave-2 review: `register_pdk` slugifies the id and stores the slug
(`sky130A` → `sky130a`) as the manifest `id`, and the same slug
flows into `list_pdks` and the I28 `pdk_ingredient` closure. Lookup
is self-consistent (both sides slugify), and replay works — but
the recorded identity no longer matches the ecosystem's canonical
name, so run records, drift messages, and anything the IDE renders
say `sky130a` where the PDK, decks, and policy template say
`sky130A`. The store already follows the SlugStore (display, slug)
philosophy for minting; the manifest should follow it for
identity: slug on disk, canonical display id in records.

## What

- Manifest v1 (additive): keep the slug-keyed directory layout,
  record the canonical display id alongside (`id` stays the lookup
  slug OR gains a `display_id` — pick one, document it, keep
  `resolve_deck` input normalization unchanged).
- `register_pdk` / `list_pdks` / `pdk_ingredient` return the
  canonical display id; drift/conflict messages use it.
- Bonus, same ticket: include `tree_hash` in `pdk_ingredient`.
  `manifest_hash` covers manifest bytes (including the
  `registered_at` timestamp), so two independent registrations of
  identical content hash differently; `tree_hash` is the
  content-addressed cross-machine identity REPLAY will need.

## Acceptance

- RED-first: register `tiny130A` → record/list/ingredient report
  `tiny130A` while the store dir stays `tiny130a`; ingredient
  includes `tree_hash` equal to the manifest's.
- Old slug-only manifests (v1 without `display_id`) still load:
  display falls back to the slug, never crashes.
- Full suite green both PATH configs.
