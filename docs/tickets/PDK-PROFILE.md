# PDK-PROFILE: Hexagonal PDK organization (refactor after concrete proofs)

*Status: Backlog · Depends: PDK-CSPDK, PDK-GF180, PDK-IHP · Size: M · Roadmap: pdk-onboarding (MVP track)*

## Why

TDD writ large: concrete per-PDK RED-GREEN slices first,
then this refactor generalizes what they proved. Each proof
slice wires relpaths/flags/quirks for one PDK; left
unfactored, that accretes into per-PDK `if` branches across
adapters (including today's baked-in sky130-isms like
ngspice's `set skywaterpdk`). This ticket organizes PDK
support hexagonally so practically anything can dock:
adapters read a PDK profile record (data), never PDK
special-cases (code); new PDKs arrive as profile entries +
recipes + proofs, with zero adapter edits.

## What (after ≥3 proofs land)

- RED-first: profile record schema (decks, models, tech,
  symbols, solver flags per PDK) + adapter migration to
  profile-driven resolution; sky130-isms evicted to the
  sky130 profile entry. Ports model PDK *capabilities*
  (resolve deck/model/symbols), never PDK identities:
  per-PDK differences live in profile data + recipes,
  never in adapter branches (hexagonal strangler, no
  big-bang).
- Re-proof: every landed PDK proof green unchanged
  (refactor, not behavior change); a checklist for future
  PDKs (profile + recipe + proofs, no adapter edits).

## Acceptance

- All landed PDK proofs green; grep shows no PDK id
  literals in adapter logic (profiles + tests only);
  full suite + gate + scenarios green.

## Direction lock (2026-10-31, owner call)

- gdsfactory-first: all 7 PDKs plug in as gdsfactory pip
  packages + KLayout tech install. Bespoke per-PDK engine
  integrations are forbidden; per-PDK slices keep the
  profile + recipe + live-proof shape with gdsfactory-shaped
  recipes. Profile record: {gdsfactory package pin, KLayout
  tech, decks (PDK-supplied or user-supplied), models}.

## Pattern verdict (2026-11-02, ngspice slice)

One adapter migrated as the pattern; the rest are documented
follow-ups (no big-bang).

- Schema + record: `src/adapters/profile.py` (new) loads and
  validates lane files (`rocketeda/pdk-profile/v0.1`: schema,
  id required; `invalid_profile` otherwise) and serves sim
  needs (`default_model_rel`, `spiceinit_for`, `render_spiceinit`).
  Lane authority is `docs/pdk/<lane>/profile.yaml`; a builtin
  copy covers installed wheels (no docs shipped).
- sky130 lane added: `docs/pdk/sky130a/profile.yaml` (new —
  no existing lane file touched) records the open_pdks tree
  distribution (tech, decks, models, sim corners
  tt/ss/ff/sf/fs per the vendored bandgap `sim/pdk.json`
  process-corners note, spiceinit extras). The pip repack stays
  the separate `sky130gf` lane.
- ngspice migrated: `_MODEL_REL` / `_SPICEINIT` literals evicted
  to the profile; the adapter reads defaults from
  `rocket_engine.adapters.profile` (explicit `model_rel` still
  wins; a PDK with no sim profile and no explicit `model_rel`
  fails loudly `invalid_command`, never a guessed relpath).
  `grep -rni sky130|skywater` on `src/adapters/ngspice/__init__.py`
  is empty; remaining literals live in profile data + tests only.
  Class/preflight/execute/parse docstrings are byte-identical
  (generated-docs freshness preserved; the new loud case is
  noted here, not in the rendered contract).
- Proven: `tests/adapters/test_ngspice.py` semantics unchanged
  (default-rel staging, spiceinit base line, drift/revision
  loudness); `/tmp` RED->GREEN probes pin the schema + defaults.
- Follow-ups (other agents/lanes, not this slice): cosim and
  postlayout adapters still carry their own sky130 `_MODEL_REL` /
  `_SPICEINIT` copies; LVS/DRC/magic decks keep per-PDK relpaths
  in code. Live-sim proofs still need ngspice on PATH
  (NGSPICE-LIVE owns the binary gate).
- Carry (BUILD-LOCAL stage 2, this slice): `prov_bin_dirs` and
  `resolve_engine_root` default to the repo-local `.tools` /
  `.stores/rocketeda`; explicit env still wins with a migration
  note for legacy `~/tools` / `~/.local/share/rocketeda` users.
  `tests/interfaces/test_pdk_store.py::test_engine_root_resolution_chain`
  still asserts the legacy default and needs its owner's
  one-line update to the new default (surfaced, not edited here).

## Verdict (adapt lane, 2026-11-03) — follow-ups scoped, not migrated

cosim/postlayout/LVS/DRC migration to profile-driven resolution
is documented but NOT implemented in this lane: postlayout
`adapter.py` and cosim carry their own sky130 `_MODEL_REL` copies
and LVS/DRC/magic decks keep per-PDK relpaths in code (other
agents/lanes own those files; this lane touches
`src/adapters/postlayout/` translation only and
`src/adapters/drc/klayout.py` LVS path only). No
`docs/pdk/*/profile.yaml` lane file was added or rewritten here —
existing 8 lanes already cover the PDKs this lane's templates
generate for, and the ONLY-to-add constraint forbids rewriting
them. New adapters in this lane read no PDK literals (profile +
tests only), consistent with the hexagonal direction.
