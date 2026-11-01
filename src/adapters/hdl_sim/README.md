# Icarus HDL simulation adapter

HdlSimAdapter serves run_hdl_test. It compiles project testbench and design sources with iverilog, runs them with vvp under a timeout, and parses compile diagnostics, FATAL, and ERROR output into normalized findings.

The adapter is registered in Engine as the icarus solver. Tool resolution uses PATH or an explicit job tool_dir. When a BwrapRunner is supplied, compile and simulation processes run inside the configured isolation boundary.

Some HDL failures can exit with status zero. Verdicts come from parsed diagnostics and simulation output, never the exit code alone.
