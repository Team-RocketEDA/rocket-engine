# RUN-PARAMS: Explicit run.request params schema

*Status: Ready · Size: S · Roadmap: convergence (MVP track)*

## Why

Runs are explicit, always — no live-update path in MVP —
which means every knob a run needs must travel IN the run
request, not hide in ambient config. xschem keeps netlist
knobs (`netlist_type`, `flat_netlist`, `lvs_netlist`,
`top_is_subckt`, …) as live TCL vars; our web split cannot
do that without per-event round-trips, so those knobs
become explicit `run.request` parameters, frozen into the
run snapshot like everything else. Without this schema,
run reproducibility (I28) has a hole: two identical-looking
runs could differ by a knob nobody recorded. Small ticket,
load-bearing invariant.

## What

- RED-first: `run.request` schema — netlist type,
  flat/split shape, lvs_netlist flag, top_is_subckt, deck
  opts passthrough — validated at submit, frozen into
  `inputs.yaml`, rejected loudly when unknown.
- Submitters (IDE, MCP, console) send the same shape; no
  caller-specific params.
- Unknown fields rejected, never ignored.

## Acceptance

- Same request replays byte-identical inputs; unknown
  field fails submit with a named reason; snapshot shows
  every knob.
- Contract + api_spec regen; full suite + gate green.
