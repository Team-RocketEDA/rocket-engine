# SymbiYosys formal adapter

FormalSbyAdapter serves run_formal with SBY. It creates a task from the job's project sources, mode, depth, and engines, runs it under a timeout, and parses the status file and DONE summary into scoped evidence.

Results distinguish proven, bounded, bounded-vacuous, unknown, and timeout. A PASS always carries its proof scope and checked properties. A proof with no active property is reported as bounded-vacuous failure, not a clean PASS. Counterexamples and assumptions are included where available.

The adapter is registered in Engine as the sby solver. It requires a version-asserted SBY binary, resolved from the job tool_dir or PATH. See the [FORMAL-SBY report](../../../docs/work/FORMAL-SBY/report.md), [FORMAL-EDGE report](../../../docs/work/FORMAL-EDGE/report.md), and [provision plan](../../../docs/provision-plan.md).
