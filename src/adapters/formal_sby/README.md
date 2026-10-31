# adapters/formal_sby — sby formal solver

`run_formal` behind the `ToolAdapter` port: preflight refuses the
wrong operation, foreign deck tools, bad proof inputs (mode, depth,
top, engines), missing sources, and unresolvable or impostor sby
(the banner is version-asserted; the remedy names the PROV
oss-cad-suite bundle); execute generates a `formal.sby` task from
the job's project sources and runs `sby -f` bounded and
cancellable (own process group, timeout SIGKILLs the tree, expiry
reports scope timeout instead of hanging); parse normalizes the
sby status plus the DONE summary into scoped measurements —
proven (prove PASS), bounded (bmc/cover PASS to the depth, FAIL
with counterexamples), unknown (inconclusive or sby ERROR), or
timeout — with assumptions, properties, failures, and cover
witnesses. Never a bare PASS: PASS always carries its scope, and
unknown/timeout fail loudly.

Verified against sby v0.70 on counter fixtures plus a SERV ALU
property (`tests/adapters/fixtures/formal/`). Tool resolution is
PATH plus an explicit job `tool_dir`; where the suite lives is
PROV/B10 scope. Engine registration is the integrator's wiring
patch (`docs/work/FORMAL-SBY/wiring.patch`).
