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
