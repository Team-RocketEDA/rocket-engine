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

## Verdict (2026-11-03, adapter leg GREEN / full match BLOCKED-needs-host)

p/n adjudicated with the Wave-1 bulk-grouping evidence
(`docs/probe-extract-gds.md`): magic's own `.ext` groups 52
devices on one common bulk plus 8 pairs, mirroring the klt
`nfet 16 / pfet 52` split exactly — the klt side is right and
magic's uniform-pfet typing is the recognition gap. The
adapter now adjudicates by bulk (`retype_by_bulk`, suffix
kept, unknown bulks untouched) and inlines hierarchy from the
root (`flatten_hierarchy`, slice-then-inline when `cell` is
given); M-line inventory covers the klt/reference format.
Pinned by `tests/adapters/test_lvs_bandgap.py` (14 tests: exact
transform + live netgen MATCH on the synthetic bandgap shape,
no PDK needed) with `test_extract_sky130.py` +
`test_lvs_escape.py` still green.

Loudly blocked, not faked: the real klt pair (229 vs ~28
devices, m-factors/combining) still FAILs through the adapter
with a bare setup — the fix belongs to the setup/deck surface
outside this wave's owned set, and the PDK tech is absent on
this host (`test_bandgap_klt_pair_still_mismatches_without_setup_mapping`).
Method: `docs/probe-lvs-bandgap.md`. Contract/api_spec regen
and Engine wiring are another surface's (composition.py is
outside the owned set).
