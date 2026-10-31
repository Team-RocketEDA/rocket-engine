# ASAP7-DRC-DECK lane report: clean-room KLayout DRC deck for ASAP7 r1p7

Status: GREEN. Branch: GREEN-the-tests (no commit, no push: parent
integrates). No existing file was modified; no wiring patch is needed
(the deck runs through the adapter deck mode unchanged, and pytest
auto-discovers the new test files).

## What was delivered

- `asap7.drc`: our own KLayout DRC deck transcribing the DRM core
  rule set (117 breaker-verified instantiated checks; 112
  instantiated rules + companion/split categories — see
  inventory.md). Runs via the existing adapter deck mode unchanged:
  `klayout -b -rd input=<gds> -rd report=<lyrdb> -r asap7.drc`.
- `inventory.md`: full DRM ch. 3 inventory — 201 table rows + 1
  note-rule (V3.M3.EN.1), 331 instantiated checks, 112 implemented,
  every deferral recorded with a reason, companion allowances, and
  DRM sic notes (M8.W.5 operator, V6.W.1 "M5", figure-only LISD.S.5/
  SRAM.LISD.S.6, V1.AUX.1 mistype).
- `fixtures/spec.json` + `fixtures/make_fixtures.py`: committed,
  reviewable geometry spec (117 per-rule breakers + `clean_all` and
  `empty` refs); GDS is generated at test time (repo ignores *.gds).
- `tech/gen_tech.py` + generated `tech/asap7.lyt` / `tech/asap7.lyp`:
  technology + display layers from the PDK layer table; the .lyt
  loads natively in KLayout 0.28.16; regen is byte-identical.
- `tests/test_asap7deck_inventory.py`, `tests/test_asap7deck_deck.py`,
  `tests/test_asap7deck_tech.py`: RED-first tests (new files only).

Acceptance: every breaker trips exactly its rule (12 documented
geometric companions in `also`), `clean_all`, `empty`, and the real
PDK cell `tests/pdk_asap7/fixtures/invx1_r.gds` are marker-free,
waivers are DRM-cited in inventory.md (none silent).

## Clean-room source list (complete; review gate)

External sources read, and nothing else:

1. `/tmp/asap7r1p7-probe/docs/asap7_drm_201207a.pdf` — the DRM
   (ASU Dec 2020); read via a `pdftotext` extraction to scratch.
2. `/tmp/asap7r1p7-probe/cdslib/asap7_TechLib_10/asap7_TechLib.layermap`
   — stream numbers/names (read fully).
3. `/tmp/asap7r1p7-probe/cdslib/asap7_TechLib_10/asap7_TechLib_08.layermap`,
   `asap7_fromAPR.layermap`, `asap7_fromAPR_08b.layermap` — searched
   for a Pad drawing stream only (none; hence V9-top deferrals).
4. KLayout's own documentation (klayout.de): DRC basics/runsets,
   layer-object reference (check functions, options, selectors),
   technology management; plus KLayout 0.28.16's own behavior
   (introspected API, native `.lyt` output mirrored for schema).

Repo files read (in-scope by definition): the ticket, the drc_kl
adapter + README, the sky130 deck-mode test (adapter-use pattern
only), `tests/pdk_asap7/_profile.py` + `fixtures/invx1_r.gds`
(clean-ref use), `tests/adapters/fixtures/drc_kl/make_cells.py`
(fixture-generation pattern), AGENTS.md, pyproject, .gitignore.

FORBIDDEN PATH: nothing under `/tmp/openlayout/` was opened, read,
grepped, listed, or diffed at any point. Rule names/values come from
the DRM alone; deck expression, fixture geometry, colors, and text
are original. Validation methodology (per-rule breaker + clean ref)
is the only adopted idea.

## RED -> GREEN evidence

RED (no lane files), `.venv/bin/pytest tests/test_asap7deck_inventory.py
tests/test_asap7deck_tech.py tests/test_asap7deck_deck.py`:
13 failed, 5 errors — all FileNotFoundError-class (missing lane
files/deck), adapter raising `invalid_reference` with no deck.

GREEN (same command): all pass — 6 inventory + 5 tech + 1 deck-gate
+ 117 breaker + 2 clean + 1 invx1 + 1 preflight + 1 oracle = 134.

Neighbors (adapter untouched, still green):
`.venv/bin/pytest tests/adapters/test_drc_kl.py
tests/adapters/test_drc_sky130.py` — all pass/skip as before (sky130
deck tests skip: no registered sky130 deck in this env).

## Verification notes and refusals

- Deck mechanics were proven empirically in scratch before the lane
  was written (directional edge spacing, extension-by-shrink,
  `enclosed`-form rectangle filters, exact bbox checks, area units,
  on-grid, `-rd` batch globals); the breaker suite re-proves each
  one on every run, and the oracle test re-verifies one breaker +
  clean via raw klayout, independent of the adapter.
- Two soundness traps found and fixed during GREEN: (1) rectangle
  filters key on the check's own layer, so via enclosure uses the
  `enclosed` form (verified: `enclosing` form does not waive);
  (2) `Layer#not_in` does not mean geometric containment, so all
  inside-checks use boolean subtraction (verified).
- Refused/left out (documented, not silent): nonzero M4-M7 grid
  offsets; V9 top-metal checks (Pad unmapped); M8.W.5 under either
  operator guess; `.lyp` GUI-load verification (no Xvfb in this
  env — structural validation only, manual follow-up); engine-store
  registration of deck+tech (needs existing-file edits — parent
  decides; no patch supplied since registration schema is the
  parent's call).
- Full suite NOT run per lane rules (new tests + named neighbors
  only). No commit, no push.
