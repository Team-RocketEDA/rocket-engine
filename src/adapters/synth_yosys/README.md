# Yosys synthesis adapter

YosysSynthAdapter serves run_synth. It reads the project RTL, checks and synthesizes the requested top, optionally maps cells using a supplied Liberty file, and returns normalized findings, cell counts, area when available, and the generated netlist artifact.

The adapter is registered in Engine as the yosys solver. Tool resolution uses PATH or an explicit job tool_dir and checks the Yosys version banner. A BwrapRunner can confine the process with tool roots read-only and a writable job directory.

Qualification covers counter fixtures, SERV, and picorv32, including mapped and generic runs. Warnings such as latches and undriven wires are surfaced as findings; broken RTL and missing tops fail loudly. See the [SYNTH-YOSYS report](../../../docs/work/SYNTH-YOSYS/report.md).
