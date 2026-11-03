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
