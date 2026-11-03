Why: docs/adapter-stdio-review.md found ~17 field groups with a known file channel; migrate the top 5 mechanical moves so adapters read files instead of scraping stdio. No flag/behavior change to tools beyond what is listed.

Moves:
1. ngspice + postlayout tier 1: parse -o log only (no flag change).
2. formal_sby: read formal/logfile.txt instead of stdout (same regexes).
3. hdl_sim (+cosim digital): add vvp -l logfile in execute (live-verified byte-identical).
4. synth_yosys: parse synth.log only (fixes -q double-report).
5. syntax: add slang --diag-json, derive counts from JSON (fixture-pin the schema).

Acceptance per move (tdd-workflow RED->GREEN): existing golden fixtures still pass byte-identical; new test pins the file channel; stdio parse path removed or kept only as fallback with a loud marker. Residue stays: magic DRC (no file channel), ngspice error quotes (from persisted logs), iverilog compile diags.

## Verdict (Wave-2, 2026-11-03) — Done

All 5 moves landed: ngspice/postlayout parse -o log only;
formal reads formal/logfile.txt; hdl_sim/cosim vvp -l
(live-verified byte-identical on vvp 14.0); synth_yosys parses
synth.log only; syntax --diag-json with live-pinned schema.
9 new tests + 213 existing adapter tests green; golden fixtures
byte-identical.
