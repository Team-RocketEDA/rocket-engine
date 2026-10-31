# TIMING-STA: Standalone run_timing via OpenSTA (top-level recheck)

*Status: Ready · Depends: PROV (LibreLane/OpenSTA
binaries) · Size: M · Roadmap: to-GDS lane (MVP track,
serves M11)*

## Why

Block-level timing rides the DIGITAL-FLOW stage reports —
but M11 rechecks timing at the TOP level with real
loads, extracted RC, generated clocks, and analog/digital
boundary constraints, after GDSFactory assembly changed
the geometry. Block evidence is historical the moment
assembly moves; only a standalone STA op can sign the
assembled chip. OpenSTA from the LibreLane closure is
the vehicle.

## What

- RED-first: `run_timing` ToolAdapter (deck.tool
  `opensta`): mapped netlist + timing libs + SDC →
  setup/hold, WNS/TNS, critical paths, slew/load,
  unconstrained endpoints.
- Mixed fixture: digital block + analog boundary with
  top-level SPEF; boundary constraints honored, missing
  constraints reported as findings (never assumed).
- Missing binary → loud `missing_dependency` with the
  PROV remedy.

## Acceptance

- Top-level timing recheck dispatches standalone with a
  paths-and-margins report; unconstrained endpoints
  listed, never silent.
- Contract + api_spec regen; full suite + gate green.
