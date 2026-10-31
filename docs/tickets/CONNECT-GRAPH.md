# CONNECT-GRAPH: Shared connectivity extraction + raw-IR emitters

*Status: Ready · Size: L · Roadmap: convergence (MVP track)*

## Why

Every netlist backend — SPICE, Verilog, VHDL — answers the
same question first ("which pins share which nets?") and
today each would answer it its own way. xschem's thirty-year
lesson is blunt: extract ONE connectivity graph, then print N
syntaxes from it, with a raw intermediate plus a small
textual post-pass per language so bus expansion and line
joinery live in exactly one place each. Without a shared
extraction, net identity splits per backend and ERC, export,
and simulation quietly disagree about the same wires — the
worst class of EDA bug because every view looks locally
correct. This ticket makes the engine the single net-naming
authority the schematic editor, emitters, and ERC all read.

## What

- RED-first: `prepare_netlist_structs` analog —
  spatial-hash wires + instance pins, propagate names from
  labels, name unlabeled nets/instances/generics, honor
  `lvs_ignore`; cached behind explicit-run guards.
- Raw IR + textual post-pass per language (SPICE first,
  Verilog/VHDL following); never hand-emit final syntax
  from the graph walker.
- 4-level format chain
  instance-custom → symbol-custom → instance-format →
  symbol-format; missing name+format skips the instance
  silently.
- One `net_name()` authority shared by all printers + ERC.

## Acceptance

- Same schematic emits SPICE/Verilog/VHDL with identical
  net identity; unlabeled nets get stable names; `lvs_ignore`
  respected; golden netlists byte-stable across runs.
- Contract + api_spec regen; full suite + gate green.
