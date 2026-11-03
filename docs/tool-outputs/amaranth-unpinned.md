# amaranth (unpinned) — backend Verilog frontend (run_synth)

Version provenance: `import amaranth` loads in the engine venv;
no provision pin (pin amaranth first). Provider
`src/adapters/synth_yosys/amaranth.py`.

## Report inventory

The frontend emits generated backend Verilog in-process (which
does not count as mixing per CANVAS-CST v1); foreign authored
source still needs explicit migration qualification.

## Exit states

- amaranth absent: `missing_dependency` with BLOCKED-needs-host
  (pin amaranth first).
- Emission is deterministic (fixed header, no timestamps).
