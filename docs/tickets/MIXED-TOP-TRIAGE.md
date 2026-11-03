# MIXED-TOP-TRIAGE: m4.5ab DRC, deck-mode cell arg, xschem top-LVS

*Status: Ready · Depends: none · Size: M ·
Roadmap: hardening (E2E-REREVIEW FIND-11 + FIND-12 + FIND-13)*

## Why

The mixed top cell trips three issues at once: klayout
m4.5ab FAIL vs documented magic-DRC 0 (real or deck
delta — needs PDK/deck triage, distinct fixture from
FIND-03); deck-mode DRC ignores the cell arg
(drc_kl:263,205-238); sd_top top-LVS is unreproducible
because xschem hierarchical *_top.sch silent-fails
(flat control works, adapter green on inv_2).

## What

- Triage each with evidence: m4.5ab real-vs-delta
  verdict; cell-arg honored in deck mode; xschem
  hierarchical root cause (or loud limitation with
  the flat workaround pinned).
- Regressions for whatever gets fixed; loud
  blockers for whatever doesn't.

## Acceptance

- All three resolved (fixed + pinned) or loudly
  blocked with causes in the report.
- Contract + api_spec regen; full suite + gate green.

## Verdict (2026-11-03, 2 GREEN + 1 BLOCKED-needs-host)

- Deck-mode cell: FIXED + pinned. `_resolve_cell_or_raise`
  (`src/adapters/drc/klayout.py`) honors the claim read-only:
  unknown cell -> `invalid_reference`; present-but-inner cell
  -> `invalid_command` (deck mode is whole-GDS); multi-top
  without cell -> `invalid_command` naming the tops (was a
  silent `top_cell()` pick). Existing synthetic DRC tests
  unchanged (single-top, no cell).
- m4.5ab: BLOCKED-needs-host. No `ROCKETEDA_HOME` store and no
  `sky130A.lydrc` exist on this host, so the engine FAIL vs
  magic-DRC-0 delta cannot be re-adjudicated here. Recorded
  instead: the `m4.5ab` lyrdb signature parses to a ruled bbox
  violation and the store-resolution probe skips loudly
  (`tests/adapters/test_mixed_top.py`).
- xschem hierarchical: ROOT CAUSE FOUND (env/rcfile, not
  hierarchy). The fixture xschemrc hardcodes
  `XSCHEM_SHAREDIR /usr/share/xschem` while installs live at
  `/usr/local` — startup dies with `Tcl_AppInit() err 4` and
  exits 0 with no output (both flat and hierarchical went
  silent here). The `src/adapters/xschem/` wrapper rcfile pins
  SHAREDIR around the project source; `ota_top.sch` netlists
  (remaining pin-count errors are fixture content, surfaced in
  the log). Pinned live by the hierarchical test + the
  DECK-XSCHEM byte-compare tests.
- Method: `docs/probe-mixed-top.md`, `docs/probe-xschem-deck.md`.
  Contract/api_spec regen and Engine wiring are another
  surface's (composition.py is outside the owned set).
