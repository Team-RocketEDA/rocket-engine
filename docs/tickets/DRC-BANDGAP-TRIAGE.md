# DRC-BANDGAP-TRIAGE: Foundry deck 740x li.5 vs fixture-clean

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-03, HIGH)*

## Why

The bandgap layout is fixture-clean but the foundry
deck reports 740 li.5 violations through the engine.
Either the layout is really broken (fix the fixture)
or the deck/adapter disagrees with the reference flow
(fix the parity) — today nobody knows which, and a
740x flood drowns any real signal.

## What

- Triage with evidence: reproduce, classify real vs
  deck-parity vs setup gap (drc_kl:164-173), fix the
  losing side, pin a regression test with the verdict.
- If real: repair fixture, document the violation
  class. If parity: align deck/adapter, keep both
  green.

## Acceptance

- Bandgap DRC leg green with the root cause named in
  the report; regression pinned.
- Contract + api_spec regen; full suite + gate green.
