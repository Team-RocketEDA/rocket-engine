# EXTRACT-GDS: run_extraction must accept GDS, not .mag-only

*Status: Ready · Depends: none · Size: M ·
Roadmap: hardening (E2E-REREVIEW FIND-08, MED)*

## Why

run_extraction is .mag-only (extract_magic:35-38)
while bandgap-class layouts are GDS-only — so no
engine-produced bandgap layout.spice exists and the
LVS leg fell back to a fixture netlist. Extraction
that can't read the engine's own layout output breaks
the layout→netlist→LVS chain the PRD requires.

## What

- RED-first: GDS input path for run_extraction (via
  magic -d GDS read or the KLayout-shaped route per
  MAGIC-EXIT direction); .mag path kept, both proven.
- Bandgap: engine-produced layout.spice feeds LVS.

## Acceptance

- GDS in → extracted netlist out with provenance;
  bandgap chain unblocked or loudly blocked.
- Contract + api_spec regen; full suite + gate green.
