Problem: digital_flow verdicts come from unpinned text scraping: generic DRC regexes (:60-62, :220-236), STA verdict = "violated" substring (:63/:296), equiv verdict = keyword list (:64/:328), step matcher on lowercase substring with drift-admitting comments (:74-75,:147-157). Fails the uranium-grade rule (no adapter on unpinned text scraping).
Expected-per: audit blesses only run-dir machine files + import librelane (audit:109); grammars in docs/tools/librelane.md (state_out.json metrics + views paths + metrics.csv). Audit MC-17, D-28.
Fix: rewrite readout on run-dir machine files; delete generic regex/keyword verdicts. TDD: fixtures from real LibreLane run dirs.

## Verdict (Wave-2, 2026-11-03) — Ready, BLOCKED-needs-host (live leg)

Code complete: `src/adapters/digital_flow/state.py` reads
state_out.json/metrics.csv only; generic DRC/STA/equiv/LVS
regex-keyword verdicts deleted; text-only trees fail loud naming
the machine files. 3 uranium RED->GREEN + 58 flow tests green.
Carry: live librelane proof (binary + PDK absent on this host);
metric key families fixture-pinned (OpenROAD timing keys grounded,
DRC/LVS/equiv best-knowledge) pending live-run confirmation.

## Verdict (Wave-4, 2026-11-03) — Done: proved live, LibreLane 3.0.17

Host built the chain in-repo: pinned AppImage runs extracted +
user-ns bind of its nix store (no FUSE needed), sky130A fetched
+ enabled via ciel into a local PDK root. First live runs exposed
four real-tool corrections, all fixed RED→GREEN: CLI flag is
`--run-tag` (not `--tag`); 3.x writes NO metrics.json — verdicts
come from state_out.json `metrics` (corner-suffixed STA keys take
worst-across-corners, `magic/klayout__drc_error__count`,
`design__lvs_unmatched_{device,net,pin}__count`, plus the
`drc.klayout.json`/`lvs.netgen.json` signoff reports); classic
flow has NO formal-equiv step — D27 force-bypassed loudly
(FORMAL-SBY owns proof), forced status asserted in-test;
small-design recipe from upstream spm (PDN offsets 5, widths 2,
pitches 30, SKIPTRIM, FP_CORE_UTIL 30) via job `config`
passthrough — PDK-default met4 straps don't fit a ~17 µm core
(PDN-0185). Counter live GREEN (GDS + DRC 0 + LVS match +
margins); SERV live GREEN at 20 ns (10 ns leaves ss-corner setup
open at WNS −2.49 ns with default effort — measured, STA gate
still judging). Full flow file 58 green incl. serv (15.5 min).
