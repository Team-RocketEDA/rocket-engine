# DIGITAL-FLOW: run_digital_flow via LibreLane (one click RTL to GDS)

*Status: Ready · Depends: SYNTH-YOSYS, PROV (LibreLane
distribution closure) · Size: L · Roadmap: to-GDS lane
(MVP track, PRD tech-stack ASIC-implementation row)*

## Why

This is the ticket the whole engine exists for: stages
D11–D27 describe the LibreLane flow (floorplan, place,
route, extract, signoff) as required steps with
entrypoint `run_digital_flow`, and today that entrypoint
is hollow. One API dispatch must take user Verilog to a
verified GDS: synth → floorplan → place → route → STA →
extraction → DRC/LVS, with per-stage evidence and gates.
Use the upstream LibreLane supported distribution
closure (its pinned Yosys/ABC, OpenROAD/OpenDB, OpenSTA,
OpenRCX, Magic/Netgen/KLayout, Tcl) — never assume `pip
install librelane` contains the native tools, per the
PRD. Timing evidence rides the flow reports first (no
standalone STA adapter until a flow-external need
proves itself).

## What

- RED-first: `run_digital_flow` ToolAdapter driving the
  pinned LibreLane distribution as a subprocess flow;
  per-stage evidence (config, reports, DB checkpoints),
  stage gates with force-bypass per the verdict-gate
  policy, bounded + cancellable long runs.
- SERV end-to-end: Verilog → GDS → KLayout DRC +
  Netgen LVS against the schematic, all inside one
  dispatched flow with inspectable stage artifacts.
- deck.tool `librelane`; missing distribution → loud
  `missing_dependency` with the PROV remedy. Flow
  failures name the failing stage + report, never a bare
  traceback.

## Acceptance

- One dispatched call takes SERV RTL to a DRC/LVS-checked
  GDS; stage evidence complete; a broken-RTL variant dies
  at synth with cause.
- Contract + api_spec regen; full suite + gate green.
