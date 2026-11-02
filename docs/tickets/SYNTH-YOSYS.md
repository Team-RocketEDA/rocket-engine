# SYNTH-YOSYS: run_synth via oss-cad-suite Yosys (RTL to mapped netlist)

*Status: Done · Depends: PROV (oss-cad-suite tarball) · Size: M ·
Roadmap: to-GDS lane (MVP track, PRD tech-stack ASIC row)*

## Why

The digital chain today is lint → sim → nothing: vocabulary
names the flow, stages.py requires it, but no adapter
synthesizes. Without synthesis there is no "to GDS" — the
PRD's stitch-the-ecosystem directive and the one-click
Verilog→GDS ask both die here. Yosys (pinned inside the
oss-cad-suite distribution, no separate install) closes the
first missing link: RTL in, mapped netlist + area/cell
evidence out.

## What

- RED-first: `run_synth` ToolAdapter driving pinned
  `yosys` (`synth -top`, sky130 cell mapping where the PDK
  permits); evidence = mapped netlist artifact, cell
  counts, area estimate, warnings-as-findings.
- deck.tool `yosys`; missing binary → loud
  `missing_dependency` naming the PROV bundle, never a
  PATH lottery (per tech-stack scoping rule).
- SERV + picorv32 fixtures: synth proves clean with
  expected cell families; mutated RTL (undriven/latch)
  surfaces as findings.

## Acceptance

- Click-equivalent API call synthesizes SERV to a mapped
  netlist with evidence; bad RTL fails loudly with cause.
- Contract + api_spec regen; full suite + gate green.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
