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
