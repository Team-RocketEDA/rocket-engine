# ASAP7-DRC-DECK: Clean-room KLayout DRC deck transcribed from the DRM

*Status: Done · Depends: PDK-ASAP7 (spike) · Size: L ·
Roadmap: pdk-onboarding (MVP track)*

## Why

Our ASAP7 matrix has inventory + layout-view proofs but
`n/a` custom rows: no KLayout tech, no DRC deck, no models.
r1p7 ships none of these (Cadence/Calibre/HSPICE only), yet
the DRM (`docs/asap7_drm_201207a.pdf`, ASU Dec 2020) fully
specifies the rules — rule names, values, and figures are
facts. OpenLayout proved a KLayout deck can be written
rule-by-rule from it; we transcribe our own from the same
primary source. This turns ASAP7 from "counted and
photographed" into "verifiable": DRC runs through the
existing KLayout adapter deck mode with zero engine
changes, and the deck becomes the first DRM-derived
artifact in the store (pattern for any PDK whose decks are
missing but documented).

## Clean-room sourcing rules (binding)

- ALLOWED sources only: the r1p7 PDK (`asap7_pdk_r1p7`
  submodule @58d72c9 — DRM PDF, tech data, LEF/GDS),
  the lane probe clone at `/tmp/asap7r1p7-probe`, our
  `/tmp/pdk-sources/asap7*` clones, and KLayout's own
  docs. The implementer MUST be able to list every file
  read; the report carries the list.
- FORBIDDEN: `/tmp/openlayout/**` in any form — never
  open, read, grep, or diff it. Rule names/values come
  from the DRM alone. Validation methodology (per-rule
  breakers + clean refs) is an uncopyrightable idea and
  is adopted; no OpenLayout expression is reproduced.
- Verification of hygiene: the lane report's source list
  is reviewed before any commit; any OpenLayout-derived
  content fails review unconditionally.

## What

- RED-first: full DRM rule inventory (every rule named +
  counted, deferred set recorded); core set implemented
  first (metal/via/active/poly/fin width + space +
  enclosure + grid rules); generated KLayout tech
  (lyt/lyp) from PDK data, written by us.
- Validation per rule: a breaker layout that MUST trip
  it + clean refs that MUST stay clean (INVx1 fixture,
  via cells, stdcell placements); waivers documented
  with DRM citations, never silent.
- Runs through the existing KLayout DRC adapter (deck
  mode) unchanged; deck + tech registered in the store
  with manifest hashes like any PDK deck.

## Acceptance

- Core rule set green: every breaker trips exactly its
  rule, every clean ref is marker-free, waivers cited.
- Inventory + deferral list complete so the remainder is
  mechanical follow-up, not rediscovery.
- No forbidden-source content (source list reviewed).
- Contract + api_spec regen if surfaces change; full
  suite + gate green.
