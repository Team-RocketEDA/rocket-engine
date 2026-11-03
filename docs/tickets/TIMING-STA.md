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

*RULING-03 (T-20): PARKED pending PROV-UPSTREAM-RECIPE — parking ends when provisioning is solved (user building manually meanwhile), not by scope decision. Adapter exists but STA grammar stays residue-only until the tool lands.*

## Verdict (Wave-2, 2026-11-03) — Ready, BLOCKED-needs-host

Top-level recheck path verified end to end (M11 entrypoint,
vocabulary, contract all list run_timing) with loud skips intact;
no code change needed. Live demonstration waits on sta on a
networked host (UPSTREAM-RECIPE source build infeasible here).

*Note 2026-11-03: host now has every OpenSTA build prereq
(git/cmake/make/g++/swig/bison/flex/tcl/eigen all present; only
the earlier "missing swig" remedy is stale) and the opensta-857316f
+ cudd sources already cloned — re-running
scripts/provision_toolchain.sh --install on the host should
complete the build where it stalled before. Sandbox cannot write
/home/alrida-ismail/tools (read-only) and CUDD is unbuilt there,
so this step must run on the host, not here.*
