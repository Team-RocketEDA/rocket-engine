# Mixed-top triage probes (MIXED-TOP-TRIAGE, 2026-11-03)

Three legs from `docs/work/E2E-REREVIEW/journey-mixed.md` J7/J8.
Tool versions: KLayout 0.28.16, xschem V3.4.8RC.

## 1. Deck-mode cell: honored (was silently dropped)

`KlayoutDrcAdapter.preflight` dropped `cell` in deck mode while
the recipe (`klayout -b -rd input= -rd report= -r <deck>`) has no
top-cell selection — a multi-top GDS silently checked
`top_cell()` against another claim (journey F3). Now
`_resolve_cell_or_raise` verifies the claim read-only via the
layout DB: unknown cell -> `invalid_reference`; present but
non-top cell -> `invalid_command` (deck mode is whole-GDS, it
cannot scope); several tops without a cell -> `invalid_command`
naming the tops. The honored top rides in `checked["cell"]`.
Pinned by `tests/adapters/test_mixed_top.py` (deck units); the
existing synthetic DRC tests are unaffected (single-top, no
cell — same behavior as before).

## 2. m4.5ab: BLOCKED-needs-host (no foundry deck on this host)

The leg needs store deck `libs.tech/klayout/drc/sky130A.lydrc`
(`sky130a@5f09001e`) over the vendored
`tt_um_pthomas_sigma_delta.gds`. No `ROCKETEDA_HOME` store and no
deck file exist on this host (searched `/`, the repo, and env),
so the 10x `m4.5ab` FAIL vs fixture-documented magic-DRC 0
cannot be re-adjudicated here. Recorded instead: the exact
`m4.5ab` lyrdb signature parses to a ruled bbox violation
(`test_m45ab_recorded_rule_parse_with_bbox`), and the
store-resolution probe skips loudly where the deck is absent
(`test_mixed_top_drc_needs_foundry_deck_or_skips`) — never
fake-green. Triage stays open for a deck-bearing host.

## 3. xschem hierarchical: ROOT CAUSE FOUND (rcfile SHAREDIR)

The journey's "hierarchical silent-fail" (ota_top/comp_top exit
0/1, no output; flat control fine) reproduces here on BOTH flat
and hierarchical schematics — the flat control also went silent
in this env, which reframed the cause: the fixture xschemrc
hardcodes `XSCHEM_SHAREDIR /usr/share/xschem` while the install
lives at `/usr/local/share/xschem`, so startup dies with
`Tcl_AppInit() err 4: cannot find /usr/share/xschem/xschem.tcl`
and exits 0 with no output. It is an env/rcfile mismatch, not a
hierarchy bug. With a wrapper rcfile pinning SHAREDIR around the
project source, `ota_top.sch` netlists (3260 B; remaining
`ota.sym` pin-count errors are fixture content, surfaced in the
log, not silent). The seam lives in `src/adapters/xschem/`
(wrapper + init-error detection + loud no-output refusal);
pinned live by
`test_xschem_hierarchical_netlists_with_wrapper_rcfile` and the
DECK-XSCHEM byte-compare tests.
