# DRC-BANDGAP-TRIAGE: Foundry deck 740x li.5 vs fixture-clean (TRIAGED 2026-11-03)

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

## Verdict (2026-11-03, triaged — fix belongs to fixture + DRC-path owners)

Reproduced with the current deck and adapter recipe: KLayout
0.28.16, store deck `libs.tech/klayout/drc/sky130A.lydrc`
(`sky130a@5f09001e`), GDS
`.../reports/20260817-020222-13476b7/bandgap_core_routed.gds`,
run as the adapter runs it
(`klayout -b -rd input=<gds> -rd report=<lyrdb> -r <deck>`, no
top-cell selection). Result: FAIL, total 740 through
`KlayoutDrcAdapter.parse` — the adapter reports faithfully.

Correction to the ticket/journey text: it is NOT "all 740 one
rule". The current split is 672 OFFGRID + 68 li.5 (240
licon_OFFGRID, 240 ct_OFFGRID, 132 m1_OFFGRID, 24 li_OFFGRID, 20
via_OFFGRID, 16 m2_OFFGRID, 68 li.5). Same total as the journey's
2x runs, so the earlier "first page all li.5" reading
under-described the flood.

Classification, with evidence:

- 672 OFFGRID (91%): setup/parity gap, not functional defects.
  Every sampled vertex sits on the 1 nm generator grid but off
  the foundry 5 nm manufacturing grid the deck enforces
  (`<layer>.ongrid(0.005)`, gated by `OFFGRID = true` in the
  deck; e.g. ct_OFFGRID at y=103.148/103.233, li_OFFGRID at
  y=43.217, licon_OFFGRID at y=20.137 — all `mod 5nm != 0`).
  The fixture `drc.json` is clean/0 because the klt curated deck
  has no offgrid section (its coverage report lists no
  manufacturing-grid rules). The engine DRC path has no
  grid-snap or waiver step. Fix direction: OFFGRID-gated deck
  handling or waivers in the DRC path — deck-mode invocation is
  MIXED-TOP's surface (do-not-touch this wave) and the drc
  adapter is outside this wave's owned set.
- 68 li.5: REAL defect class. Rule: min li enclosure of licon
  0.08 um on 2 opposite edges. All 68 are DISTINCT 0.17x0.17 li
  stubs — exactly licon-sized, zero enclosure — localized to
  `bandgap_core_bus__bandgap_core_bus` (not hierarchy-amplified).
  The klt deck passes them only by coverage gap (no
  li-enclosure rule evident). Fix direction: regenerate the bus
  cell with enclosed li stubs through the fixture flow (the
  vendored tree cannot be hand-edited).

No change in this wave's owned files (extract/lvs adapters and
their tests): the losing sides are the fixture geometry and the
DRC-path deck handling, both outside scope. No `test_drc*`
regression pinned here (`tests/adapters/test_drc*.py` is not
owned); suggested pins for the owners: (a) an OFFGRID-gated deck
run over the routed GDS asserting the offgrid bucket is empty
post-snap/waiver, (b) a li-enclosure unit over the bus cell
asserting zero li.5 post-regen. `scripts/api_spec.py --check` /
`scripts/contract.py --check` currently crash on another agent's
in-flight `composition.py` breakage — recorded, not caused here.
