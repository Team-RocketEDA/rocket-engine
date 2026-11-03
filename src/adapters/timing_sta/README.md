# OpenSTA timing adapter

OpenStaTimingAdapter serves run_timing with the opensta tool. It runs a top-level timing recheck from the mapped netlist, timing libraries, SDC, and optional top-level SPEF, then returns setup/hold slack, critical paths, slew/load findings, and unconstrained endpoints.

The adapter is registered in Engine. Preflight refuses missing inputs, invalid tops/timeouts, and unavailable or unassertable tools. Execution writes a timing script, runs sta under the job timeout with stdin closed, and includes an explicit exit command so STA cannot remain at its prompt.

The parser treats violated paths, violated constraints, and any Error line as failures. Warnings do not fail alone; raw check_setup output carries missing constraints so they are visible. Missing constraints are never assumed away.

Tool resolution uses the job tool_dir, then OPENSTA_PREFIX/bin, then PATH. The binary must report an OpenSTA version banner.
