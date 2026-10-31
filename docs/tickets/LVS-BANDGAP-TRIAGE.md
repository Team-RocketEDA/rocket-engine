# LVS-BANDGAP-TRIAGE: Netgen 185 mismatch vs fixture match

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-04, HIGH)*

## Why

Netgen reports 185 LVS mismatches on the bandgap
through the engine while the fixture flow matches.
Device-combining vs setup-mapping is undiagnosed
(lvs_netgen:248-256), and no engine-produced
layout.spice exists — the leg used a fixture klt
netlist instead of extraction output. Related to
LVS-ESCAPE (possible shared setup root, kept
separate until proven).

## What

- Triage with evidence: reproduce, classify combining
  vs setup vs fixture gap, fix, pin regression.
- Produce the missing engine extraction output for
  the leg where feasible (x-ref EXTRACT-GDS).

## Acceptance

- Bandgap LVS leg green (or loudly blocked with the
  cause); root cause in the report; regression pinned.
- Contract + api_spec regen; full suite + gate green.
